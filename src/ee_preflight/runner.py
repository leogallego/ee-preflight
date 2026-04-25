"""Validation orchestration and venv lifecycle management.

This module is the main orchestrator for ee-preflight. It:
- Creates and manages the temporary venv for ade install
- Executes the 4 validation layers in sequence
- Handles layer dependencies (skipping downstream layers on errors)
- Applies fixes via --fix
- Re-validates cheap layers after fixes are applied
- Optionally runs ansible-builder after successful validation
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Literal

from .ee_parser import parse_ee
from .fixer import apply_fixes, apply_layer0_fixes, backup_ee_files
from .layers import galaxy, prechecks, python_deps, system_deps
from .models import EEDefinition, Finding, LayerResult, Severity, ValidateContext


def run(
    ee_path: Path,
    fix: bool = False,
    build: bool = False,
    tag: str | None = None,
    venv_path: Path | None = None,
    keep_venv: bool = False,
    container_test: bool = False,
    runtime: Literal["podman", "docker"] | None = None,
    verbose: bool = False,
    use_cache: bool = True,
    cache_path: Path | None = None,
) -> list[LayerResult]:
    """Run all validation layers against an execution environment definition.

    Executes up to 4 validation layers in sequence:
    - Layer 0: Pre-checks (YAML lint, file refs, build args)
    - Layer 1: Galaxy resolution (ade install)
    - Layer 2: Dependency validation (diff discovered vs declared)
    - Layer 3: Container wheel test (optional, tests source-only Python packages)

    If Layer 0 finds missing files, Layers 1-3 are skipped.
    If Layer 1 fails, Layers 2-3 are skipped.

    Args:
        ee_path: Path to execution-environment.yml
        fix: Apply auto-fixes to EE files when possible
        build: Run ansible-builder after successful validation
        tag: Image tag for --build (default: <ee_dir_name>:latest)
        venv_path: Custom venv path (if None, creates temp venv in tmp/)
        keep_venv: Keep temp venv after run (only applies to auto-created venvs)
        container_test: Force Layer 3 container wheel test
        verbose: Show INFO-level findings in output

    Returns:
        List of LayerResult objects, one per layer executed
    """
    ee = parse_ee(ee_path)
    user_venv = venv_path is not None

    if venv_path is None:
        path_hash = hashlib.md5(str(ee_path).encode()).hexdigest()[:8]
        venv_path = Path("tmp").resolve() / f"ee-preflight-{path_hash}"
    else:
        venv_path = venv_path.resolve()

    venv_path.parent.mkdir(parents=True, exist_ok=True)

    ctx = ValidateContext(
        ee=ee,
        venv_path=venv_path,
        fix=fix,
        container_test=container_test,
        runtime=runtime,
        verbose=verbose,
        use_cache=use_cache,
        cache_path=cache_path,
    )

    results: list[LayerResult] = []

    if fix:
        backups = backup_ee_files(ee)
        if backups:
            results.append(
                LayerResult(
                    name="fix",
                    status="pass",
                    findings=[
                        Finding(
                            severity=Severity.INFO,
                            message=f"Backed up {len(backups)} file(s) before applying fixes",
                        )
                    ],
                )
            )

    try:
        # Layer 0: Pre-checks
        r0 = prechecks.validate(ctx)

        has_l0_fixable = any(
            f.code in ("missing_file", "stray_collections") for f in r0.findings
        )
        if fix and has_l0_fixable:
            l0_findings = [
                f for f in r0.findings
                if f.code in ("missing_file", "stray_collections")
            ]
            l0_changes = apply_layer0_fixes(ee, l0_findings)
            if l0_changes:
                for change in l0_changes:
                    results.append(
                        LayerResult(
                            name="fix",
                            status="pass",
                            findings=[Finding(severity=Severity.INFO, message=change)],
                        )
                    )
                ee = parse_ee(ee_path)
                ctx = ValidateContext(
                    ee=ee,
                    venv_path=venv_path,
                    fix=fix,
                    container_test=container_test,
                    runtime=runtime,
                    verbose=verbose,
                    use_cache=use_cache,
                    cache_path=cache_path,
                )
                r0 = prechecks.validate(ctx)

        results.append(r0)
        missing_files = any(f.code == "missing_file" for f in r0.findings)

        # Skip downstream layers if required files are missing
        if missing_files:
            results.extend(
                [
                    LayerResult(name="galaxy", status="skipped"),
                    LayerResult(name="python_deps", status="skipped"),
                    LayerResult(name="system_deps", status="skipped"),
                ]
            )
            return results

        # Layer 1: Galaxy resolution via ade install
        r1, python_build_findings, failed_pkgs = galaxy.validate(ctx)
        results.append(r1)

        # Skip Layers 2-3 if galaxy resolution failed
        if r1.has_errors:
            results.extend(
                [
                    LayerResult(name="python_deps", status="skipped"),
                    LayerResult(name="system_deps", status="skipped"),
                ]
            )
        else:
            # Layer 2: Dependency validation (diff discovered vs declared)
            r2 = python_deps.validate(ctx)
            # Attach Python build failures from Layer 1 to Layer 2 results
            r2.findings.extend(python_build_findings)
            if (
                python_build_findings
                and not r2.has_errors
                and any(f.severity == Severity.ERROR for f in python_build_findings)
            ):
                r2.status = "fail"
            results.append(r2)

            # Force Layer 3 if Python build failures were detected
            if python_build_findings:
                ctx.container_test = True

            # Layer 3: Container wheel test (source-only Python packages)
            r3 = system_deps.validate(ctx, extra_packages=failed_pkgs)
            results.append(r3)

        if fix:
            all_findings = [f for r in results for f in r.findings]
            fixable = [f for f in all_findings if f.fix and f.severity in (Severity.WARNING, Severity.ERROR)]
            if fixable:
                changes = apply_fixes(ee, fixable)
                for change in changes:
                    results.append(
                        LayerResult(
                            name="fix",
                            status="pass",
                            findings=[Finding(severity=Severity.INFO, message=change)],
                        )
                    )

                if changes:
                    # Re-validate cheap layers after fixes were applied.
                    # Layer 1 (galaxy) and Layer 3 (system_deps) are expensive
                    # and kept as-is; only re-run Layer 0 and Layer 2.
                    ee = parse_ee(ee_path)
                    ctx = ValidateContext(
                        ee=ee,
                        venv_path=venv_path,
                        fix=False,
                        container_test=ctx.container_test,
                        runtime=runtime,
                        verbose=verbose,
                        use_cache=use_cache,
                        cache_path=cache_path,
                    )

                    new_r0 = prechecks.validate(ctx)
                    for i, r in enumerate(results):
                        if r.name == "prechecks":
                            results[i] = new_r0
                            break

                    new_r2 = python_deps.validate(ctx)
                    for i, r in enumerate(results):
                        if r.name == "python_deps":
                            results[i] = new_r2
                            break

        if build:
            has_errors = any(r.has_errors for r in results)
            if has_errors:
                results.append(
                    LayerResult(
                        name="build",
                        status="skipped",
                        findings=[
                            Finding(
                                severity=Severity.ERROR,
                                message="Build skipped: unresolved errors remain",
                            )
                        ],
                    )
                )
            else:
                build_result = _run_build(ee, tag)
                results.append(build_result)

    finally:
        if not user_venv and not keep_venv:
            shutil.rmtree(venv_path, ignore_errors=True)

    return results


def _run_build(ee: EEDefinition, tag: str | None) -> LayerResult:
    """Run ansible-builder to build the execution environment image.

    Invokes ansible-builder with verbosity level 3 and passes through any
    build args extracted from the EE definition's additional_build_steps.

    Args:
        ee: Parsed execution environment definition
        tag: Image tag for the build (default: <ee_dir_name>:latest)

    Returns:
        LayerResult indicating build success or failure
    """
    ee_name = ee.ee_dir.name
    if tag is None:
        tag = f"{ee_name}:latest"

    cmd = [
        "ansible-builder",
        "build",
        "-f",
        str(ee.path),
        "-t",
        tag,
        "-v",
        "3",
    ]

    # Pass through ARGs declared in additional_build_steps
    for arg_name in ee.build_args:
        val = os.environ.get(arg_name)
        if val:
            cmd.extend(["--build-arg", f"{arg_name}={val}"])

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return LayerResult(
            name="build",
            status="fail",
            findings=[
                Finding(
                    severity=Severity.ERROR,
                    message="Build timed out after 600s",
                )
            ],
        )

    if proc.returncode == 0:
        return LayerResult(
            name="build",
            status="pass",
            findings=[
                Finding(
                    severity=Severity.INFO,
                    message=f"Image built successfully: {tag}",
                )
            ],
        )

    return LayerResult(
        name="build",
        status="fail",
        findings=[
            Finding(
                severity=Severity.ERROR,
                message=f"Build failed: {proc.stderr[-300:]}",
            )
        ],
    )
