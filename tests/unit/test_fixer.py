from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import yaml

from ee_preflight.ee_parser import parse_ee
from ee_preflight.fixer import (
    _extract_quoted_entries,
    _remove_root_key,
    apply_fixes,
    apply_layer0_fixes,
)
from ee_preflight.models import (
    EEDefinition,
    Finding,
    Severity,
)


class TestApplyFixes:
    def test_apply_fixes_creates_bindep(self, tmp_ee_dir: Path):
        """System dep fix creates bindep.txt when none exists."""
        ee = parse_ee(tmp_ee_dir / "execution-environment.yml")

        # Ensure no system dep ref and no bindep.txt
        assert ee.system is None
        assert not (tmp_ee_dir / "bindep.txt").exists()

        findings = [
            Finding(
                severity=Severity.ERROR,
                message="Missing system package libxml2-devel",
                fix="Add 'libxml2-devel' to bindep.txt",
                source="system_deps",
            ),
        ]

        changes = apply_fixes(ee, findings)

        assert len(changes) > 0
        bindep = tmp_ee_dir / "bindep.txt"
        assert bindep.exists()
        content = bindep.read_text()
        assert "libxml2-devel" in content

    def test_apply_fixes_appends_to_existing(self, tmp_ee_dir: Path):
        """When bindep.txt exists, new entries are appended and existing
        entries are not duplicated."""
        # Create an EE with a system dep file reference
        ee_yml = tmp_ee_dir / "execution-environment.yml"
        ee_yml.write_text(
            dedent("""\
                version: 3
                images:
                  base_image:
                    name: registry.redhat.io/ansible-automation-platform-25/ee-minimal-rhel9:latest
                dependencies:
                  galaxy: requirements.yml
                  system: bindep.txt
            """)
        )

        # Pre-populate bindep.txt with an existing entry
        bindep = tmp_ee_dir / "bindep.txt"
        bindep.write_text("gcc\n")

        ee = parse_ee(ee_yml)

        findings = [
            Finding(
                severity=Severity.ERROR,
                message="Missing gcc",
                fix="Add 'gcc' to bindep.txt",
                source="system_deps",
            ),
            Finding(
                severity=Severity.ERROR,
                message="Missing openssl-devel",
                fix="Add 'openssl-devel' to bindep.txt",
                source="system_deps",
            ),
        ]

        changes = apply_fixes(ee, findings)

        content = bindep.read_text()
        # gcc was already there, should not be duplicated
        assert content.count("gcc") == 1
        # openssl-devel should be appended
        assert "openssl-devel" in content
        assert len(changes) == 1
        assert "openssl-devel" in changes[0]

    def test_apply_fixes_no_fixable(self):
        """Empty findings list produces no changes."""
        ee = EEDefinition(
            path=Path("/fake/execution-environment.yml"),
            ee_dir=Path("/fake"),
            version=3,
            base_image="registry.redhat.io/ee-minimal-rhel9:latest",
        )

        changes = apply_fixes(ee, [])

        assert changes == []


