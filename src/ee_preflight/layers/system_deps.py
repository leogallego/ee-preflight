"""Layer 3: Container wheel test for source-only Python packages.

This module tests whether source-only Python packages (systemd-python, gssapi,
lxml, etc.) can build wheels inside the target container. It:
- Pulls the base image and detects Python version
- Identifies source-only packages from discovered deps
- Tests wheel builds inside the container with declared bindep deps installed
- Extracts missing headers/libraries from build errors
- Uses dnf/apt-file to find providing packages
- Retries failed builds cumulatively as new deps are discovered

All RPM resolution happens inside the container, not on the host.
"""

from __future__ import annotations

import re

from ..cache import DependencyCache
from ..container import ContainerRuntime
from ..models import Finding, LayerResult, Severity, ValidateContext

# Patterns for extracting missing files/dependencies from wheel build errors
MISSING_FILE_PATTERNS = [
    (r"fatal error: (\S+\.h): No such file or directory", "header"),
    (r"(\S+): command not found", "command"),
    (r"Package '(\S+)' not found", "pkgconfig"),
    (r"Package (\S+) was not found in the pkg-config search path", "pkgconfig"),
    (r"Cannot find (\S+)", "library"),
    (r"(libxml2|libxslt) development packages are", "devpkg"),
    (r"Failed to build '(\S+)'", "wheel"),
]


def validate(ctx: ValidateContext, extra_packages: set[str] | None = None) -> LayerResult:
    """Run Layer 3 container wheel test.

    Tests wheel builds for source-only Python packages inside the target container.
    Uses cumulative retry: when a package fails, extracts the missing dependency,
    adds it to the discovered set, and retries all failed packages with the expanded
    dep set. Repeats up to 3 times or until no new deps are discovered.

    Args:
        ctx: Validation context
        extra_packages: Additional packages to test (from Layer 1 build failures)

    Returns:
        LayerResult with findings from wheel build tests
    """
    if not ctx.container_test:
        return LayerResult(name="system_deps", status="skipped", findings=[])

    findings: list[Finding] = []

    try:
        runtime = ContainerRuntime(ctx.runtime)
    except RuntimeError as e:
        findings.append(Finding(severity=Severity.ERROR, message=str(e)))
        return LayerResult(name="system_deps", status="fail", findings=findings)

    # Initialize cache
    cache = None
    if ctx.use_cache:
        cache = DependencyCache(cache_path=ctx.cache_path)

    image = ctx.ee.base_image
    findings.append(
        Finding(
            severity=Severity.INFO,
            message=f"Pulling base image: {image}",
        )
    )

    pull_result = runtime.pull(image)
    if pull_result.returncode != 0:
        findings.append(
            Finding(
                severity=Severity.ERROR,
                message=f"Failed to pull base image: {pull_result.stderr.strip()}",
            )
        )
        return LayerResult(name="system_deps", status="fail", findings=findings)

    python_version = _detect_python_version(runtime, image)

    discovered_python = _get_discovered_python(ctx)
    source_pkgs = _find_source_only_packages(discovered_python)

    if extra_packages:
        seen = {p.lower().replace("-", "_") for p in source_pkgs}
        for pkg in extra_packages:
            normalized = pkg.lower().replace("-", "_")
            if normalized not in seen:
                source_pkgs.append(pkg)
                seen.add(normalized)

    if not source_pkgs:
        findings.append(
            Finding(
                severity=Severity.INFO,
                message="No source-only packages to test",
            )
        )
        return LayerResult(name="system_deps", status="pass", findings=findings)

    bindep_install = _get_bindep_install_cmd(ctx)

    # Track discovered RPMs and failed packages across retries
    discovered_rpms: set[str] = set()
    all_pkg_findings: list[Finding] = []
    failed_pkgs: set[str] = set()

    # Initial pass: test all source-only packages
    for pkg in source_pkgs:
        pkg_result, rpm = _test_wheel_build(
            ctx,
            runtime,
            image,
            pkg,
            bindep_install,
            python_version,
            cache=cache,
        )
        all_pkg_findings.extend(pkg_result)
        if rpm:
            discovered_rpms.add(rpm)
            failed_pkgs.add(pkg)
        elif any(f.severity == Severity.ERROR for f in pkg_result):
            failed_pkgs.add(pkg)

    # Cumulative retry: retry failed packages with expanded dep set.
    # Stop when no new deps are discovered or max retries reached.
    max_retries = 3
    for _attempt in range(max_retries):
        if not failed_pkgs or not discovered_rpms:
            break

        prev_count = len(discovered_rpms)
        all_pkg_findings.append(
            Finding(
                severity=Severity.INFO,
                message=(
                    f"Retrying {len(failed_pkgs)} failed package(s) with "
                    f"discovered deps: {', '.join(sorted(discovered_rpms))}"
                ),
            )
        )

        still_failing: set[str] = set()
        for pkg in list(failed_pkgs):
            pkg_result, rpm = _test_wheel_build(
                ctx,
                runtime,
                image,
                pkg,
                bindep_install,
                python_version,
                extra_rpms=discovered_rpms,
                cache=cache,
            )
            all_pkg_findings.extend(pkg_result)
            if rpm:
                discovered_rpms.add(rpm)
                still_failing.add(pkg)
            elif any(f.severity == Severity.ERROR for f in pkg_result):
                still_failing.add(pkg)

        failed_pkgs = still_failing
        # Stop retrying if no new deps were discovered this round
        if len(discovered_rpms) == prev_count:
            break

    findings.extend(all_pkg_findings)

    status = "fail" if any(f.severity == Severity.ERROR for f in findings) else "pass"
    return LayerResult(name="system_deps", status=status, findings=findings)


