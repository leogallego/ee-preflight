"""Data models for ee-preflight validation.

This module defines the core data structures used throughout ee-preflight:
- Finding: A single validation issue or informational message
- LayerResult: Results from one validation layer
- EEDefinition: Parsed execution-environment.yml structure
- ValidateContext: Shared context passed to all validation layers
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Literal

LayerStatus = Literal["pass", "fail", "skipped"]


class Severity(Enum):
    """Severity level for validation findings.

    ERROR: Blocks successful validation (exit code 1)
    WARNING: Important issue but not blocking
    INFO: Informational message (only shown with --verbose)
    """

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Finding:
    """A single validation finding (error, warning, or info).

    Attributes:
        severity: Severity level (ERROR, WARNING, INFO)
        message: Human-readable description of the finding
        fix: Optional suggested fix (used by --fix)
        source: Optional source context (e.g., which collection requires a dep)
    """

    severity: Severity
    message: str
    fix: str | None = None
    source: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        """Convert to dictionary for JSON serialization."""
        return {
            "severity": self.severity.value,
            "message": self.message,
            "fix": self.fix,
            "source": self.source,
        }


@dataclass
class LayerResult:
    """Results from a single validation layer.

    Attributes:
        name: Layer identifier (prechecks, galaxy, python_deps, system_deps, fix, build)
        status: One of "pass", "fail", or "skipped"
        findings: List of findings discovered by this layer
    """

    name: str
    status: LayerStatus
    findings: list[Finding] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        """Check if this layer has any ERROR-level findings."""
        return any(f.severity == Severity.ERROR for f in self.findings)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "status": self.status,
            "findings": [f.to_dict() for f in self.findings],
        }


class DepFormat(Enum):
    """Format for dependency declarations in execution-environment.yml.

    FILE: Reference to an external file (e.g., dependencies: python: requirements.txt)
    INLINE: List embedded directly in YAML (e.g., dependencies: python: [pkg1, pkg2])
    """

    FILE = "file"
    INLINE = "inline"


@dataclass
class DepRef:
    """Reference to a dependency list (galaxy, python, or system).

    Attributes:
        format: Whether the deps are in a file or inline in the YAML
        file_path: Path to the dependency file (if format == FILE)
        entries: List of inline entries (if format == INLINE)
    """

    format: DepFormat
    file_path: Path | None = None
    entries: list[str | dict[str, Any]] = field(default_factory=list)


@dataclass
class EEDefinition:
    """Parsed execution-environment.yml definition.

    Attributes:
        path: Absolute path to execution-environment.yml
        ee_dir: Parent directory containing the EE definition
        version: EE schema version (1, 2, or 3)
        base_image: Container base image (from images.base_image.name or build_arg_defaults.EE_BASE_IMAGE)
        galaxy: Galaxy/collection dependencies (optional)
        python: Python dependencies (optional)
        system: System (RPM/bindep) dependencies (optional)
        build_steps: additional_build_steps from the EE definition
        build_files: additional_build_files from the EE definition
        options: options from the EE definition (e.g., package_manager_path)
        raw: Raw YAML dict from the EE file
    """

    path: Path
    ee_dir: Path
    version: int
    base_image: str
    galaxy: DepRef | None = None
    python: DepRef | None = None
    system: DepRef | None = None
    build_steps: dict[str, list[str]] = field(default_factory=dict)
    build_files: list[dict[str, str]] = field(default_factory=list)
    options: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def build_args(self) -> list[str]:
        """Extract ARG declarations from additional_build_steps.

        Scans build steps for lines starting with "ARG " and returns a list
        of argument names. These are passed to ansible-builder via --build-arg.

        Returns:
            List of ARG names declared in build steps
        """
        args: list[str] = []
        for step_list in self.build_steps.values():
            for step in step_list:
                if step.strip().startswith("ARG "):
                    arg_name = step.strip().split()[1].split("=")[0]
                    args.append(arg_name)
        return args


@dataclass
class ValidateContext:
    """Shared context passed to all validation layers.

    Attributes:
        ee: Parsed execution environment definition
        venv_path: Path to the venv used by ade install
        fix: Whether to apply auto-fixes (--fix)
        container_test: Whether to run Layer 3 container wheel test (--container-test)
        verbose: Whether to show INFO-level findings (--verbose)
    """

    ee: EEDefinition
    venv_path: Path
    fix: bool = False
    container_test: bool = False
    verbose: bool = False
    use_cache: bool = True
    cache_path: Path | None = None
    runtime: str | None = None