class TestPkgNameNormalization:
    """Test _pkg_name normalization (hyphen/underscore equivalence)."""

    def test_fix_handles_hyphenated_package_names(self, tmp_path: Path):
        """Verify that pip-tools (existing) matches pip_tools (new)
        and doesn't create a duplicate."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text(
            dedent("""\
                version: 3
                images:
                  base_image:
                    name: registry.redhat.io/ee-minimal-rhel9:latest
                dependencies:
                  galaxy: requirements.yml
                  python: requirements.txt
            """)
        )
        reqs = tmp_path / "requirements.yml"
        reqs.write_text("collections:\n  - name: ansible.posix\n")

        reqs_txt = tmp_path / "requirements.txt"
        reqs_txt.write_text("pip-tools\n")

        ee = parse_ee(ee_yml)

        from ee_preflight.fixer import _add_python_deps

        changes: list[str] = []
        # pip_tools (underscore) should match existing pip-tools (hyphen)
        _add_python_deps(ee, ["pip_tools"], changes)

        content = reqs_txt.read_text()
        # Should not have added a duplicate entry
        assert content.count("pip") == 1
        assert len(changes) == 0

    def test_normalization_strips_version_specifiers(self):
        """Verify _pkg_name strips version specifiers before normalizing."""
        from ee_preflight.models import pkg_name

        assert pkg_name("pip-tools>=7.0") == "pip_tools"
        assert pkg_name("pip_tools>=7.0") == "pip_tools"
        assert pkg_name("PyYAML") == "pyyaml"
        assert pkg_name("requests[security]>=2.28") == "requests"


class TestExtractQuotedEntries:
    def test_extract_quoted_entries(self):
        findings = [
            Finding(
                severity=Severity.ERROR,
                message="Missing libxml2-devel",
                fix="Add 'libxml2-devel' to bindep.txt",
            ),
            Finding(
                severity=Severity.ERROR,
                message="Missing openssl-devel",
                fix="Add 'openssl-devel' to bindep.txt",
            ),
            Finding(
                severity=Severity.WARNING,
                message="Something without a fix",
                fix=None,
            ),
            Finding(
                severity=Severity.ERROR,
                message="Missing python3-devel",
                fix="Add 'python3-devel' to bindep.txt",
            ),
        ]

        entries = _extract_quoted_entries(findings)

        assert entries == ["libxml2-devel", "openssl-devel", "python3-devel"]


class TestFixStrayCollections:
    """Tests for _fix_stray_collections via apply_layer0_fixes."""

    def test_case_a_missing_galaxy_file_creates_requirements(self, tmp_path: Path):
        """Case A: galaxy file ref exists but file missing + root collections
        -> creates requirements.yml from root collections."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text(
            dedent("""\
                version: 3
                images:
                  base_image:
                    name: test:latest
                dependencies:
                  galaxy: requirements.yml
                collections:
                  - name: ansible.posix
                  - name: community.general
            """)
        )

        # Do NOT create requirements.yml — it should be missing
        ee = parse_ee(ee_yml)

        findings = [
            Finding(
                severity=Severity.WARNING,
                message="stray collections",
                code="stray_collections",
            ),
        ]

        changes = apply_layer0_fixes(ee, findings)

        # requirements.yml should now exist with the collections
        reqs = tmp_path / "requirements.yml"
        assert reqs.exists()
        data = yaml.safe_load(reqs.read_text())
        names = [c["name"] if isinstance(c, dict) else c for c in data["collections"]]
        assert "ansible.posix" in names
        assert "community.general" in names

        # Root collections key should be removed from EE
        ee_content = yaml.safe_load(ee_yml.read_text())
        assert "collections" not in ee_content

        assert any("Created" in c for c in changes)
        assert any("Removed root-level" in c for c in changes)

    def test_case_b_existing_galaxy_file_merges_deduplicates(self, tmp_path: Path):
        """Case B: galaxy file ref + file exists + root collections
        -> merges and deduplicates."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text(
            dedent("""\
                version: 3
                images:
                  base_image:
                    name: test:latest
                dependencies:
                  galaxy: requirements.yml
                collections:
                  - name: ansible.posix
                  - name: community.crypto
            """)
        )

        # Create requirements.yml with an existing collection
        reqs = tmp_path / "requirements.yml"
        reqs.write_text(
            dedent("""\
                collections:
                  - name: ansible.posix
                  - name: ansible.utils
            """)
        )

        ee = parse_ee(ee_yml)

        findings = [
            Finding(
                severity=Severity.WARNING,
                message="stray collections",
                code="stray_collections",
            ),
        ]

        apply_layer0_fixes(ee, findings)

        # requirements.yml should have merged entries, no duplicates
        data = yaml.safe_load(reqs.read_text())
        names = [c["name"] if isinstance(c, dict) else c for c in data["collections"]]
        assert names.count("ansible.posix") == 1
        assert "ansible.utils" in names
        assert "community.crypto" in names

        # Root collections key should be removed from EE
        ee_content = yaml.safe_load(ee_yml.read_text())
        assert "collections" not in ee_content

    def test_case_d_no_galaxy_dep_adds_inline(self, tmp_path: Path):
        """Case D: no galaxy dep + root collections -> adds inline to EE."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text(
            dedent("""\
                version: 3
                images:
                  base_image:
                    name: test:latest
                dependencies:
                  python: requirements.txt
                collections:
                  - name: ansible.posix
            """)
        )
        # Create a dummy requirements.txt so parse_ee doesn't fail on it
        (tmp_path / "requirements.txt").write_text("")

        ee = parse_ee(ee_yml)

        findings = [
            Finding(
                severity=Severity.WARNING,
                message="stray collections",
                code="stray_collections",
            ),
        ]

        changes = apply_layer0_fixes(ee, findings)

        # EE should now have inline galaxy collections
        ee_content = yaml.safe_load(ee_yml.read_text())
        assert "collections" not in ee_content  # root key removed
        galaxy_dep = ee_content.get("dependencies", {}).get("galaxy", {})
        assert "collections" in galaxy_dep
        coll_names = [
            c["name"] if isinstance(c, dict) else c
            for c in galaxy_dep["collections"]
        ]
        assert "ansible.posix" in coll_names

        assert any("Added inline galaxy" in c for c in changes)


