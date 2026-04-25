"""Container runtime abstraction for podman/docker operations.

This module provides a unified interface for interacting with container
runtimes (podman or docker). Used by Layer 3 to pull the base image and
run wheel build tests inside containers.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Literal


class ContainerRuntime:
    """Abstraction over podman/docker container runtimes.

    Automatically detects which runtime is available (prefers podman over docker)
    and provides a unified interface for pulling images and running commands.
    """

    def __init__(self, runtime: Literal["podman", "docker"] | None = None) -> None:
        """Initialize the runtime by detecting or validating a container engine.

        Args:
            runtime: Optional runtime preference ("podman" or "docker").
                    If None, auto-detect with priority: podman -> docker.

        Raises:
            RuntimeError: If no runtime is found or the requested runtime is unavailable.
        """
        self.engine = self._detect(runtime)

    def _detect(
        self, runtime: Literal["podman", "docker"] | None = None,
    ) -> Literal["podman", "docker"]:
        """Detect or validate container runtime.

        Args:
            runtime: Optional runtime preference ("podman" or "docker").
                    If None, auto-detect with priority: podman -> docker.

        Returns:
            The name of the detected/validated runtime command.

        Raises:
            RuntimeError: If no runtime is found or the requested runtime is unavailable.
        """
        if runtime:
            if runtime not in ("podman", "docker"):
                raise RuntimeError(f"Invalid runtime '{runtime}'. Use 'podman' or 'docker'.")
            if not shutil.which(runtime):
                raise RuntimeError(
                    f"Requested runtime '{runtime}' not found. "
                    f"Install {runtime} or use --runtime to select another."
                )
            return runtime

        # Auto-detect: podman first, then docker
        for cmd in ("podman", "docker"):
            if shutil.which(cmd):
                return cmd
        raise RuntimeError("No container runtime found. Install podman or docker for --container-test")

    def pull(self, image: str) -> subprocess.CompletedProcess[str]:
        """Pull a container image.

        Args:
            image: Image name/tag to pull

        Returns:
            CompletedProcess with stdout/stderr
        """
        return subprocess.run(
            [self.engine, "pull", image],
            capture_output=True,
            text=True,
            timeout=300,
        )

    def run(self, image: str, command: str, timeout: int = 300) -> subprocess.CompletedProcess[str]:
        """Run a command inside a container.

        Runs the command in a fresh container (--rm) via sh -c.

        Args:
            image: Image name/tag to run
            command: Shell command to execute inside the container
            timeout: Command timeout in seconds (default 300)

        Returns:
            CompletedProcess with stdout/stderr
        """
        return subprocess.run(
            [self.engine, "run", "--rm", image, "sh", "-c", command],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
