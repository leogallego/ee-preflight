"""Unit tests for container runtime abstraction."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ee_preflight.container import ContainerRuntime


class TestContainerRuntime:
    """Unit tests for ContainerRuntime class."""

    def test_auto_detect_podman_first(self):
        """Auto-detection should prefer podman over docker."""
        with patch("shutil.which") as mock_which:
            # Both available: podman should be chosen
            mock_which.side_effect = lambda cmd: cmd in ("podman", "docker")
            runtime = ContainerRuntime()
            assert runtime.engine == "podman"

    def test_auto_detect_docker_fallback(self):
        """Auto-detection should fall back to docker if podman unavailable."""
        with patch("shutil.which") as mock_which:
            # Only docker available
            mock_which.side_effect = lambda cmd: cmd == "docker"
            runtime = ContainerRuntime()
            assert runtime.engine == "docker"

    def test_auto_detect_no_runtime(self):
        """Auto-detection should fail when no runtime is available."""
        with patch("shutil.which", return_value=None), pytest.raises(
            RuntimeError,
            match="No container runtime found. Install podman or docker",
        ):
            ContainerRuntime()

    def test_explicit_podman(self):
        """Explicit podman runtime should be used when available."""
        with patch("shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/podman"
            runtime = ContainerRuntime(runtime="podman")
            assert runtime.engine == "podman"

    def test_explicit_docker(self):
        """Explicit docker runtime should be used when available."""
        with patch("shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/docker"
            runtime = ContainerRuntime(runtime="docker")
            assert runtime.engine == "docker"

    def test_explicit_invalid_name(self):
        """Invalid runtime name should raise error."""
        with pytest.raises(RuntimeError, match="Invalid runtime 'invalid'"):
            ContainerRuntime(runtime="invalid")

    def test_explicit_unavailable(self):
        """Requesting unavailable runtime should raise clear error."""
        with patch("shutil.which", return_value=None), pytest.raises(
            RuntimeError, match="Requested runtime 'podman' not found",
        ):
            ContainerRuntime(runtime="podman")

    def test_pull_command(self):
        """Pull should execute correct command."""
        with patch("shutil.which", return_value="/usr/bin/podman"), patch(
            "subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            runtime = ContainerRuntime()
            runtime.pull("quay.io/ansible/creator-ee:latest")

            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert args == ["podman", "pull", "quay.io/ansible/creator-ee:latest"]

    def test_run_command(self):
        """Run should execute correct command with --rm flag."""
        with patch("shutil.which", return_value="/usr/bin/docker"), patch(
            "subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            runtime = ContainerRuntime(runtime="docker")
            runtime.run("alpine:latest", "echo hello")

            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert args == ["docker", "run", "--rm", "alpine:latest", "sh", "-c", "echo hello"]

    def test_pull_timeout(self):
        """Pull should have 300s timeout."""
        with patch("shutil.which", return_value="/usr/bin/podman"), patch(
            "subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            runtime = ContainerRuntime()
            runtime.pull("test-image")

            assert mock_run.call_args[1]["timeout"] == 300

    def test_run_custom_timeout(self):
        """Run should accept custom timeout."""
        with patch("shutil.which", return_value="/usr/bin/podman"), patch(
            "subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            runtime = ContainerRuntime()
            runtime.run("test-image", "test-cmd", timeout=600)

            assert mock_run.call_args[1]["timeout"] == 600

    def test_run_default_timeout(self):
        """Run should use 300s timeout by default."""
        with patch("shutil.which", return_value="/usr/bin/podman"), patch(
            "subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            runtime = ContainerRuntime()
            runtime.run("test-image", "test-cmd")

            assert mock_run.call_args[1]["timeout"] == 300
