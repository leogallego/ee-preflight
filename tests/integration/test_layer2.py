"""Integration tests for Layer 2 (Python / system dependency diffing).

These tests depend on Layer 1 having run first so that the ``ade``
discovered-requirements files exist inside the venv directory.  In a
full integration run, use ``pytest --order`` or run tests sequentially
so that the venv populated by Layer 1 is available here.
"""

import pytest

from ee_preflight.ee_parser import parse_ee
from ee_preflight.layers.python_deps import validate
from ee_preflight.models import ValidateContext


@pytest.mark.integration
def test_python_deps_pass_after_galaxy(minimal_ee_path, tmp_path):
    """Layer 2 should pass (or report INFO-only findings) on a minimal EE."""
    ee = parse_ee(minimal_ee_path)
    ctx = ValidateContext(ee=ee, venv_path=tmp_path / "venv")
    result = validate(ctx)

    assert result.name == "python_deps"
    # With no prior ade run the layer should still return cleanly
    assert result.status in ("pass", "skipped")
