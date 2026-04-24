"""Integration tests for Layer 3 (container-based system dependency resolution).

These tests require:
- ``podman`` (or ``docker``) installed and available on PATH.
- Ability to pull the base image specified in the EE definition.
- Sufficient privileges to run containers.
"""

import shutil

import pytest

from ee_preflight.ee_parser import parse_ee
from ee_preflight.layers.system_deps import validate
from ee_preflight.models import ValidateContext

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _require_container_runtime():
    """Skip all tests in this module when no container runtime is available."""
    if not shutil.which("podman") and not shutil.which("docker"):
        pytest.skip("No container runtime (podman/docker) found on PATH")


def test_system_deps_skipped_without_flag(minimal_ee_path, tmp_path):
    """Layer 3 should return 'skipped' when container_test is not enabled."""
    ee = parse_ee(minimal_ee_path)
    ctx = ValidateContext(ee=ee, venv_path=tmp_path / "venv", container_test=False)
    result = validate(ctx)

    assert result.name == "system_deps"
    assert result.status == "skipped"


def test_system_deps_runs_with_flag(minimal_ee_path, tmp_path):
    """Layer 3 should attempt validation when container_test is enabled."""
    ee = parse_ee(minimal_ee_path)
    ctx = ValidateContext(ee=ee, venv_path=tmp_path / "venv", container_test=True)
    result = validate(ctx)

    assert result.name == "system_deps"
    assert result.status in ("pass", "fail")


def test_system_deps_runtime_selection_podman(minimal_ee_path, tmp_path):
    """Layer 3 should use podman when explicitly requested."""
    if not shutil.which("podman"):
        pytest.skip("podman not available for testing")

    ee = parse_ee(minimal_ee_path)
    ctx = ValidateContext(ee=ee, venv_path=tmp_path / "venv", container_test=True, runtime="podman")
    result = validate(ctx)

    assert result.name == "system_deps"
    assert result.status in ("pass", "fail")


def test_system_deps_runtime_selection_docker(minimal_ee_path, tmp_path):
    """Layer 3 should use docker when explicitly requested."""
    if not shutil.which("docker"):
        pytest.skip("docker not available for testing")

    ee = parse_ee(minimal_ee_path)
    ctx = ValidateContext(ee=ee, venv_path=tmp_path / "venv", container_test=True, runtime="docker")
    result = validate(ctx)

    assert result.name == "system_deps"
    assert result.status in ("pass", "fail")


def test_system_deps_invalid_runtime(minimal_ee_path, tmp_path):
    """Layer 3 should fail gracefully when an invalid runtime is requested."""
    ee = parse_ee(minimal_ee_path)
    ctx = ValidateContext(ee=ee, venv_path=tmp_path / "venv", container_test=True, runtime="invalid")
    result = validate(ctx)

    assert result.name == "system_deps"
    assert result.status == "fail"
    assert any("Invalid runtime" in f.message for f in result.findings)
