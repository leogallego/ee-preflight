from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from ee_preflight.ee_parser import parse_ee
from ee_preflight.fixer import _extract_quoted_entries, apply_fixes
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
