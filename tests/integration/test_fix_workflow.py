"""Integration tests for --fix workflow.

These tests verify that ee-preflight can auto-fix missing dependencies
by appending to bindep.txt/requirements.txt or modifying inline YAML.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from ee_preflight.ee_parser import parse_ee
from ee_preflight.fixer import apply_fixes
from ee_preflight.models import Finding, Severity


@pytest.mark.integration
class TestFixWorkflowBindep:
    """Test --fix for system dependencies (bindep.txt)."""

    def test_fix_creates_bindep_txt(self, tmp_path: Path):
        """When no bindep.txt exists, --fix creates it and adds the dep."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text(
            dedent("""\
                version: 3
                images:
                  base_image:
                    name: registry.redhat.io/ansible-automation-platform-25/ee-minimal-rhel9:latest
                dependencies:
                  galaxy: requirements.yml
            """)
        )
        reqs = tmp_path / "requirements.yml"
        reqs.write_text("collections:\n  - name: ansible.posix\n")

        ee = parse_ee(ee_yml)
        findings = [
            Finding(
                severity=Severity.ERROR,
                message="Missing libxml2-devel",
                fix="Add 'libxml2-devel' to bindep.txt",
                source="system_deps",
            ),
        ]

        changes = apply_fixes(ee, findings)

        assert len(changes) > 0
        bindep = tmp_path / "bindep.txt"
        assert bindep.exists()
        assert "libxml2-devel" in bindep.read_text()
        # Verify dep reference was added to EE file
        ee_content = ee_yml.read_text()
        assert "system: bindep.txt" in ee_content

    def test_fix_appends_to_existing_bindep(self, tmp_path: Path):
        """When bindep.txt exists, --fix appends new deps."""
        ee_yml = tmp_path / "execution-environment.yml"
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
        reqs = tmp_path / "requirements.yml"
        reqs.write_text("collections:\n  - name: ansible.posix\n")

        bindep = tmp_path / "bindep.txt"
        bindep.write_text("gcc\n")

        ee = parse_ee(ee_yml)
        findings = [
            Finding(
                severity=Severity.ERROR,
                message="Missing openssl-devel",
                fix="Add 'openssl-devel' to bindep.txt",
                source="system_deps",
            ),
        ]

        changes = apply_fixes(ee, findings)

        content = bindep.read_text()
        assert "gcc" in content
        assert "openssl-devel" in content
        assert len(changes) == 1

    def test_fix_idempotent_bindep(self, tmp_path: Path):
        """Running --fix twice should not duplicate deps."""
        ee_yml = tmp_path / "execution-environment.yml"
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
        reqs = tmp_path / "requirements.yml"
        reqs.write_text("collections:\n  - name: ansible.posix\n")

        bindep = tmp_path / "bindep.txt"
        bindep.write_text("gcc\n")

        ee = parse_ee(ee_yml)
        findings = [
            Finding(
                severity=Severity.ERROR,
                message="Missing gcc",
                fix="Add 'gcc' to bindep.txt",
                source="system_deps",
            ),
        ]

        # First fix
        changes1 = apply_fixes(ee, findings)
        content1 = bindep.read_text()

        # Second fix with same finding
        ee = parse_ee(ee_yml)
        changes2 = apply_fixes(ee, findings)
        content2 = bindep.read_text()

        # Should not have added gcc twice
        assert content1.count("gcc") == 1
        assert content2.count("gcc") == 1
        assert len(changes1) == 0  # gcc already existed
        assert len(changes2) == 0

    def test_fix_inline_system_deps(self, tmp_path: Path):
        """Test --fix with inline system dependencies."""
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
                  system:
                    - gcc
            """)
        )

        ee = parse_ee(ee_yml)
        findings = [
            Finding(
                severity=Severity.ERROR,
                message="Missing openssl-devel",
                fix="Add 'openssl-devel' to bindep.txt",
                source="system_deps",
            ),
        ]

        changes = apply_fixes(ee, findings)

        assert len(changes) > 0
        ee_content = ee_yml.read_text()
        assert "- gcc" in ee_content
        assert "- openssl-devel" in ee_content


@pytest.mark.integration
class TestFixWorkflowPython:
    """Test --fix for Python dependencies (requirements.txt).

    NOTE: These tests call the private ``_add_python_deps`` function directly
    because ``apply_fixes`` does not yet route any findings to Python-dep
    fixes (no layer currently emits Python-specific fix suggestions).
    Once a layer starts producing such suggestions, these tests should be
    migrated to exercise the public ``apply_fixes`` entry point instead.
    """

    def test_fix_creates_requirements_txt(self, tmp_path: Path):
        """When no requirements.txt exists, --fix creates it (future use case)."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text(
            dedent("""\
                version: 3
                images:
                  base_image:
                    name: registry.redhat.io/ansible-automation-platform-25/ee-minimal-rhel9:latest
                dependencies:
                  galaxy: requirements.yml
            """)
        )
        reqs = tmp_path / "requirements.yml"
        reqs.write_text("collections:\n  - name: ansible.posix\n")

        ee = parse_ee(ee_yml)

        # _add_python_deps is private; see class docstring for rationale.
        from ee_preflight.fixer import _add_python_deps

        changes: list[str] = []
        _add_python_deps(ee, ["requests>=2.28.0"], changes)

        assert len(changes) > 0
        reqs_txt = tmp_path / "requirements.txt"
        assert reqs_txt.exists()
        assert "requests>=2.28.0" in reqs_txt.read_text()

    def test_fix_appends_to_existing_requirements(self, tmp_path: Path):
        """When requirements.txt exists, --fix appends new deps."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text(
            dedent("""\
                version: 3
                images:
                  base_image:
                    name: registry.redhat.io/ansible-automation-platform-25/ee-minimal-rhel9:latest
                dependencies:
                  galaxy: requirements.yml
                  python: requirements.txt
            """)
        )
        reqs = tmp_path / "requirements.yml"
        reqs.write_text("collections:\n  - name: ansible.posix\n")

        reqs_txt = tmp_path / "requirements.txt"
        reqs_txt.write_text("pyyaml\n")

        ee = parse_ee(ee_yml)

        # _add_python_deps is private; see class docstring for rationale.
        from ee_preflight.fixer import _add_python_deps

        changes: list[str] = []
        _add_python_deps(ee, ["requests>=2.28.0"], changes)

        content = reqs_txt.read_text()
        assert "pyyaml" in content
        assert "requests>=2.28.0" in content

    def test_fix_idempotent_python_deps(self, tmp_path: Path):
        """Python deps should not be duplicated."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text(
            dedent("""\
                version: 3
                images:
                  base_image:
                    name: registry.redhat.io/ansible-automation-platform-25/ee-minimal-rhel9:latest
                dependencies:
                  galaxy: requirements.yml
                  python: requirements.txt
            """)
        )
        reqs = tmp_path / "requirements.yml"
        reqs.write_text("collections:\n  - name: ansible.posix\n")

        reqs_txt = tmp_path / "requirements.txt"
        reqs_txt.write_text("requests>=2.28.0\n")

        ee = parse_ee(ee_yml)

        # _add_python_deps is private; see class docstring for rationale.
        from ee_preflight.fixer import _add_python_deps

        # First fix
        changes1: list[str] = []
        _add_python_deps(ee, ["requests>=2.28.0"], changes1)
        content1 = reqs_txt.read_text()

        # Second fix with same dep
        ee = parse_ee(ee_yml)
        changes2: list[str] = []
        _add_python_deps(ee, ["requests>=2.28.0"], changes2)
        content2 = reqs_txt.read_text()

        # Should not have added requests twice
        assert content1.count("requests") == 1
        assert content2.count("requests") == 1
        assert len(changes1) == 0  # requests already existed
        assert len(changes2) == 0


