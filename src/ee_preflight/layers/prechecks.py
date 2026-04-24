"""Layer 0: Pre-checks validation.

This module performs early sanity checks before running expensive operations:
- YAML linting with ansible-lint (optional)
- Dependency file existence checks
- Build argument validation
- Base image format validation

Errors in this layer (e.g., missing files) skip Layers 1-3.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess

from ..models import Finding, LayerResult, LayerStatus, Severity, ValidateContext


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
    _check_base_image(ctx, findings)

    has_missing_files = any(f.severity == Severity.ERROR and "not found" in f.message for f in findings)
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
    if not shutil.which("ansible-lint"):
        findings.append(
            Finding(
                severity=Severity.INFO,
                message="ansible-lint not found, skipping YAML format check",
                fix="pip install ansible-lint",
            )
        )
        return

    try:
        proc = subprocess.run(
            ["ansible-lint", str(ctx.ee.path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            for line in proc.stdout.splitlines():
                if ctx.ee.path.name in line and "]" in line:
                    findings.append(
                        Finding(
                            severity=Severity.WARNING,
                            message=f"ansible-lint: {line.strip()}",
                        )
                    )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass


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


def _check_base_image(ctx: ValidateContext, findings: list[Finding]) -> None:
    """Validate the base image format and presence.

    Checks that a base image is specified and matches expected format.
    Reports INFO if the image uses SHA digest pinning.

    Args:
        ctx: Validation context
        findings: List to append findings to
    """
    image = ctx.ee.base_image
    if not image:
        findings.append(
            Finding(
                severity=Severity.ERROR,
                message="No base image specified",
            )
        )
        return

    if not re.match(r"^[\w.\-]+(/[\w.\-]+)+(:\S+)?(@sha256:[a-f0-9]+)?$", image):
        findings.append(
            Finding(
                severity=Severity.WARNING,
                message=f"Base image may be malformed: {image}",
            )
        )

    if "@sha256:" in image:
        findings.append(
            Finding(
                severity=Severity.INFO,
                message="Base image uses SHA digest pin",
            )
        )