class TestRemoveRootKey:
    """Tests for _remove_root_key."""

    def test_removes_key_and_block(self, tmp_path: Path):
        """Root key and all indented children are removed."""
        yaml_file = tmp_path / "test.yml"
        yaml_file.write_text(
            dedent("""\
                version: 3
                collections:
                  - name: foo
                  - name: bar
                images:
                  base_image:
                    name: test:latest
            """)
        )

        _remove_root_key(yaml_file, "collections")

        content = yaml_file.read_text()
        assert "collections" not in content
        assert "foo" not in content
        assert "bar" not in content
        # Other keys should remain
        assert "version: 3" in content
        assert "images:" in content
        assert "test:latest" in content

    def test_removes_last_key(self, tmp_path: Path):
        """Removing the last key in the file works."""
        yaml_file = tmp_path / "test.yml"
        yaml_file.write_text(
            dedent("""\
                version: 3
                extra:
                  key: value
            """)
        )

        _remove_root_key(yaml_file, "extra")

        content = yaml_file.read_text()
        assert "extra" not in content
        assert "key" not in content
        assert "version: 3" in content


class TestApplyLayer0Fixes:
    """Tests for apply_layer0_fixes routing logic."""

    def test_routes_stray_collections(self, tmp_path: Path):
        """apply_layer0_fixes handles stray_collections finding."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text(
            dedent("""\
                version: 3
                images:
                  base_image:
                    name: test:latest
                dependencies:
                  galaxy: requirements.yml
                collections:
                  - name: ansible.posix
            """)
        )
        # No requirements.yml – Case A

        ee = parse_ee(ee_yml)

        findings = [
            Finding(
                severity=Severity.WARNING,
                message="stray",
                code="stray_collections",
            ),
        ]

        changes = apply_layer0_fixes(ee, findings)

        assert len(changes) > 0
        reqs = tmp_path / "requirements.yml"
        assert reqs.exists()

    def test_routes_missing_system_file(self, tmp_path: Path):
        """apply_layer0_fixes creates empty file for missing system dep."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text(
            dedent("""\
                version: 3
                images:
                  base_image:
                    name: test:latest
                dependencies:
                  galaxy: requirements.yml
                  system: bindep.txt
            """)
        )
        # Create galaxy file but NOT bindep.txt
        (tmp_path / "requirements.yml").write_text(
            "collections:\n  - name: ansible.posix\n"
        )

        ee = parse_ee(ee_yml)

        findings = [
            Finding(
                severity=Severity.ERROR,
                message="missing file",
                code="missing_file",
                source="system",
            ),
        ]

        changes = apply_layer0_fixes(ee, findings)

        assert (tmp_path / "bindep.txt").exists()
        assert any("Created empty bindep.txt" in c for c in changes)

    def test_ignores_non_system_missing_file(self, tmp_path: Path):
        """apply_layer0_fixes only creates files for source=system."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text(
            dedent("""\
                version: 3
                images:
                  base_image:
                    name: test:latest
                dependencies:
                  galaxy: requirements.yml
            """)
        )

        ee = parse_ee(ee_yml)

        findings = [
            Finding(
                severity=Severity.ERROR,
                message="missing file",
                code="missing_file",
                source="galaxy",
            ),
        ]

        changes = apply_layer0_fixes(ee, findings)

        # Should not create any file for galaxy missing_file
        assert len(changes) == 0
