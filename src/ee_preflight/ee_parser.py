"""Parser for execution-environment.yml files.

This module parses Ansible Execution Environment definition files and
extracts dependency references (galaxy, python, system), base image,
build steps, and other metadata. Supports EE schema versions 1-3.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .models import DepFormat, DepRef, EEDefinition


def parse_ee(ee_path: Path) -> EEDefinition:
    """Parse an execution-environment.yml file into an EEDefinition.

    Args:
        ee_path: Path to execution-environment.yml

    Returns:
        Parsed EEDefinition with dependency refs and metadata
    """
    ee_path = ee_path.resolve()
    ee_dir = ee_path.parent

    with open(ee_path) as f:
        raw = yaml.safe_load(f)

    version = raw.get("version", 1)
    base_image = _extract_base_image(raw, version)
    galaxy = _parse_dep(raw, "galaxy", ee_dir)
    python = _parse_dep(raw, "python", ee_dir)
    system = _parse_dep(raw, "system", ee_dir)
    build_steps = raw.get("additional_build_steps", {})
    build_files = raw.get("additional_build_files", [])
    options = raw.get("options", {})

    return EEDefinition(
        path=ee_path,
        ee_dir=ee_dir,
        version=version,
        base_image=base_image,
        galaxy=galaxy,
        python=python,
        system=system,
        build_steps=build_steps,
        build_files=build_files,
        options=options,
        raw=raw,
    )


def _extract_base_image(raw: dict, version: int) -> str:
    """Extract the base image from the EE definition.

    Schema version 3+ uses images.base_image.name.
    Earlier versions use build_arg_defaults.EE_BASE_IMAGE.

    Args:
        raw: Parsed YAML dict from execution-environment.yml
        version: EE schema version

    Returns:
        Base image name/tag
    """
    if version >= 3:
        return str(raw.get("images", {}).get("base_image", {}).get("name", ""))
    return str(raw.get("build_arg_defaults", {}).get("EE_BASE_IMAGE", ""))


def _parse_dep(raw: dict, dep_type: str, ee_dir: Path) -> DepRef | None:
    """Parse a dependency reference from the EE definition.

    Dependencies can be declared as:
    - String: path to a file (e.g., dependencies: python: requirements.txt)
    - List: inline entries (e.g., dependencies: python: [pkg1, pkg2])
    - Dict: galaxy collections dict (e.g., dependencies: galaxy: {collections: [...]})

    Args:
        raw: Parsed YAML dict from execution-environment.yml
        dep_type: Dependency type ("galaxy", "python", or "system")
        ee_dir: Directory containing the EE definition

    Returns:
        DepRef if dependencies exist, None otherwise
    """
    deps = raw.get("dependencies", {})
    value = deps.get(dep_type)

    if value is None:
        return None

    if isinstance(value, str):
        return DepRef(
            format=DepFormat.FILE,
            file_path=(ee_dir / value).resolve(),
        )

    if isinstance(value, list):
        return DepRef(format=DepFormat.INLINE, entries=value)

    if isinstance(value, dict):
        # Galaxy deps can be {collections: [...]}
        if "collections" in value:
            return DepRef(format=DepFormat.INLINE, entries=value["collections"])
        return DepRef(format=DepFormat.INLINE, entries=[])

    return None
