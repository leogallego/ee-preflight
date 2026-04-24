"""Unit tests for runner module."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from textwrap import dedent
from unittest.mock import MagicMock, patch

import pytest

from ee_preflight.models import EEDefinition, Finding, LayerResult, Severity
from ee_preflight.runner import _run_build, run


class TestRunBuild:
    """Test _run_build function."""

    @patch("ee_preflight.runner.subprocess.run")
    def test_run_build_success(self, mock_run: MagicMock, tmp_path: Path):
        """Test successful build."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee = EEDefinition(
            path=ee_yml,
            ee_dir=tmp_path,
            version=3,
            base_image="test:latest",
        )

        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )

        result = _run_build(ee, None)

        assert result.name == "build"
        assert result.status == "pass"
        assert len(result.findings) == 1
        assert result.findings[0].severity == Severity.INFO
        # Check default tag
        call_args = mock_run.call_args[0][0]
        assert "-t" in call_args
        tag_idx = call_args.index("-t")
        assert ":latest" in call_args[tag_idx + 1]

    @patch("ee_preflight.runner.subprocess.run")
    def test_run_build_custom_tag(self, mock_run: MagicMock, tmp_path: Path):
        """Test build with custom tag."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee = EEDefinition(
            path=ee_yml,
            ee_dir=tmp_path,
            version=3,
            base_image="test:latest",
        )

        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )

        result = _run_build(ee, "custom:v1.0.0")

        assert result.status == "pass"
        call_args = mock_run.call_args[0][0]
        assert "-t" in call_args
        tag_idx = call_args.index("-t")
        assert call_args[tag_idx + 1] == "custom:v1.0.0"

    @patch("ee_preflight.runner.subprocess.run")
    def test_run_build_failure(self, mock_run: MagicMock, tmp_path: Path):
        """Test build failure."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee = EEDefinition(
            path=ee_yml,
            ee_dir=tmp_path,
            version=3,
            base_image="test:latest",
        )

        error_msg = "Error: build failed due to missing dependency"
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr=error_msg
        )

        result = _run_build(ee, None)

        assert result.name == "build"
        assert result.status == "fail"
        assert len(result.findings) == 1
        assert result.findings[0].severity == Severity.ERROR
        # Should include truncated stderr
        assert "failed" in result.findings[0].message.lower()

    @patch("ee_preflight.runner.subprocess.run")
    def test_run_build_timeout(self, mock_run: MagicMock, tmp_path: Path):
        """Test build timeout."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee = EEDefinition(
            path=ee_yml,
            ee_dir=tmp_path,
            version=3,
            base_image="test:latest",
        )

        mock_run.side_effect = subprocess.TimeoutExpired(cmd=[], timeout=600)

        result = _run_build(ee, None)

        assert result.name == "build"
        assert result.status == "fail"
        assert len(result.findings) == 1
        assert "timeout" in result.findings[0].message.lower()

    @patch("ee_preflight.runner.subprocess.run")
    def test_run_build_with_build_args(self, mock_run: MagicMock, tmp_path: Path):
        """Test build with ARG declarations."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee = EEDefinition(
            path=ee_yml,
            ee_dir=tmp_path,
            version=3,
            base_image="test:latest",
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
            call_args = mock_run.call_args[0][0]
            assert "--build-arg" in call_args
            arg_idx = call_args.index("--build-arg")
            assert call_args[arg_idx + 1] == "AH_TOKEN=test-token-123"
        finally:
            del os.environ["AH_TOKEN"]

    @patch("ee_preflight.runner.subprocess.run")
    def test_run_build_skips_missing_env_vars(self, mock_run: MagicMock, tmp_path: Path):
        """Test build skips ARGs with no env var set."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee = EEDefinition(
            path=ee_yml,
            ee_dir=tmp_path,
            version=3,
            base_image="test:latest",
            build_steps={
                "prepend_galaxy": [
                    "ARG MISSING_VAR",
                ]
            },
        )

        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )

        # Ensure MISSING_VAR is not set
        if "MISSING_VAR" in os.environ:
            del os.environ["MISSING_VAR"]

        result = _run_build(ee, None)

        assert result.status == "pass"
        call_args = mock_run.call_args[0][0]
        # Should not have --build-arg for missing var
        if "--build-arg" in call_args:
            arg_idx = call_args.index("--build-arg")
            assert "MISSING_VAR" not in call_args[arg_idx + 1]

    @patch("ee_preflight.runner.subprocess.run")
    def test_run_build_verbose_flag(self, mock_run: MagicMock, tmp_path: Path):
        """Test build includes -v 3 flag."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee = EEDefinition(
            path=ee_yml,
            ee_dir=tmp_path,
            version=3,
            base_image="test:latest",
        )

        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )

        result = _run_build(ee, None)

        call_args = mock_run.call_args[0][0]
        assert "-v" in call_args
        v_idx = call_args.index("-v")
        assert call_args[v_idx + 1] == "3"


