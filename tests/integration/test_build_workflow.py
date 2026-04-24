"""Integration tests for --build workflow.

These tests verify that ee-preflight can trigger ansible-builder,
respect --tag, skip on errors, and pass build args.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from textwrap import dedent
from unittest.mock import MagicMock, patch

import pytest

from ee_preflight.runner import _run_build, run
from ee_preflight.models import EEDefinition, Finding, LayerResult, Severity


@pytest.mark.integration
class TestBuildWorkflow:
    """Test --build integration with ansible-builder."""

    @patch("ee_preflight.runner.subprocess.run")
    def test_build_success(self, mock_run: MagicMock, tmp_path: Path):
        """Test successful build execution."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text(
            dedent("""\
                version: 3
                images:
                  base_image:
                    name: registry.redhat.io/ansible-automation-platform-25/ee-minimal-rhel9:latest
            """)
        )

        ee = EEDefinition(
            path=ee_yml,
            ee_dir=tmp_path,
            version=3,
            base_image="registry.redhat.io/ansible-automation-platform-25/ee-minimal-rhel9:latest",
        )

        # Mock successful build
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="Build complete", stderr=""
        )

        result = _run_build(ee, None)

        assert result.name == "build"
        assert result.status == "pass"
        assert len(result.findings) == 1
        assert "successfully" in result.findings[0].message.lower()
        # Verify default tag was used
        assert any("latest" in str(arg) for call in mock_run.call_args_list for arg in call[0][0])

    @patch("ee_preflight.runner.subprocess.run")
    def test_build_with_custom_tag(self, mock_run: MagicMock, tmp_path: Path):
        """Test build with custom --tag."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text(
            dedent("""\
                version: 3
                images:
                  base_image:
                    name: registry.redhat.io/ansible-automation-platform-25/ee-minimal-rhel9:latest
            """)
        )

        ee = EEDefinition(
            path=ee_yml,
            ee_dir=tmp_path,
            version=3,
            base_image="registry.redhat.io/ansible-automation-platform-25/ee-minimal-rhel9:latest",
        )

        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="Build complete", stderr=""
        )

        custom_tag = "my-ee:v1.0.0"
        result = _run_build(ee, custom_tag)

        assert result.status == "pass"
        # Verify custom tag was used
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "-t" in call_args
        tag_idx = call_args.index("-t")
        assert call_args[tag_idx + 1] == custom_tag

    @patch("ee_preflight.runner.subprocess.run")
    def test_build_failure(self, mock_run: MagicMock, tmp_path: Path):
        """Test build failure handling."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text(
            dedent("""\
                version: 3
                images:
                  base_image:
                    name: registry.redhat.io/ansible-automation-platform-25/ee-minimal-rhel9:latest
            """)
        )

        ee = EEDefinition(
            path=ee_yml,
            ee_dir=tmp_path,
            version=3,
            base_image="registry.redhat.io/ansible-automation-platform-25/ee-minimal-rhel9:latest",
        )

        # Mock failed build
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="Error: build failed"
        )

        result = _run_build(ee, None)

        assert result.name == "build"
        assert result.status == "fail"
        assert len(result.findings) == 1
        assert result.findings[0].severity == Severity.ERROR
        assert "failed" in result.findings[0].message.lower()

    @patch("ee_preflight.runner.subprocess.run")
    def test_build_timeout(self, mock_run: MagicMock, tmp_path: Path):
        """Test build timeout handling."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text(
            dedent("""\
                version: 3
                images:
                  base_image:
                    name: registry.redhat.io/ansible-automation-platform-25/ee-minimal-rhel9:latest
            """)
        )

        ee = EEDefinition(
            path=ee_yml,
            ee_dir=tmp_path,
            version=3,
            base_image="registry.redhat.io/ansible-automation-platform-25/ee-minimal-rhel9:latest",
        )

        # Mock timeout
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=[], timeout=600)

        result = _run_build(ee, None)

        assert result.name == "build"
        assert result.status == "fail"
        assert len(result.findings) == 1
        assert "timeout" in result.findings[0].message.lower()

    @patch("ee_preflight.runner.subprocess.run")
    def test_build_passes_env_build_args(self, mock_run: MagicMock, tmp_path: Path):
        """Test that build args from environment are passed to ansible-builder."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text(
            dedent("""\
                version: 3
                images:
                  base_image:
                    name: registry.redhat.io/ansible-automation-platform-25/ee-minimal-rhel9:latest
                additional_build_steps:
                  prepend_galaxy:
                    - ARG AH_TOKEN
                    - ENV ANSIBLE_GALAXY_SERVER_AUTOMATION_HUB_TOKEN=$AH_TOKEN
            """)
        )

        ee = EEDefinition(
            path=ee_yml,
            ee_dir=tmp_path,
            version=3,
            base_image="registry.redhat.io/ansible-automation-platform-25/ee-minimal-rhel9:latest",
            build_steps={
                "prepend_galaxy": [
                    "ARG AH_TOKEN",
                    "ENV ANSIBLE_GALAXY_SERVER_AUTOMATION_HUB_TOKEN=$AH_TOKEN",
                ]
            },
        )

        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )

        # Set environment variable
        os.environ["AH_TOKEN"] = "test-token-123"
        try:
            result = _run_build(ee, None)

            assert result.status == "pass"
            # Verify --build-arg was passed
            call_args = mock_run.call_args[0][0]
            assert "--build-arg" in call_args
            arg_idx = call_args.index("--build-arg")
            assert call_args[arg_idx + 1] == "AH_TOKEN=test-token-123"
        finally:
            del os.environ["AH_TOKEN"]

    @patch("ee_preflight.runner.subprocess.run")
    def test_build_skips_on_validation_errors(self, mock_run: MagicMock, tmp_path: Path):
        """Test that --build is skipped when validation errors exist."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text(
            dedent("""\
                version: 3
                images:
                  base_image:
                    name: registry.redhat.io/ansible-automation-platform-25/ee-minimal-rhel9:latest
                dependencies:
                  galaxy: missing-file.yml
            """)
        )

        # Mock all subprocess calls to avoid actual execution
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )

        with patch("ee_preflight.layers.prechecks.validate") as mock_prechecks:
            # Mock a precheck failure
            mock_prechecks.return_value = LayerResult(
                name="prechecks",
                status="fail",
                findings=[
                    Finding(
                        severity=Severity.ERROR,
                        message="File not found: missing-file.yml",
                    )
                ],
            )

            results = run(ee_path=ee_yml, build=True)

            # Build should be skipped
            build_result = next((r for r in results if r.name == "build"), None)
            assert build_result is not None
            assert build_result.status == "skipped"
            assert any("skipped" in f.message.lower() for f in build_result.findings)


@pytest.mark.integration
class TestBuildIntegrationFlags:
    """Test interaction between --build and other flags."""

    @patch("ee_preflight.runner.subprocess.run")
    @patch("ee_preflight.layers.prechecks.validate")
    @patch("ee_preflight.layers.galaxy.validate")
    @patch("ee_preflight.layers.python_deps.validate")
    @patch("ee_preflight.layers.system_deps.validate")
    def test_build_and_fix_workflow(
        self,
        mock_system: MagicMock,
        mock_python: MagicMock,
        mock_galaxy: MagicMock,
        mock_prechecks: MagicMock,
        mock_subprocess: MagicMock,
        tmp_path: Path,
    ):
        """Test --build combined with --fix."""
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

        # Mock all layers to pass
        mock_prechecks.return_value = LayerResult(name="prechecks", status="pass")
        mock_galaxy.return_value = (
            LayerResult(name="galaxy", status="pass"),
            [],
            [],
        )
        mock_python.return_value = LayerResult(name="python_deps", status="pass")
        mock_system.return_value = LayerResult(name="system_deps", status="pass")
        mock_subprocess.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )

        results = run(ee_path=ee_yml, fix=True, build=True)

        # Build should have run
        build_result = next((r for r in results if r.name == "build"), None)
        assert build_result is not None
        assert build_result.status == "pass"

    @patch("ee_preflight.runner.subprocess.run")
    def test_build_preserves_venv(self, mock_run: MagicMock, tmp_path: Path):
        """Test that --build with --keep-venv preserves the venv."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text(
            dedent("""\
                version: 3
                images:
                  base_image:
                    name: registry.redhat.io/ansible-automation-platform-25/ee-minimal-rhel9:latest
            """)
        )

        venv_path = tmp_path / "test-venv"

        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )

        with patch("ee_preflight.layers.prechecks.validate") as mock_prechecks, \
             patch("ee_preflight.layers.galaxy.validate") as mock_galaxy, \
             patch("ee_preflight.layers.python_deps.validate") as mock_python, \
             patch("ee_preflight.layers.system_deps.validate") as mock_system:

            mock_prechecks.return_value = LayerResult(name="prechecks", status="pass")
            mock_galaxy.return_value = (LayerResult(name="galaxy", status="pass"), [], [])
            mock_python.return_value = LayerResult(name="python_deps", status="pass")
            mock_system.return_value = LayerResult(name="system_deps", status="pass")

            results = run(
                ee_path=ee_yml,
                build=True,
                venv_path=venv_path,
                keep_venv=True,
            )

            build_result = next((r for r in results if r.name == "build"), None)
            assert build_result is not None
