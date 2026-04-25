"""Layer 0: Pre-checks validation.

This module performs early sanity checks before running expensive operations:
- YAML/schema validation via ansible-lint (required dependency)
- Dependency file existence checks
- Build argument / environment variable validation
- Container registry authentication checks
- Automation Hub collection warnings

Schema and format validation is delegated to ansible-lint. Custom checks
here only cover runtime concerns (file existence, env vars, registry auth)
that ansible-lint cannot verify.

Errors in this layer (e.g., missing files) skip Layers 1-3.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess

import yaml

from ..models import DepFormat, Finding, LayerResult, LayerStatus, Severity, ValidateContext


def validate(ctx: ValidateContext) -> LayerResult:
    """Run Layer 0 pre-checks.

    Args:
        ctx: Validation context

    Returns:
        LayerResult with status "fail" if required files are missing, "pass" otherwise
    """
    findings: list[Finding] = []

    _check_ansible_lint(ctx, findings)
    _check_file_refs(ctx, findings)
    _check_build_args(ctx, findings)
    _check_registry_auth(ctx.ee.base_image, findings)
    _check_ah_collections(ctx, findings)

    has_missing_files = any(f.code == "missing_file" for f in findings)
    status: LayerStatus = "fail" if has_missing_files else "pass"

    return LayerResult(name="prechecks", status=status, findings=findings)


def _check_ansible_lint(ctx: ValidateContext, findings: list[Finding]) -> None:
    """Run ansible-lint on the execution-environment.yml file.

    Optional check: skips if ansible-lint is not installed. Reports YAML
    formatting and style issues as warnings.

    Args:
        ctx: Validation context
        findings: List to append findings to
    """
    try:
        proc = subprocess.run(
            ["ansible-lint", "--format", "codeclimate", str(ctx.ee.path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            _parse_ansible_lint_output(proc.stdout, findings)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass


def _parse_ansible_lint_output(output: str, findings: list[Finding]) -> None:
    """Parse ansible-lint codeclimate JSON output into findings."""
    for line in output.splitlines():
        line = line.strip()
        if not line.startswith("["):
            continue
        try:
            issues = json.loads(line)
        except json.JSONDecodeError:
            continue
        for issue in issues:
            rule = issue.get("check_name", "")
            desc = issue.get("description", "")
            severity = Severity.ERROR if "schema" in rule else Severity.WARNING
            findings.append(
                Finding(
                    severity=severity,
                    message=f"ansible-lint [{rule}]: {desc}",
                    code="ansible_lint",
                )
            )
        return



def _check_file_refs(ctx: ValidateContext, findings: list[Finding]) -> None:
    """Check that all referenced dependency files exist.

    Reports ERROR if a file referenced in dependencies (e.g., requirements.txt)
    does not exist on disk.

    Args:
        ctx: Validation context
        findings: List to append findings to
    """
    for _dep_name, dep_ref in [
        ("galaxy", ctx.ee.galaxy),
        ("python", ctx.ee.python),
        ("system", ctx.ee.system),
    ]:
        if dep_ref is None:
            continue
        if dep_ref.format.value == "file" and dep_ref.file_path and not dep_ref.file_path.exists():
            findings.append(
                Finding(
                    severity=Severity.ERROR,
                    message=f"Dependency file not found: {dep_ref.file_path.name}",
                    fix=f"Create {dep_ref.file_path.name} in {ctx.ee.ee_dir}",
                    code="missing_file",
                )
            )


def _check_build_args(ctx: ValidateContext, findings: list[Finding]) -> None:
    """Check that ARGs declared in build steps have environment variables set.

    Scans additional_build_steps for ARG declarations and warns if the
    corresponding environment variable is not set.

    Args:
        ctx: Validation context
        findings: List to append findings to
    """
    for arg_name in ctx.ee.build_args:
        if not os.environ.get(arg_name):
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    message=f"ARG {arg_name} declared in build steps but ${arg_name} is not set",
                    fix=f"export {arg_name}=<value> before running",
                )
            )



AUTHENTICATED_REGISTRIES = (
    "registry.redhat.io",
    "registry.connect.redhat.com",
)


def _check_registry_auth(image: str, findings: list[Finding]) -> None:
    """Check if container registry credentials are configured for the base image."""
    registry = image.split("/")[0] if "/" in image else None
    if not registry or registry not in AUTHENTICATED_REGISTRIES:
        return

    for runtime in ("podman", "docker"):
        if not shutil.which(runtime):
            continue
        try:
            proc = subprocess.run(
                [runtime, "login", "--get-login", registry],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return
        except subprocess.TimeoutExpired:
            return

    findings.append(
        Finding(
            severity=Severity.WARNING,
            message=f"Not logged in to {registry} — Layer 3 container pull will fail",
            fix=f"podman login {registry}",
        )
    )


AH_PREFIXES = ("ansible.", "redhat.")
AH_PUBLIC_EXCEPTIONS = {
    "ansible.posix",
    "ansible.utils",
    "ansible.netcommon",
}


def _check_ah_collections(ctx: ValidateContext, findings: list[Finding]) -> None:
    """Warn if collections likely require Automation Hub but AH_TOKEN is not set."""
    if os.environ.get("AH_TOKEN"):
        return

    collection_names = _extract_collection_names(ctx)
    if not collection_names:
        return

    ah_collections = [
        name for name in collection_names
        if name.startswith(AH_PREFIXES) and name not in AH_PUBLIC_EXCEPTIONS
    ]

    if ah_collections:
        names = ", ".join(sorted(ah_collections))
        findings.append(
            Finding(
                severity=Severity.WARNING,
                message=f"Collections that may require Automation Hub: {names}",
                fix="export AH_TOKEN=<offline-token> if these are on Automation Hub",
            )
        )


def _extract_collection_names(ctx: ValidateContext) -> list[str]:
    """Extract collection names from the galaxy dependency (file or inline)."""
    if ctx.ee.galaxy is None:
        return []

    if ctx.ee.galaxy.format == DepFormat.INLINE:
        names: list[str] = []
        for entry in ctx.ee.galaxy.entries:
            name = entry.get("name", "") if isinstance(entry, dict) else str(entry)
            if name:
                names.append(name)
        return names

    if (
        ctx.ee.galaxy.format == DepFormat.FILE
        and ctx.ee.galaxy.file_path
        and ctx.ee.galaxy.file_path.exists()
    ):
        try:
            data = yaml.safe_load(ctx.ee.galaxy.file_path.read_text())
        except yaml.YAMLError:
            return []
        if isinstance(data, dict):
            collections = data.get("collections", [])
            return [
                c["name"] if isinstance(c, dict) else str(c)
                for c in collections
                if (isinstance(c, dict) and "name" in c) or isinstance(c, str)
            ]

    return []