def _detect_python_version(runtime: ContainerRuntime, image: str) -> str:
    """Detect Python version inside the container.

    Used to construct python3.x-devel package names for the target image.

    Args:
        runtime: Container runtime
        image: Container image name

    Returns:
        Python version string (e.g., "3.11" or "3" if detection fails)
    """
    result = runtime.run(
        image,
        "python3 -c 'import sys; print(f\"{sys.version_info.major}.{sys.version_info.minor}\")'",
    )
    if result.returncode == 0:
        return str(result.stdout.strip())
    return "3"


def _get_discovered_python(ctx: ValidateContext) -> list[str]:
    """Read Python deps from ade's discovered_requirements.txt.

    Args:
        ctx: Validation context

    Returns:
        List of Python requirement specs
    """
    path = ctx.venv_path / ".ansible-dev-environment" / "discovered_requirements.txt"
    if not path.exists():
        return []
    deps: list[str] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        dep = line.split("#")[0].strip()
        if dep:
            deps.append(dep)
    return deps


def _find_source_only_packages(python_deps: list[str]) -> list[str]:
    """Identify source-only Python packages from discovered deps.

    Source-only packages typically require system libraries/headers to build
    wheels (e.g., systemd-python needs systemd-devel).

    Also checks for extras that pull in source-only deps (e.g., aiokafka[gssapi]).

    Args:
        python_deps: List of discovered Python requirement specs

    Returns:
        List of package names that are source-only
    """
    known_source_only = {
        "systemd_python",
        "gssapi",
        "ncclient",
        "lxml",
        "ovirt_engine_sdk_python",
        "python_ldap",
        "pynacl",
    }
    # Extras that pull in source-only deps (e.g., aiokafka[gssapi] → gssapi)
    extras_mapping = {
        "gssapi": "gssapi",
    }

    source_pkgs: list[str] = []
    seen: set[str] = set()
    for dep in python_deps:
        # Check the package name itself
        name = dep.split(">=")[0].split("==")[0].split("<")[0].split("[")[0].split(";")[0].strip()
        normalized = name.lower().replace("-", "_")
        if normalized in known_source_only and normalized not in seen:
            seen.add(normalized)
            source_pkgs.append(name)
            continue

        # Check if extras pull in source-only deps
        if "[" in dep:
            extras = dep.split("[")[1].split("]")[0].split(",")
            for extra in extras:
                extra = extra.strip().lower()
                if extra in extras_mapping and extras_mapping[extra] not in seen:
                    seen.add(extras_mapping[extra])
                    source_pkgs.append(extras_mapping[extra])

    return source_pkgs


