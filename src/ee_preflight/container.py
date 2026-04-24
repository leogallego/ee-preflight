from __future__ import annotations

import shutil
import subprocess


class ContainerRuntime:
    def __init__(self, runtime: str | None = None) -> None:
        self.cmd = self._detect(runtime)

    def _detect(self, runtime: str | None = None) -> str:
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

    def pull(self, image: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [self.cmd, "pull", image],
            capture_output=True,
            text=True,
            timeout=300,
        )

    def run(self, image: str, command: str, timeout: int = 300) -> subprocess.CompletedProcess:
        return subprocess.run(
            [self.cmd, "run", "--rm", image, "sh", "-c", command],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    @property
    def available(self) -> bool:
        try:
            self._detect()
            return True
        except RuntimeError:
            return False