@pytest.mark.integration
class TestFixWorkflowMixedFormats:
    """Test --fix with mixed dependency formats."""

    def test_fix_file_and_inline_deps(self, tmp_path: Path):
        """Test fixing EE with file-based galaxy and inline system deps."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text(
            dedent("""\
                version: 3
                images:
                  base_image:
                    name: registry.redhat.io/ansible-automation-platform-25/ee-minimal-rhel9:latest
                dependencies:
                  galaxy: requirements.yml
                  system:
                    - gcc
            """)
        )
        reqs = tmp_path / "requirements.yml"
        reqs.write_text("collections:\n  - name: ansible.posix\n")

        ee = parse_ee(ee_yml)
        findings = [
            Finding(
                severity=Severity.ERROR,
                message="Missing openssl-devel",
                fix="Add 'openssl-devel' to bindep.txt",
                source="system_deps",
            ),
        ]

        changes = apply_fixes(ee, findings)

        assert len(changes) > 0
        ee_content = ee_yml.read_text()
        # Should add to inline list
        assert "- openssl-devel" in ee_content

    def test_fix_preserves_yaml_structure(self, tmp_path: Path):
        """Ensure --fix preserves YAML structure and comments."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text(
            dedent("""\
                version: 3
                # Base image configuration
                images:
                  base_image:
                    name: registry.redhat.io/ansible-automation-platform-25/ee-minimal-rhel9:latest
                # Dependencies section
                dependencies:
                  galaxy: requirements.yml
                  system:
                    - gcc  # C compiler
            """)
        )
        reqs = tmp_path / "requirements.yml"
        reqs.write_text("collections:\n  - name: ansible.posix\n")

        ee = parse_ee(ee_yml)
        findings = [
            Finding(
                severity=Severity.ERROR,
                message="Missing python3-devel",
                fix="Add 'python3-devel' to bindep.txt",
                source="system_deps",
            ),
        ]

        apply_fixes(ee, findings)

        ee_content = ee_yml.read_text()
        # Comments should be preserved
        assert "# Base image configuration" in ee_content
        assert "# Dependencies section" in ee_content
        # New dep should be added
        assert "- python3-devel" in ee_content