def _get_bindep_install_cmd(ctx: ValidateContext) -> str:
    """Build command to install declared bindep packages.

    Constructs a package manager install command from the declared system deps.
    Returns "true" if no system deps are declared.

    Args:
        ctx: Validation context

    Returns:
        Shell command to install declared bindep packages
    """
    from .python_deps import read_declared_system

    declared = read_declared_system(ctx)
    pkg_names = [line.split()[0] for line in declared if line.strip()]
    if pkg_names:
        pkgmgr = ctx.ee.options.get("package_manager_path", "/usr/bin/microdnf")
        return f"{pkgmgr} install -y {' '.join(pkg_names)}"
    return "true"


def _test_wheel_build(
    ctx: ValidateContext,
    runtime: ContainerRuntime,
    image: str,
    pkg: str,
    bindep_install: str,
    python_version: str,
    extra_rpms: set[str] | None = None,
    cache: DependencyCache | None = None,
) -> tuple[list[Finding], str | None]:
    """Test wheel build for a single package inside the container.

    Runs pip wheel --no-binary to force source build. If the build fails,
    extracts the missing file/library and uses dnf/apt-file to find the
    providing package.

    Args:
        ctx: Validation context
        runtime: Container runtime
        image: Container image name
        pkg: Python package spec to test
        bindep_install: Command to install declared bindep packages
        python_version: Python version string (e.g., "3.11")
        extra_rpms: Additional RPMs to install (from previous retries)

    Returns:
        Tuple of (findings, providing_package):
        - findings: List of findings from this wheel build test
        - providing_package: RPM that provides the missing dependency, or None
    """
    pkg_name = pkg.split(">=")[0].split("==")[0].split("<")[0].strip()
    pkgmgr = ctx.ee.options.get("package_manager_path", "/usr/bin/microdnf")
    pycmd = f"python{python_version}"

    rpm_install = bindep_install
    if extra_rpms:
        rpm_install += f" && {pkgmgr} install -y {' '.join(sorted(extra_rpms))} 2>/dev/null; true"

    cmd = (
        f"{rpm_install} && "
        f"{pkgmgr} install -y python3-pip python3-devel gcc 2>/dev/null; "
        f"{pycmd} -m ensurepip 2>/dev/null; "
        f"{pycmd} -m pip install --upgrade pip setuptools wheel && "
        f"{pycmd} -m pip wheel --no-binary :all: '{pkg}' -w /tmp/wheels"
    )

    result = runtime.run(image, cmd, timeout=180)
    findings: list[Finding] = []

    if result.returncode == 0:
        findings.append(
            Finding(
                severity=Severity.INFO,
                message=f"Wheel build OK: {pkg_name}",
            )
        )
        return findings, None

    output = result.stdout + result.stderr
    missing_file = _extract_missing_file(output)

    if missing_file:
        pkg_provider = _find_providing_package(
            runtime, image, missing_file, python_version, pkg_name=pkg_name, cache=cache
        )
        if pkg_provider:
            findings.append(
                Finding(
                    severity=Severity.ERROR,
                    message=f"{pkg_name} failed to build: {missing_file} not found",
                    fix=f"Add '{pkg_provider}' to bindep.txt",
                    source=f"required by {pkg_name}",
                )
            )
            return findings, pkg_provider
        else:
            findings.append(
                Finding(
                    severity=Severity.ERROR,
                    message=f"{pkg_name} failed to build: {missing_file} not found",
                    fix=f"Find the package providing {missing_file} for your base image and add it to bindep.txt",
                    source=f"required by {pkg_name}",
                )
            )
            return findings, None
    else:
        findings.append(
            Finding(
                severity=Severity.ERROR,
                message=f"{pkg_name} failed to build",
                source=f"pip wheel output: {output[-300:]}",
            )
        )
        return findings, None


