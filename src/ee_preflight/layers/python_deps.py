"""Layer 2: Dependency validation via diff of discovered vs declared.

This module compares dependencies discovered by ade install against those
declared in the EE definition:
- Reads ade's discovered_requirements.txt and discovered_bindep.txt
- Diffs against declared Python and system deps
- Reports transitive Python deps as INFO
- Reports undeclared system deps as WARNING (with --fix support)
- Handles platform-specific bindep entries (rhel-8, rhel-9, etc.)

Uses ade's introspection output, not ansible-builder introspect.
"""

from __future__ import annotations

import re

from ..models import DepFormat, Finding, LayerResult, LayerStatus, Severity, ValidateContext, pkg_name

ADE_ENV_DIR = ".ansible-dev-environment"
DISCOVERED_PYTHON = "discovered_requirements.txt"
DISCOVERED_SYSTEM = "discovered_bindep.txt"


def validate(ctx: ValidateContext) -> LayerResult:
    """Run Layer 2 dependency validation.

    Reads ade's discovered dependencies and compares against declared deps
    in the EE definition. Reports transitive Python deps (INFO) and undeclared
    system deps (WARNING).

    Args:
        ctx: Validation context

    Returns:
        LayerResult with findings from dependency diff
    """
    findings: list[Finding] = []

    discovered_python = _read_discovered_python(ctx)
    discovered_system = _read_discovered_system(ctx)

    if not discovered_python and not discovered_system:
        findings.append(
            Finding(
                severity=Severity.INFO,
                message="No discovered dependencies found (ade may not have completed introspection)",
            )
        )
        return LayerResult(name="python_deps", status="pass", findings=findings)

    _diff_python_deps(ctx, discovered_python, findings)
    _diff_system_deps(ctx, discovered_system, findings)

    status: LayerStatus = "fail" if any(f.severity == Severity.ERROR for f in findings) else "pass"
    return LayerResult(name="python_deps", status=status, findings=findings)


