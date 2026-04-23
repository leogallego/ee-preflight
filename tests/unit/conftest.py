from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from ee_preflight.ee_parser import parse_ee


@pytest.fixture()
def tmp_ee_dir(tmp_path: Path) -> Path:
    """Create a minimal v3 EE directory with file-based galaxy deps."""
    ee_yml = tmp_path / "execution-environment.yml"
    ee_yml.write_text(
        dedent("""\
            version: 3
            images:
              base_image:
                name: registry.redhat.io/ansible-automation-platform-25/ee-minimal-rhel9:latest
            dependencies:
              galaxy: requirements.yml
            additional_build_steps:
              prepend_galaxy:
                - ADD _build/configs/ansible.cfg /etc/ansible/ansible.cfg
                - ARG AH_TOKEN
                - ENV ANSIBLE_GALAXY_SERVER_AUTOMATION_HUB_TOKEN=$AH_TOKEN
        """)
    )

    reqs = tmp_path / "requirements.yml"
    reqs.write_text(
        dedent("""\
            collections:
              - name: ansible.posix
        """)
    )

    return tmp_path


@pytest.fixture()
def inline_ee_dir(tmp_path: Path) -> Path:
    """Create a v3 EE directory with inline (list) galaxy deps."""
    ee_yml = tmp_path / "execution-environment.yml"
    ee_yml.write_text(
        dedent("""\
            version: 3
            images:
              base_image:
                name: registry.redhat.io/ansible-automation-platform-25/ee-minimal-rhel9:latest
            dependencies:
              galaxy:
                collections:
                  - name: ansible.posix
                  - name: community.general
        """)
    )

    return tmp_path


@pytest.fixture()
def ee_definition(tmp_ee_dir: Path):
    """Return a parsed EEDefinition from the tmp_ee_dir fixture."""
    ee_path = tmp_ee_dir / "execution-environment.yml"
    return parse_ee(ee_path)