def _extract_missing_file(output: str) -> str | None:
    """Extract missing file/library name from wheel build error output.

    Scans for common error patterns (missing headers, pkg-config libs, commands).

    Args:
        output: Combined stdout/stderr from pip wheel

    Returns:
        Missing file/library name, or None if no pattern matches
    """
    for pattern, _ in MISSING_FILE_PATTERNS:
        match = re.search(pattern, output)
        if match:
            return match.group(1)
    return None


def _find_providing_package(
    runtime: ContainerRuntime,
    image: str,
    missing_file: str,
    python_version: str,
    pkg_name: str = "",
    cache: DependencyCache | None = None,
) -> str | None:
    """Find which RPM/DEB package provides the missing file.

    Uses dnf provides (RPM-based) or apt-file (Debian-based) inside the container.
    Prefers -devel packages for header/pkg-config lookups.

    Args:
        runtime: Container runtime
        image: Container image name
        missing_file: Missing file/library name
        python_version: Python version string

    Returns:
        Package name that provides the missing file, or None if not found
    """
    # Special case: Python.h is always in python3.x-devel
    if missing_file == "Python.h":
        return f"python{python_version}-devel"

    # Detect platform (rpm vs dpkg)
    platform = "rpm"  # default
    if "debian" in image.lower() or "ubuntu" in image.lower():
        platform = "dpkg"

    # Check cache first
    if cache:
        cached = cache.get(
            base_image=image,
            python_package=pkg_name,
            missing_file=missing_file,
            platform=platform,
            python_version=python_version,
        )
        if cached is not None:
            return cached

    # Cache miss - run container resolution
    resolved_rpm: str | None = None

    # Try dnf provides inside the container (install dnf if needed)
    search = f"*/pkgconfig/{missing_file}.pc" if "." not in missing_file else f"*/{missing_file}"
    result = runtime.run(
        image,
        f"(microdnf install -y dnf 2>/dev/null || true) && dnf provides '{search}' 2>/dev/null",
        timeout=120,
    )
    if result.returncode == 0 and result.stdout.strip():
        candidates: list[str] = []
        for line in result.stdout.splitlines():
            line = line.strip()
            skip_prefixes = ("Last", "=", "Repo", "Matched", "Filename", "Provide")
            if not line or any(line.startswith(p) for p in skip_prefixes):
                continue
            match = re.match(r"^(\S+?)-\d", line)
            if match:
                candidates.append(match.group(1))
        # Prefer -devel packages for header/pkgconfig lookups
        for c in candidates:
            if c.endswith("-devel"):
                resolved_rpm = c
                break
        if not resolved_rpm and candidates:
            resolved_rpm = candidates[0]

    # Try apt-file for Debian-based containers
    if not resolved_rpm:
        result = runtime.run(
            image,
            f"apt-file search '{missing_file}' 2>/dev/null | head -1",
            timeout=60,
        )
        if result.returncode == 0 and result.stdout.strip():
            pkg = str(result.stdout.strip().split(":")[0])
            if pkg:
                resolved_rpm = pkg

    # Cache the result (even if None, to avoid retrying failed lookups)
    if cache:
        cache.set(
            base_image=image,
            python_package=pkg_name,
            missing_file=missing_file,
            resolved_rpm=resolved_rpm,
            platform=platform,
            python_version=python_version,
        )

    return resolved_rpm
