"""Unit tests for CLI module."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from textwrap import dedent
from unittest.mock import MagicMock, patch

import pytest

from ee_preflight.cli import _output_human, _output_json, main
from ee_preflight.models import Finding, LayerResult, Severity


class TestOutputJson:
    """Test JSON output formatting."""

    def test_output_json_pass(self, capsys):
        """Test JSON output for passing validation."""
        results = [
            LayerResult(
                name="prechecks",
                status="pass",
                findings=[
                    Finding(severity=Severity.INFO, message="All checks passed")
                ],
            ),
            LayerResult(name="galaxy", status="pass"),
        ]

        _output_json(Path("/fake/execution-environment.yml"), results)

        captured = capsys.readouterr()
        output = json.loads(captured.out)

        assert output["result"] == "pass"
        assert output["ee"] == "/fake/execution-environment.yml"
        assert len(output["layers"]) == 2
        assert output["layers"][0]["name"] == "prechecks"
        assert output["layers"][0]["status"] == "pass"

    def test_output_json_fail(self, capsys):
        """Test JSON output for failing validation."""
        results = [
            LayerResult(
                name="prechecks",
                status="fail",
                findings=[
                    Finding(severity=Severity.ERROR, message="File not found")
                ],
            ),
        ]

        _output_json(Path("/fake/execution-environment.yml"), results)

        captured = capsys.readouterr()
        output = json.loads(captured.out)

        assert output["result"] == "fail"
        assert output["layers"][0]["status"] == "fail"
        assert output["layers"][0]["findings"][0]["severity"] == "error"


class TestOutputHuman:
    """Test human-readable output formatting."""

    def test_output_human_pass(self, capsys):
        """Test human output for passing validation."""
        results = [
            LayerResult(
                name="prechecks",
                status="pass",
                findings=[
                    Finding(severity=Severity.INFO, message="All files found")
                ],
            ),
            LayerResult(name="galaxy", status="pass"),
        ]

        _output_human(Path("/fake/execution-environment.yml"), results, verbose=False)

        captured = capsys.readouterr()
        assert "ee-preflight" in captured.out
        assert "Layer 0: Pre-checks" in captured.out
        assert "PASS" in captured.out
        assert "0 error(s)" in captured.out

    def test_output_human_fail(self, capsys):
        """Test human output for failing validation."""
        results = [
            LayerResult(
                name="prechecks",
                status="fail",
                findings=[
                    Finding(
                        severity=Severity.ERROR,
                        message="File not found",
                        fix="Create the file",
                        source="prechecks",
                    )
                ],
            ),
        ]

        _output_human(Path("/fake/execution-environment.yml"), results, verbose=False)

        captured = capsys.readouterr()
        assert "FAIL" in captured.out
        assert "File not found" in captured.out
        assert "Create the file" in captured.out
        assert "(prechecks)" in captured.out

    def test_output_human_warnings(self, capsys):
        """Test human output includes warnings."""
        results = [
            LayerResult(
                name="galaxy",
                status="pass",
                findings=[
                    Finding(severity=Severity.WARNING, message="Deprecated collection")
                ],
            ),
        ]

        _output_human(Path("/fake/execution-environment.yml"), results, verbose=False)

        captured = capsys.readouterr()
        assert "Deprecated collection" in captured.out
        assert "1 warning(s)" in captured.out

    def test_output_human_verbose_shows_info(self, capsys):
        """Test verbose mode shows INFO findings."""
        results = [
            LayerResult(
                name="prechecks",
                status="pass",
                findings=[
                    Finding(severity=Severity.INFO, message="All files found")
                ],
            ),
        ]

        _output_human(Path("/fake/execution-environment.yml"), results, verbose=True)

        captured = capsys.readouterr()
        assert "All files found" in captured.out

    def test_output_human_non_verbose_hides_info(self, capsys):
        """Test non-verbose mode hides INFO findings."""
        results = [
            LayerResult(
                name="prechecks",
                status="pass",
                findings=[
                    Finding(severity=Severity.INFO, message="All files found")
                ],
            ),
        ]

        _output_human(Path("/fake/execution-environment.yml"), results, verbose=False)

        captured = capsys.readouterr()
        assert "All files found" not in captured.out

    def test_output_human_error_count(self, capsys):
        """Test that the summary shows the exact error and warning counts."""
        results = [
            LayerResult(
                name="prechecks",
                status="fail",
                findings=[
                    Finding(severity=Severity.ERROR, message="Missing file A"),
                    Finding(severity=Severity.ERROR, message="Missing file B"),
                    Finding(severity=Severity.WARNING, message="Deprecated format"),
                ],
            ),
        ]

        _output_human(Path("/fake/execution-environment.yml"), results, verbose=False)

        captured = capsys.readouterr()
        assert "2 error(s), 1 warning(s)" in captured.out

    def test_output_human_skipped_layer(self, capsys):
        """Test output for skipped layers."""
        results = [
            LayerResult(name="galaxy", status="skipped"),
        ]

        _output_human(Path("/fake/execution-environment.yml"), results, verbose=False)

        captured = capsys.readouterr()
        assert "skipped" in captured.out


class TestMain:
    """Test main CLI entry point."""

    @patch("ee_preflight.cli.run")
    def test_main_default_args(self, mock_run: MagicMock, tmp_path: Path):
        """Test main with minimal args."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text(
            dedent("""\
                version: 3
                images:
                  base_image:
                    name: registry.redhat.io/ee-minimal-rhel9:latest
            """)
        )

        mock_run.return_value = [LayerResult(name="prechecks", status="pass")]

        with patch.object(sys, "argv", ["ee-preflight", str(ee_yml)]), pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 0
        mock_run.assert_called_once()

    @patch("ee_preflight.cli.run")
    def test_main_with_fix(self, mock_run: MagicMock, tmp_path: Path):
        """Test main with --fix flag."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text("version: 3\nimages:\n  base_image:\n    name: test:latest\n")

        mock_run.return_value = [LayerResult(name="prechecks", status="pass")]

        with patch.object(sys, "argv", ["ee-preflight", str(ee_yml), "--fix"]), pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 0
        assert mock_run.call_args.kwargs["fix"] is True

    @patch("ee_preflight.cli.run")
    def test_main_with_build(self, mock_run: MagicMock, tmp_path: Path):
        """Test main with --build flag."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text("version: 3\nimages:\n  base_image:\n    name: test:latest\n")

        mock_run.return_value = [LayerResult(name="prechecks", status="pass")]

        with patch.object(sys, "argv", ["ee-preflight", str(ee_yml), "--build"]), pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 0
        assert mock_run.call_args.kwargs["build"] is True

    @patch("ee_preflight.cli.run")
    def test_main_with_tag(self, mock_run: MagicMock, tmp_path: Path):
        """Test main with --tag flag."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text("version: 3\nimages:\n  base_image:\n    name: test:latest\n")

        mock_run.return_value = [LayerResult(name="prechecks", status="pass")]

        with patch.object(
            sys, "argv", ["ee-preflight", str(ee_yml), "--build", "--tag", "my-ee:v1.0"]
        ), pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 0
        assert mock_run.call_args.kwargs["tag"] == "my-ee:v1.0"

    @patch("ee_preflight.cli.run")
    def test_main_with_container_test(self, mock_run: MagicMock, tmp_path: Path):
        """Test main with --container-test flag."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text("version: 3\nimages:\n  base_image:\n    name: test:latest\n")

        mock_run.return_value = [LayerResult(name="prechecks", status="pass")]

        with (
            patch.object(sys, "argv", ["ee-preflight", str(ee_yml), "--container-test"]),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 0
        assert mock_run.call_args.kwargs["container_test"] is True

    @patch("ee_preflight.cli.run")
    def test_main_with_venv_path(self, mock_run: MagicMock, tmp_path: Path):
        """Test main with --venv flag."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text("version: 3\nimages:\n  base_image:\n    name: test:latest\n")

        venv_path = tmp_path / "custom-venv"

        mock_run.return_value = [LayerResult(name="prechecks", status="pass")]

        with patch.object(
            sys, "argv", ["ee-preflight", str(ee_yml), "--venv", str(venv_path)]
        ), pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 0
        assert mock_run.call_args.kwargs["venv_path"] == venv_path

    @patch("ee_preflight.cli.run")
    def test_main_with_keep_venv(self, mock_run: MagicMock, tmp_path: Path):
        """Test main with --keep-venv flag."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text("version: 3\nimages:\n  base_image:\n    name: test:latest\n")

        mock_run.return_value = [LayerResult(name="prechecks", status="pass")]

        with (
            patch.object(sys, "argv", ["ee-preflight", str(ee_yml), "--keep-venv"]),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 0
        assert mock_run.call_args.kwargs["keep_venv"] is True

    @patch("ee_preflight.cli.run")
    def test_main_with_json_output(self, mock_run: MagicMock, tmp_path: Path, capsys):
        """Test main with --json flag."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text("version: 3\nimages:\n  base_image:\n    name: test:latest\n")

        mock_run.return_value = [LayerResult(name="prechecks", status="pass")]

        with patch.object(sys, "argv", ["ee-preflight", str(ee_yml), "--json"]), pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert "result" in output
        assert "layers" in output

    @patch("ee_preflight.cli.run")
    def test_main_exit_code_on_errors(self, mock_run: MagicMock, tmp_path: Path):
        """Test main exits with code 1 on validation errors."""
        ee_yml = tmp_path / "execution-environment.yml"
        ee_yml.write_text("version: 3\nimages:\n  base_image:\n    name: test:latest\n")

        mock_run.return_value = [
            LayerResult(
                name="prechecks",
                status="fail",
                findings=[Finding(severity=Severity.ERROR, message="Error")],
            )
        ]

        with patch.object(sys, "argv", ["ee-preflight", str(ee_yml)]), pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1

    def test_main_missing_ee_file(self, capsys):
        """Test main with non-existent EE file."""
        with patch.object(sys, "argv", ["ee-preflight", "/fake/missing.yml"]), pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "not found" in captured.err