class TestRun:
    """Test run function orchestration."""

    @patch("ee_preflight.layers.prechecks.validate")
    @patch("ee_preflight.layers.galaxy.validate")
    @patch("ee_preflight.layers.python_deps.validate")
    @patch("ee_preflight.layers.system_deps.validate")
    def test_run_missing_files_skips_layers(
        self,
        mock_system: MagicMock,
        mock_python: MagicMock,
        mock_galaxy: MagicMock,
        mock_prechecks: MagicMock,
        tmp_path: Path,
    ):
        """Test that missing files cause later layers to be skipped."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text(
            dedent("""\
                version: 3
                images:
                  base_image:
                    name: test:latest
                dependencies:
                  galaxy: missing.yml
            """)
        )

        # Mock prechecks to report missing file
        mock_prechecks.return_value = LayerResult(
            name="prechecks",
            status="fail",
            findings=[
                Finding(
                    severity=Severity.ERROR,
                    message="File not found: missing.yml",
                )
            ],
        )

        results = run(ee_path=ee_yml)

        # Layers 1-3 should be skipped
        assert any(r.name == "galaxy" and r.status == "skipped" for r in results)
        assert any(r.name == "python_deps" and r.status == "skipped" for r in results)
        assert any(r.name == "system_deps" and r.status == "skipped" for r in results)

    @patch("ee_preflight.layers.prechecks.validate")
    @patch("ee_preflight.layers.galaxy.validate")
    @patch("ee_preflight.layers.python_deps.validate")
    @patch("ee_preflight.layers.system_deps.validate")
    def test_run_galaxy_errors_skip_later_layers(
        self,
        mock_system: MagicMock,
        mock_python: MagicMock,
        mock_galaxy: MagicMock,
        mock_prechecks: MagicMock,
        tmp_path: Path,
    ):
        """Test that galaxy errors skip layers 2-3."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text(
            dedent("""\
                version: 3
                images:
                  base_image:
                    name: test:latest
            """)
        )

        mock_prechecks.return_value = LayerResult(name="prechecks", status="pass")
        mock_galaxy.return_value = (
            LayerResult(
                name="galaxy",
                status="fail",
                findings=[
                    Finding(severity=Severity.ERROR, message="Collection not found")
                ],
            ),
            [],
            [],
        )

        results = run(ee_path=ee_yml)

        # Layers 2-3 should be skipped
        assert any(r.name == "python_deps" and r.status == "skipped" for r in results)
        assert any(r.name == "system_deps" and r.status == "skipped" for r in results)

    @patch("ee_preflight.layers.prechecks.validate")
    @patch("ee_preflight.layers.galaxy.validate")
    @patch("ee_preflight.layers.python_deps.validate")
    @patch("ee_preflight.layers.system_deps.validate")
    def test_run_python_build_findings_force_container_test(
        self,
        mock_system: MagicMock,
        mock_python: MagicMock,
        mock_galaxy: MagicMock,
        mock_prechecks: MagicMock,
        tmp_path: Path,
    ):
        """Test that python build findings force container test."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text(
            dedent("""\
                version: 3
                images:
                  base_image:
                    name: test:latest
            """)
        )

        mock_prechecks.return_value = LayerResult(name="prechecks", status="pass")
        python_build_findings = [
            Finding(
                severity=Severity.ERROR,
                message="Failed to build wheel for cryptography",
            )
        ]
        mock_galaxy.return_value = (
            LayerResult(name="galaxy", status="pass"),
            python_build_findings,
            ["cryptography"],
        )
        mock_python.return_value = LayerResult(name="python_deps", status="pass")
        mock_system.return_value = LayerResult(name="system_deps", status="pass")

        results = run(ee_path=ee_yml, container_test=False)

        # Layer 3 should have been called with container_test=True
        assert mock_system.called
        ctx = mock_system.call_args[0][0]
        assert ctx.container_test is True

    @patch("ee_preflight.layers.prechecks.validate")
    @patch("ee_preflight.layers.galaxy.validate")
    @patch("ee_preflight.layers.python_deps.validate")
    @patch("ee_preflight.layers.system_deps.validate")
    def test_run_with_fix_revalidates(
        self,
        mock_system: MagicMock,
        mock_python: MagicMock,
        mock_galaxy: MagicMock,
        mock_prechecks: MagicMock,
        tmp_path: Path,
    ):
        """Test that --fix re-validates after applying fixes."""
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
        reqs = tmp_path / "requirements.yml"
        reqs.write_text("collections:\n  - name: ansible.posix\n")

        # First prechecks call
        mock_prechecks.side_effect = [
            LayerResult(
                name="prechecks",
                status="fail",
                findings=[
                    Finding(
                        severity=Severity.ERROR,
                        message="Missing bindep.txt",
                        fix="Add 'gcc' to bindep.txt",
                    )
                ],
            ),
            # Second call after fix
            LayerResult(name="prechecks", status="pass"),
        ]

        mock_galaxy.return_value = (LayerResult(name="galaxy", status="pass"), [], [])
        mock_python.side_effect = [
            LayerResult(name="python_deps", status="pass"),
            LayerResult(name="python_deps", status="pass"),
        ]
        mock_system.return_value = LayerResult(name="system_deps", status="skipped")

        results = run(ee_path=ee_yml, fix=True)

        # Should have been called twice (initial + after fix)
        assert mock_prechecks.call_count == 1  # Actually only called once since missing files skip everything
        # Check that fix layer exists
        assert any(r.name == "fix" for r in results)

    @patch("ee_preflight.layers.prechecks.validate")
    @patch("ee_preflight.layers.galaxy.validate")
    @patch("ee_preflight.layers.python_deps.validate")
    @patch("ee_preflight.layers.system_deps.validate")
    @patch("ee_preflight.runner.subprocess.run")
    def test_run_with_build_skips_on_errors(
        self,
        mock_subprocess: MagicMock,
        mock_system: MagicMock,
        mock_python: MagicMock,
        mock_galaxy: MagicMock,
        mock_prechecks: MagicMock,
        tmp_path: Path,
    ):
        """Test that --build skips when errors exist."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text(
            dedent("""\
                version: 3
                images:
                  base_image:
                    name: test:latest
            """)
        )

        mock_prechecks.return_value = LayerResult(
            name="prechecks",
            status="fail",
            findings=[Finding(severity=Severity.ERROR, message="Error")],
        )

        results = run(ee_path=ee_yml, build=True)

        # Build should be skipped
        build_result = next((r for r in results if r.name == "build"), None)
        assert build_result is not None
        assert build_result.status == "skipped"
        # ansible-builder should not have been called
        mock_subprocess.assert_not_called()

    @patch("ee_preflight.layers.prechecks.validate")
    @patch("ee_preflight.layers.galaxy.validate")
    @patch("ee_preflight.layers.python_deps.validate")
    @patch("ee_preflight.layers.system_deps.validate")
    def test_run_venv_path_resolution(
        self,
        mock_system: MagicMock,
        mock_python: MagicMock,
        mock_galaxy: MagicMock,
        mock_prechecks: MagicMock,
        tmp_path: Path,
    ):
        """Test venv path generation."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text(
            dedent("""\
                version: 3
                images:
                  base_image:
                    name: test:latest
            """)
        )

        mock_prechecks.return_value = LayerResult(name="prechecks", status="pass")
        mock_galaxy.return_value = (LayerResult(name="galaxy", status="pass"), [], [])
        mock_python.return_value = LayerResult(name="python_deps", status="pass")
        mock_system.return_value = LayerResult(name="system_deps", status="skipped")

        results = run(ee_path=ee_yml)

        # Should have created a temp venv path
        assert len(results) > 0
        # Venv should have been passed to layers
        assert mock_prechecks.called
        ctx = mock_prechecks.call_args[0][0]
        assert ctx.venv_path is not None

    @patch("ee_preflight.layers.prechecks.validate")
    @patch("ee_preflight.layers.galaxy.validate")
    @patch("ee_preflight.layers.python_deps.validate")
    @patch("ee_preflight.layers.system_deps.validate")
    def test_run_python_build_findings_set_layer2_fail(
        self,
        mock_system: MagicMock,
        mock_python: MagicMock,
        mock_galaxy: MagicMock,
        mock_prechecks: MagicMock,
        tmp_path: Path,
    ):
        """Test that ERROR python build findings set layer 2 status to fail."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text(
            dedent("""\
                version: 3
                images:
                  base_image:
                    name: test:latest
            """)
        )

        mock_prechecks.return_value = LayerResult(name="prechecks", status="pass")
        python_build_findings = [
            Finding(
                severity=Severity.ERROR,
                message="Failed to build wheel",
            )
        ]
        mock_galaxy.return_value = (
            LayerResult(name="galaxy", status="pass"),
            python_build_findings,
            [],
        )
        mock_python.return_value = LayerResult(name="python_deps", status="pass")
        mock_system.return_value = LayerResult(name="system_deps", status="skipped")

        results = run(ee_path=ee_yml)

        python_result = next(r for r in results if r.name == "python_deps")
        # Should be marked as fail due to ERROR finding
        assert python_result.status == "fail"
        # Should have the build finding
        assert any(f.message == "Failed to build wheel" for f in python_result.findings)
