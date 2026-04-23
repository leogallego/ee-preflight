"""Integration tests for Layer 0 (prechecks)."""

import pytest

from ee_preflight.ee_parser import parse_ee
from ee_preflight.layers.prechecks import validate
from ee_preflight.models import ValidateContext


@pytest.mark.integration
def test_prechecks_pass_minimal_ee(minimal_ee_path, tmp_path):
    """Prechecks should pass for a well-formed minimal EE definition."""
    ee = parse_ee(minimal_ee_path)
    ctx = ValidateContext(ee=ee, venv_path=tmp_path / "venv")
    result = validate(ctx)

    assert result.name == "prechecks"
    assert result.status == "pass"
