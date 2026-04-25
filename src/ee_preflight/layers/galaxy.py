"""Layer 1: Galaxy resolution via ade install.

This module uses `ade install` to:
- Resolve and install Ansible collections
- Detect collection conflicts and authentication errors
- Identify Python build failures during collection installation
- Retry transient errors with exponential backoff

Python build failures are separated and attached to Layer 2 results,
while collection resolution errors fail Layer 1.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml

from ..models import DepFormat, Finding, LayerResult, Severity, ValidateContext
from .system_deps import MISSING_FILE_PATTERNS

GALAXY_API = "https://galaxy.ansible.com/api/v3/collections"
AH_API = "https://console.redhat.com/api/automation-hub/v3/collections"
AH_SSO_URL = "https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token"

# Network errors that should trigger retry with backoff
TRANSIENT_PATTERNS = [
    "HTTP Error 504",
    "HTTP Error 502",
    "HTTP Error 429",
    "Connection timed out",
    "Connection refused",
    "Gateway Time-out",
]

# Patterns indicating Python package build failures during ade install
PYTHON_BUILD_PATTERNS = [
    "No module named",
    "command not found",
    "No such file or directory",
    "Failed building wheel",
    "Failed to build",
    "pkg-config search path",
    "Cannot find",
]

MAX_RETRIES = 3
BACKOFF_SECONDS = [5, 15, 45]  # Exponential backoff for transient errors


def validate(ctx: ValidateContext) -> tuple[LayerResult, list[Finding], set[str]]:
    """Run Layer 1 galaxy resolution via ade install.

    Runs `ade install` with retry logic for transient errors. Separates
    collection resolution errors from Python build failures.

    Args:
        ctx: Validation context

    Returns:
        Tuple of (layer1_result, python_build_findings, failed_pkgs):
        - layer1_result: LayerResult for galaxy resolution
        - python_build_findings: List of Python build error findings (attached to Layer 2)
        - failed_pkgs: Set of Python package names that failed to build
    """
    findings: list[Finding] = []

    reqs_path = _get_requirements_path(ctx, findings)
    if reqs_path is None:
        return LayerResult(name="galaxy", status="fail", findings=findings), [], set()

    not_found = _probe_collections(ctx, findings)
    if not_found:
        return LayerResult(name="galaxy", status="fail", findings=findings), [], set()

    env = _build_env(ctx)

    for attempt in range(MAX_RETRIES):
        try:
            proc = subprocess.run(
                [
                    "ade",
                    "install",
                    "-r",
                    str(reqs_path),
                    "--venv",
                    str(ctx.venv_path),
                    "--im",
                    "none",
                    "-v",
                ],
                capture_output=True,
                text=True,
                env=env,
                timeout=600,
            )
        except subprocess.TimeoutExpired:
            findings.append(
                Finding(
                    severity=Severity.ERROR,
                    message="Galaxy resolution timed out after 600s",
                )
            )
            return LayerResult(name="galaxy", status="fail", findings=findings), [], set()

        output = proc.stdout + proc.stderr
        collections_installed = "Installed collections include:" in output

        if proc.returncode == 0 or collections_installed:
            installed = _count_collections(output)
            if proc.returncode != 0:
                python_build_findings, failed_pkgs = _parse_python_build_errors(output)
            else:
                python_build_findings, failed_pkgs = [], set()

            findings.append(
                Finding(
                    severity=Severity.INFO,
                    message=f"{installed} collections resolved and installed",
                )
            )

            if python_build_findings:
                return (
                    LayerResult(name="galaxy", status="pass", findings=findings),
                    python_build_findings,
                    failed_pkgs,
                )
            return LayerResult(name="galaxy", status="pass", findings=findings), [], set()

        if _is_transient(output) and attempt < MAX_RETRIES - 1:
            wait = BACKOFF_SECONDS[attempt]
            findings.append(
                Finding(
                    severity=Severity.INFO,
                    message=f"Transient error, retrying in {wait}s (attempt {attempt + 1}/{MAX_RETRIES})",
                )
            )
            time.sleep(wait)
            continue

        # Separate collection errors from Python build failures
        collection_findings = _parse_collection_errors(output)
        python_build_findings, failed_pkgs = _parse_python_build_errors(output)

        if collection_findings:
            findings.extend(collection_findings)
            return LayerResult(name="galaxy", status="fail", findings=findings), [], set()

        if python_build_findings:
            installed = _count_collections(output)
            findings.append(
                Finding(
                    severity=Severity.INFO,
                    message=f"{installed} collections resolved (Python dep build issues detected)",
                )
            )
            return (
                LayerResult(name="galaxy", status="pass", findings=findings),
                python_build_findings,
                failed_pkgs,
            )

        # Unknown failure
        last_lines = output.strip().splitlines()[-5:]
        findings.append(
            Finding(
                severity=Severity.ERROR,
                message="Galaxy resolution failed: " + " | ".join(line.strip() for line in last_lines if line.strip()),
            )
        )
        return LayerResult(name="galaxy", status="fail", findings=findings), [], set()

    return LayerResult(name="galaxy", status="fail", findings=findings), [], set()


def _probe_collections(ctx: ValidateContext, findings: list[Finding]) -> list[str]:
    """Probe Galaxy and Automation Hub APIs to verify collections exist.

    Checks each collection against public Galaxy. If AH_TOKEN is set,
    also checks Automation Hub for collections not found on Galaxy.

    Returns list of collection names not found on any server.
    """
    from .prechecks import _extract_collection_names

    collection_names = _extract_collection_names(ctx)
    if not collection_names:
        return []

    ah_token = os.environ.get("AH_TOKEN")
    ah_access_token = _get_ah_access_token(ah_token) if ah_token else None

    not_found: list[str] = []
    found_on_galaxy: list[str] = []
    found_on_ah: list[str] = []

    for name in collection_names:
        parts = name.split(".")
        if len(parts) < 2:
            continue
        namespace, col_name = parts[0], ".".join(parts[1:])

        on_galaxy = _check_galaxy(namespace, col_name)
        if on_galaxy:
            found_on_galaxy.append(name)
            continue

        if ah_access_token:
            on_ah = _check_ah(namespace, col_name, ah_access_token)
            if on_ah:
                found_on_ah.append(name)
                continue

        not_found.append(name)

    if found_on_galaxy:
        findings.append(
            Finding(
                severity=Severity.INFO,
                message=f"{len(found_on_galaxy)} collection(s) found on public Galaxy",
            )
        )

    if found_on_ah:
        findings.append(
            Finding(
                severity=Severity.INFO,
                message=(
                    f"{len(found_on_ah)} collection(s) found on Automation Hub: "
                    f"{', '.join(found_on_ah)}"
                ),
            )
        )

    for name in not_found:
        servers = "Galaxy or Automation Hub" if ah_access_token else "public Galaxy"
        findings.append(
            Finding(
                severity=Severity.ERROR,
                message=f"Collection '{name}' not found on {servers}",
                fix=(
                    "Check the collection namespace/name for typos"
                    if ah_access_token
                    else f"Set AH_TOKEN if '{name}' is on Automation Hub"
                ),
                code="collection_not_found",
            )
        )

    return not_found


def _get_ah_access_token(offline_token: str) -> str | None:
    """Exchange an AH offline token for a short-lived access token via Red Hat SSO."""
    data = (
        f"grant_type=refresh_token&client_id=cloud-services"
        f"&refresh_token={offline_token}"
    ).encode()
    req = urllib.request.Request(AH_SSO_URL, data=data)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result: str | None = json.loads(resp.read()).get("access_token")
            return result
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return None


def _check_galaxy(namespace: str, name: str) -> bool:
    """Check if a collection exists on public Galaxy. Returns True if found."""
    url = f"{GALAXY_API}/{namespace}/{name}/"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return bool(resp.status == 200)
    except urllib.error.HTTPError:
        return False
    except (urllib.error.URLError, TimeoutError):
        return True  # network error — assume exists, let ade install verify


def _check_ah(namespace: str, name: str, access_token: str) -> bool:
    """Check if a collection exists on Automation Hub. Returns True if found."""
    url = f"{AH_API}/{namespace}/{name}/"
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {access_token}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return bool(resp.status == 200)
    except urllib.error.HTTPError:
        return False
    except (urllib.error.URLError, TimeoutError):
        return True  # network error — assume exists


def _get_requirements_path(ctx: ValidateContext, findings: list[Finding]) -> Path | None:
    """Get path to galaxy requirements file for ade install.

    If galaxy deps are inline, creates a temporary requirements.yml.

    Args:
        ctx: Validation context
        findings: List to append findings to

    Returns:
        Path to requirements file, or None if no galaxy deps are defined
    """
    if ctx.ee.galaxy is None:
        findings.append(
            Finding(
                severity=Severity.ERROR,
                message="No galaxy dependencies defined",
            )
        )
        return None

    if ctx.ee.galaxy.format == DepFormat.FILE:
        return ctx.ee.galaxy.file_path

    # Create temp file for inline deps
    tmp_dir = Path("tmp")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp = tmp_dir / "inline-requirements.yml"
    with open(tmp, "w") as f:
        yaml.dump({"collections": ctx.ee.galaxy.entries}, f)
    return tmp


def _build_env(ctx: ValidateContext) -> dict[str, str]:
    """Build environment dict for ade install.

    Configures Automation Hub authentication if AH_TOKEN is set.
    Sets UV_CACHE_DIR to tmp/ to avoid read-only filesystem issues.

    Args:
        ctx: Validation context

    Returns:
        Environment dict for subprocess
    """
    env = os.environ.copy()
    env.pop("ANSIBLE_CONFIG", None)
    # Keep uv cache local to avoid read-only filesystem issues in sandboxed environments
    env.setdefault("UV_CACHE_DIR", str(Path("tmp").resolve() / "uv-cache"))
    ah_token = os.environ.get("AH_TOKEN")
    if ah_token:
        env["ANSIBLE_GALAXY_SERVER_LIST"] = "automation_hub_certified,automation_hub_validated,release_galaxy"
        env["ANSIBLE_GALAXY_SERVER_AUTOMATION_HUB_CERTIFIED_URL"] = (
            "https://console.redhat.com/api/automation-hub/content/published/"
        )
        env["ANSIBLE_GALAXY_SERVER_AUTOMATION_HUB_CERTIFIED_AUTH_URL"] = (
            "https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token"
        )
        env["ANSIBLE_GALAXY_SERVER_AUTOMATION_HUB_CERTIFIED_TOKEN"] = ah_token
        env["ANSIBLE_GALAXY_SERVER_AUTOMATION_HUB_VALIDATED_URL"] = (
            "https://console.redhat.com/api/automation-hub/content/validated/"
        )
        env["ANSIBLE_GALAXY_SERVER_AUTOMATION_HUB_VALIDATED_AUTH_URL"] = (
            "https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token"
        )
        env["ANSIBLE_GALAXY_SERVER_AUTOMATION_HUB_VALIDATED_TOKEN"] = ah_token
        env["ANSIBLE_GALAXY_SERVER_RELEASE_GALAXY_URL"] = "https://galaxy.ansible.com/"

    return env


def _is_transient(output: str) -> bool:
    """Check if error output indicates a transient network issue.

    Args:
        output: Combined stdout/stderr from ade install

    Returns:
        True if output contains transient error patterns
    """
    return any(p in output for p in TRANSIENT_PATTERNS)


def _count_collections(output: str) -> int:
    """Count how many collections were installed.

    Args:
        output: Combined stdout/stderr from ade install

    Returns:
        Number of collections installed
    """
    count = output.count("was installed successfully")
    if count == 0:
        count = output.count("Installing ")
    return count


def _parse_collection_errors(output: str) -> list[Finding]:
    """Extract collection resolution errors from ade install output.

    Looks for version conflicts and authentication failures.

    Args:
        output: Combined stdout/stderr from ade install

    Returns:
        List of ERROR findings for collection issues
    """
    findings: list[Finding] = []

    if "Could not satisfy" in output or "Failed to resolve" in output:
        lines = output.splitlines()
        hint = ""
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("Hint:"):
                # Trim the noisy RequirementInformation repr from the hint
                hint_text = stripped
                req_idx = hint_text.find(": [RequirementInformation")
                if req_idx > 0:
                    hint_text = hint_text[:req_idx]
                hint = hint_text
                break

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("*"):
                detail = stripped[2:]
                is_not_found = "direct request" in detail and "dependency of" not in detail
                if is_not_found:
                    col_name = detail.split(":")[0] if ":" in detail else detail
                    needs_ah = col_name.startswith(("ansible.", "redhat."))
                    if needs_ah and not os.environ.get("AH_TOKEN"):
                        fix = (
                            f"'{col_name}' is on Automation Hub, not public Galaxy. "
                            f"Set AH_TOKEN to authenticate."
                        )
                    elif hint:
                        fix = hint
                    else:
                        fix = None
                    findings.append(
                        Finding(
                            severity=Severity.ERROR,
                            message=f"Collection not found: {detail}",
                            fix=fix,
                            code="collection_not_found",
                        )
                    )
                else:
                    findings.append(
                        Finding(
                            severity=Severity.ERROR,
                            message=f"Collection conflict: {detail}",
                            code="collection_conflict",
                        )
                    )

    if any(p in output for p in ("HTTP Error 400", "Unauthorized", "HTTP Error 401")):
        findings.append(
            Finding(
                severity=Severity.ERROR,
                message="Galaxy/Automation Hub authentication failed",
                fix="Check AH_TOKEN or ansible.cfg credentials",
                code="auth_failure",
            )
        )

    return findings


def _parse_python_build_errors(output: str) -> tuple[list[Finding], set[str]]:
    """Extract Python package build failures from ade install output.

    Detects missing headers, libraries, and commands that prevent wheels
    from building. These are separated from collection errors and attached
    to Layer 2 results.

    Args:
        output: Combined stdout/stderr from ade install

    Returns:
        Tuple of (findings, failed_pkgs):
        - findings: List of WARNING findings for Python build issues
        - failed_pkgs: Set of package names that failed to build
    """
    findings: list[Finding] = []

    if not any(p in output for p in PYTHON_BUILD_PATTERNS):
        return findings, set()

    # Extract which packages failed to build
    failed_pkgs: set[str] = set()
    for pattern in [
        r"Failed to build '(\S+)'",
        r"Failed building wheel for (\S+)",
        r"Failed to build installable wheels.*?╰─> (\S+)",
        r"error: subprocess-exited-with-error.*?Getting requirements.*?for (\S+)",
    ]:
        for match in re.finditer(pattern, output):
            failed_pkgs.add(match.group(1).lower().replace("-", "_"))

    seen: set[str] = set()
    for pattern, kind in MISSING_FILE_PATTERNS:
        for match in re.finditer(pattern, output):
            missing = match.group(1)
            if missing in seen:
                continue
            seen.add(missing)
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    message=f"Python dep build failed: {missing} not found ({kind})",
                    fix="Layer 3 container test will resolve the exact package",
                    source=(
                        f"failed packages: {', '.join(sorted(failed_pkgs))}"
                        if failed_pkgs
                        else "detected during ade install"
                    ),
                )
            )

    if not findings and failed_pkgs:
        for pkg in sorted(failed_pkgs):
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    message=f"Python dep failed to build: {pkg}",
                    fix="Layer 3 container test will resolve the exact package",
                    source="detected during ade install",
                )
            )

    return findings, failed_pkgs
