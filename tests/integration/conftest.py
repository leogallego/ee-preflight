from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def minimal_ee_path():
    return FIXTURES_DIR / "minimal-ee" / "execution-environment.yml"


@pytest.fixture
def inline_ee_path():
    return FIXTURES_DIR / "inline-ee" / "execution-environment.yml"
