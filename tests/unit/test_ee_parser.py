from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from ee_preflight.ee_parser import _extract_base_image, parse_ee
from ee_preflight.models import DepFormat


class TestParseEE:
    def test_parse_v3_ee(self, tmp_ee_dir: Path):
        ee = parse_ee(tmp_ee_dir / "execution-environment.yml")

        assert ee.version == 3
        assert ee.base_image == ("registry.redhat.io/ansible-automation-platform-25/ee-minimal-rhel9:latest")
        assert ee.galaxy is not None
        assert ee.galaxy.format == DepFormat.FILE

    def test_parse_v2_ee(self, tmp_path: Path):
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text(
            dedent("""\
                version: 2
                build_arg_defaults:
                  EE_BASE_IMAGE: registry.redhat.io/ansible-automation-platform-24/ee-minimal-rhel9:latest
                dependencies:
                  galaxy: requirements.yml
            """)
        )
        reqs = tmp_path / "requirements.yml"
        reqs.write_text(
            dedent("""\
                collections:
                  - name: ansible.posix
            """)
        )

        ee = parse_ee(ee_yml)

        assert ee.version == 2
        assert ee.base_image == ("registry.redhat.io/ansible-automation-platform-24/ee-minimal-rhel9:latest")

    def test_parse_inline_deps(self, inline_ee_dir: Path):
        ee = parse_ee(inline_ee_dir / "execution-environment.yml")

        assert ee.galaxy is not None
        assert ee.galaxy.format == DepFormat.INLINE
        assert len(ee.galaxy.entries) == 2
        assert ee.galaxy.entries[0]["name"] == "ansible.posix"
        assert ee.galaxy.entries[1]["name"] == "community.general"

    def test_parse_file_deps(self, tmp_ee_dir: Path):
        ee = parse_ee(tmp_ee_dir / "execution-environment.yml")

        assert ee.galaxy is not None
        assert ee.galaxy.format == DepFormat.FILE
        assert ee.galaxy.file_path is not None
        assert ee.galaxy.file_path.name == "requirements.yml"
        assert ee.galaxy.file_path.exists()

    def test_parse_no_deps(self, tmp_path: Path):
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text(
            dedent("""\
                version: 3
                images:
                  base_image:
                    name: registry.redhat.io/ansible-automation-platform-25/ee-minimal-rhel9:latest
            """)
        )

        ee = parse_ee(ee_yml)

        assert ee.galaxy is None
        assert ee.python is None
        assert ee.system is None


class TestExtractBaseImage:
    def test_extract_base_image_v3(self):
        raw = {
            "images": {
                "base_image": {
                    "name": "registry.redhat.io/ee-minimal-rhel9:latest",
                },
            },
        }
        result = _extract_base_image(raw, version=3)
        assert result == "registry.redhat.io/ee-minimal-rhel9:latest"

    def test_extract_base_image_v2(self):
        raw = {
            "build_arg_defaults": {
                "EE_BASE_IMAGE": "registry.redhat.io/ee-minimal-rhel8:latest",
            },
        }
        result = _extract_base_image(raw, version=2)
        assert result == "registry.redhat.io/ee-minimal-rhel8:latest"
