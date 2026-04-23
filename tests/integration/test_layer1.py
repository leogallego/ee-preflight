"""Integration tests for Layer 1 (galaxy collection resolution).

These tests require:
- ``ade`` (ansible-dev-environment) installed and available on PATH.
- Network access to Galaxy (galaxy.ansible.com) or Automation Hub.
"""

import pytest

from ee_preflight.ee_parser import parse_ee
from ee_preflight.layers.galaxy import validate
from ee_preflight.models import ValidateContext


@pytest.mark.integration
def test_galaxy_resolve_minimal_ee(minimal_ee_path, tmp_path):
    """Resolve collections from an external requirements file."""
    ee = parse_ee(minimal_ee_path)
    ctx = ValidateContext(ee=ee, venv_path=tmp_path / "venv")
    result = validate(ctx)

    assert len(result) == 3, "validate() should return a 3-element tuple (LayerResult, findings, failed_pkgs)"
    layer_result, python_findings, failed_pkgs = result

    assert layer_result.name == "galaxy"