def _read_discovered_python(ctx: ValidateContext) -> list[dict[str, str | None]]:
    """Read ade's discovered_requirements.txt.

    Parses ade's discovered Python deps with collection source attribution.

    Args:
        ctx: Validation context

    Returns:
        List of dicts with keys: dep (requirement spec), source (collection name or None)
    """
    path = ctx.venv_path / ADE_ENV_DIR / DISCOVERED_PYTHON
    if not path.exists():
        return []

    entries: list[dict[str, str | None]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        source = None
        if "# from collection" in line:
            parts = line.split("# from collection")
            line = parts[0].strip()
            source = parts[1].strip()
        entries.append({"dep": line, "source": source})
    return entries


def _read_discovered_system(ctx: ValidateContext) -> list[dict[str, str | list[str] | None]]:
    """Read ade's discovered_bindep.txt.

    Parses bindep entries with collection source and platform tags.

    Args:
        ctx: Validation context

    Returns:
        List of dicts with keys:
        - dep: Full bindep line (e.g., "pkg [platform:rhel-9]")
        - pkg_name: Package name
        - source: Collection name or None
        - platforms: List of platform tags (e.g., ["rhel-9"])
    """
    path = ctx.venv_path / ADE_ENV_DIR / DISCOVERED_SYSTEM
    if not path.exists():
        return []

    entries: list[dict[str, str | list[str] | None]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        source = None
        if "# from collection" in line:
            parts = line.split("# from collection")
            line = parts[0].strip()
            source = parts[1].strip()

        package_name = line.split()[0]
        platforms = re.findall(r"platform:(\S+)", line)
        entries.append(
            {
                "dep": line,
                "pkg_name": package_name,
                "source": source,
                "platforms": platforms,
            }
        )
    return entries


def _diff_python_deps(
    ctx: ValidateContext,
    discovered: list[dict[str, str | None]],
    findings: list[Finding],
) -> None:
    """Compare discovered Python deps against declared deps.

    Reports transitive dependencies (discovered but not declared) as INFO.
    These are not errors because pip resolves them automatically.

    Args:
        ctx: Validation context
        discovered: List of discovered Python deps from ade
        findings: List to append findings to
    """
    declared = _read_declared_python(ctx)
    declared_names = {pkg_name(d) for d in declared}

    seen: set[str] = set()
    for entry in discovered:
        name = pkg_name(str(entry["dep"]))
        if not name or name in declared_names or name in seen:
            continue
        seen.add(name)

        findings.append(
            Finding(
                severity=Severity.INFO,
                message=f"Transitive Python dep: {entry['dep']}",
                source=f"from collection {entry['source']}" if entry["source"] else None,
            )
        )


def _diff_system_deps(
    ctx: ValidateContext,
    discovered: list[dict[str, str | list[str] | None]],
    findings: list[Finding],
) -> None:
    """Compare discovered system deps against declared deps.

    Reports undeclared system (RPM/bindep) dependencies as WARNING with fix
    suggestions. Filters by platform tags to avoid false positives.

    Args:
        ctx: Validation context
        discovered: List of discovered system deps from ade
        findings: List to append findings to
    """
    declared = _read_declared_system(ctx)
    declared_names = {line.split()[0] for line in declared if line.strip()}

    target_platform = _detect_target_platform(ctx)

    seen: set[str] = set()
    for entry in discovered:
        package_name = str(entry["pkg_name"])
        platforms = entry["platforms"]

        if package_name in declared_names or package_name in seen:
            continue

        # Skip if platform tags don't match the target platform
        if platforms and not _matches_platform(list(platforms), target_platform):
            continue

        seen.add(package_name)

        findings.append(
            Finding(
                severity=Severity.WARNING,
                message=f"Undeclared system dep: {package_name}",
                fix=f"Add '{entry['dep']}' to bindep.txt",
                source=f"from collection {entry['source']}" if entry["source"] else None,
            )
        )


def _detect_target_platform(ctx: ValidateContext) -> str:
    """Infer the target platform from the base image name.

    Platform detection is used to filter platform-specific bindep entries.
    Falls back to "rpm" if no specific platform is detected.

    Args:
        ctx: Validation context

    Returns:
        Platform identifier (rhel-9, rhel-8, centos-9, centos-8, fedora, debian, or rpm)
    """
    image = ctx.ee.base_image.lower()
    if "rhel-9" in image or "rhel9" in image:
        return "rhel-9"
    if "rhel-8" in image or "rhel8" in image:
        return "rhel-8"
    if "centos-9" in image or "centos9" in image:
        return "centos-9"
    if "centos-8" in image or "centos8" in image:
        return "centos-8"
    if "fedora" in image:
        return "fedora"
    if "debian" in image or "ubuntu" in image:
        return "debian"
    return "rpm"


def _matches_platform(platforms: list[str], target: str) -> bool:
    """Check if any of the bindep platform tags match our target.

    Handles platform aliases:
    - "rpm" matches rhel-*, centos-*, fedora
    - "redhat" matches rhel-*, centos-*
    - "dpkg" matches debian, ubuntu

    Args:
        platforms: List of platform tags from bindep entry
        target: Detected target platform

    Returns:
        True if any platform tag matches the target
    """
    for p in platforms:
        if p == target:
            return True
        if p == "rpm" and target in ("rhel-8", "rhel-9", "centos-8", "centos-9", "fedora"):
            return True
        if p == "redhat" and target in ("rhel-8", "rhel-9", "centos-8", "centos-9"):
            return True
        if p == "dpkg" and target in ("debian", "ubuntu"):
            return True
    return False


def read_declared_python(ctx: ValidateContext) -> list[str]:
    """Read declared Python dependencies from the EE definition.

    Public wrapper around _read_declared_python for use by other modules.

    Args:
        ctx: Validation context

    Returns:
        List of declared Python requirement specs
    """
    return _read_declared_python(ctx)


def read_declared_system(ctx: ValidateContext) -> list[str]:
    """Read declared system dependencies from the EE definition.

    Public wrapper around _read_declared_system for use by other modules.

    Args:
        ctx: Validation context

    Returns:
        List of declared bindep entries
    """
    return _read_declared_system(ctx)


def _read_declared_python(ctx: ValidateContext) -> list[str]:
    """Read declared Python dependencies from the EE definition."""
    if ctx.ee.python is None:
        return []
    if ctx.ee.python.format == DepFormat.FILE and ctx.ee.python.file_path and ctx.ee.python.file_path.exists():
        return [
            line.strip()
            for line in ctx.ee.python.file_path.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
    if ctx.ee.python.format == DepFormat.INLINE:
        return [str(e) for e in ctx.ee.python.entries]
    return []


def _read_declared_system(ctx: ValidateContext) -> list[str]:
    """Read declared system (bindep) dependencies from the EE definition."""
    if ctx.ee.system is None:
        return []
    if ctx.ee.system.format == DepFormat.FILE and ctx.ee.system.file_path and ctx.ee.system.file_path.exists():
        return [
            line.strip()
            for line in ctx.ee.system.file_path.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
    if ctx.ee.system.format == DepFormat.INLINE:
        return [str(e) for e in ctx.ee.system.entries]
    return []
