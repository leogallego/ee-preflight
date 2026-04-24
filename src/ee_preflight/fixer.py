"""Auto-fix logic for --fix mode.

This module applies suggested fixes from validation findings back to the
execution-environment.yml file and dependency files. Currently supports:
- Adding missing system (bindep) dependencies
- Creating new dependency files if they don't exist
- Adding dependency references to execution-environment.yml

Python dependency fixes are not yet implemented (no layer produces them).
"""

from __future__ import annotations

import re

import yaml

from .models import DepFormat, EEDefinition, Finding, pkg_name


def apply_fixes(ee: EEDefinition, findings: list[Finding]) -> list[str]:
    """Apply auto-fixes to the EE definition and dependency files.

    Processes fix suggestions from validation findings and writes changes back
    to the filesystem. Returns a list of change descriptions for user feedback.

    Args:
        ee: Parsed execution environment definition
        findings: List of findings with fix suggestions

    Returns:
        List of human-readable change descriptions
    """
    changes: list[str] = []

    # Extract system (bindep) fixes from findings
    system_fixes = [f for f in findings if f.fix and "bindep" in f.fix.lower()]

    if system_fixes:
        entries = _extract_quoted_entries(system_fixes)
        _add_system_deps(ee, entries, changes)

    # NOTE: No layer currently produces fix text matching Python requirements.
    # _add_python_deps() is kept as a utility for future use when a layer
    # emits Python-specific fix suggestions.

    return changes


def _extract_quoted_entries(fixes: list[Finding]) -> list[str]:
    """Extract quoted dependency entries from fix suggestions.

    Parses fix text like "Add 'python3-devel' to bindep.txt" to extract
    the quoted package name.

    Args:
        fixes: Findings with fix suggestions

    Returns:
        List of extracted entries (e.g., package names)
    """
    entries: list[str] = []
    for f in fixes:
        if f.fix and "'" in f.fix:
            start = f.fix.index("'") + 1
            end = f.fix.index("'", start)
            entries.append(f.fix[start:end])
    return entries


def _add_system_deps(ee: EEDefinition, entries: list[str], changes: list[str]) -> None:
    """Add system (bindep) dependencies to the EE definition.

    Handles three cases:
    1. Existing FILE reference: append to the file
    2. Existing INLINE list: add to the inline list in execution-environment.yml
    3. No system deps: create bindep.txt and add reference to execution-environment.yml

    Args:
        ee: Execution environment definition
        entries: List of bindep entries to add
        changes: List to append change descriptions to
    """
    if not entries:
        return

    if ee.system and ee.system.format == DepFormat.FILE and ee.system.file_path:
        # Append to existing bindep file
        existing = ee.system.file_path.read_text() if ee.system.file_path.exists() else ""
        existing_names = {line.split()[0] for line in existing.splitlines() if line.strip()}
        new_entries = [e for e in entries if e.split()[0] not in existing_names]
        if new_entries:
            with open(ee.system.file_path, "a") as f:
                for entry in new_entries:
                    f.write(f"{entry}\n")
            changes.append(f"Added to {ee.system.file_path.name}: {', '.join(new_entries)}")

    elif ee.system and ee.system.format == DepFormat.INLINE:
        # Add to inline list in execution-environment.yml
        _add_inline_deps(ee, "system", entries, changes)

    else:
        # Create new bindep.txt and add reference to execution-environment.yml
        bindep_path = ee.ee_dir / "bindep.txt"
        with open(bindep_path, "w") as f:
            for entry in entries:
                f.write(f"{entry}\n")
        changes.append(f"Created {bindep_path.name} with: {', '.join(entries)}")
        _add_dep_ref_to_ee(ee, "system", "bindep.txt", changes)


def _add_python_deps(ee: EEDefinition, entries: list[str], changes: list[str]) -> None:
    """Add Python dependencies to the EE definition.

    Similar to _add_system_deps but for Python requirements. Currently not used
    as no layer emits Python fix suggestions, but kept for future use.

    Args:
        ee: Execution environment definition
        entries: List of Python requirement specs to add
        changes: List to append change descriptions to
    """
    if not entries:
        return

    if ee.python and ee.python.format == DepFormat.FILE and ee.python.file_path:
        existing = ee.python.file_path.read_text() if ee.python.file_path.exists() else ""
        existing_names = {
            pkg_name(line) for line in existing.splitlines() if line.strip() and not line.startswith("#")
        }
        new_entries = [e for e in entries if pkg_name(e) not in existing_names]
        if new_entries:
            with open(ee.python.file_path, "a") as f:
                for entry in new_entries:
                    f.write(f"{entry}\n")
            changes.append(f"Added to {ee.python.file_path.name}: {', '.join(new_entries)}")

    elif ee.python and ee.python.format == DepFormat.INLINE:
        _add_inline_deps(ee, "python", entries, changes)

    else:
        reqs_path = ee.ee_dir / "requirements.txt"
        with open(reqs_path, "w") as f:
            for entry in entries:
                f.write(f"{entry}\n")
        changes.append(f"Created {reqs_path.name} with: {', '.join(entries)}")
        _add_dep_ref_to_ee(ee, "python", "requirements.txt", changes)


def _add_dep_ref_to_ee(ee: EEDefinition, dep_type: str, filename: str, changes: list[str]) -> None:
    """Add a dependency file reference to execution-environment.yml.

    Inserts a line like "system: bindep.txt" under the dependencies: key.
    Creates the dependencies: key if it doesn't exist.

    Args:
        ee: Execution environment definition
        dep_type: Dependency type ("galaxy", "python", or "system")
        filename: Filename to reference (e.g., "bindep.txt")
        changes: List to append change descriptions to
    """
    lines = ee.path.read_text().splitlines(keepends=True)

    # Check if the dep_type already exists under dependencies
    with open(ee.path) as f:
        raw = yaml.safe_load(f)
    deps = raw.get("dependencies", {})
    if deps and dep_type in deps:
        return

    # Find the dependencies: line and determine insertion point
    dep_line_idx = None
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("dependencies:"):
            dep_line_idx = i
            break

    if dep_line_idx is None:
        # No dependencies key - append one at end of file
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append("dependencies:\n")
        dep_line_idx = len(lines) - 1

    # Determine the indentation used by existing entries under dependencies
    base_indent = len(lines[dep_line_idx]) - len(lines[dep_line_idx].lstrip())
    child_indent = base_indent + 2  # default child indent

    # Scan entries under dependencies: to find the last one
    last_dep_entry_idx = dep_line_idx
    for i in range(dep_line_idx + 1, len(lines)):
        stripped = lines[i].strip()
        if not stripped or stripped.startswith("#"):
            last_dep_entry_idx = i
            continue
        current_indent = len(lines[i]) - len(lines[i].lstrip())
        if current_indent > base_indent:
            child_indent = current_indent
            last_dep_entry_idx = i
        else:
            break

    # Insert the new dependency reference after the last entry
    new_line = f"{' ' * child_indent}{dep_type}: {filename}\n"
    lines.insert(last_dep_entry_idx + 1, new_line)

    ee.path.write_text("".join(lines))
    changes.append(f"Added '{dep_type}: {filename}' to {ee.path.name}")


def _add_inline_deps(ee: EEDefinition, dep_type: str, entries: list[str], changes: list[str]) -> None:
    """Add dependencies to an inline list in execution-environment.yml.

    Appends new entries to the existing list, preserving YAML formatting and indentation.
    Handles both plain lists (python/system) and galaxy dict format (collections: [...]).

    Args:
        ee: Execution environment definition
        dep_type: Dependency type ("galaxy", "python", or "system")
        entries: List of entries to add
        changes: List to append change descriptions to
    """
    # Verify the dep_type is inline (list or dict with a nested list)
    with open(ee.path) as f:
        raw = yaml.safe_load(f)
    deps = raw.get("dependencies", {})
    existing = deps.get(dep_type)

    # Galaxy deps can be a dict with a "collections" key containing a list;
    # python/system deps are plain lists.
    if isinstance(existing, dict):
        existing_list = existing.get("collections", [])
        is_galaxy_dict = True
    elif isinstance(existing, list):
        existing_list = existing
        is_galaxy_dict = False
    else:
        return

    # Filter out entries already present
    existing_set = set(str(e) for e in existing_list)
    new_entries = [e for e in entries if e not in existing_set]
    if not new_entries:
        return

    lines = ee.path.read_text().splitlines(keepends=True)

    # Find the dep_type key under dependencies
    dep_line_idx = None
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("dependencies:"):
            dep_line_idx = i
            break

    if dep_line_idx is None:
        return

    # Find the dep_type: line under dependencies
    type_line_idx = None
    base_indent = len(lines[dep_line_idx]) - len(lines[dep_line_idx].lstrip())
    for i in range(dep_line_idx + 1, len(lines)):
        stripped = lines[i].strip()
        if not stripped or stripped.startswith("#"):
            continue
        current_indent = len(lines[i]) - len(lines[i].lstrip())
        if current_indent <= base_indent:
            break  # left the dependencies block
        if re.match(rf"^\s+{re.escape(dep_type)}\s*:", lines[i]):
            type_line_idx = i
            break

    if type_line_idx is None:
        return

    # For galaxy dict format, find the "collections:" subkey line
    search_start = type_line_idx
    if is_galaxy_dict:
        type_indent = len(lines[type_line_idx]) - len(lines[type_line_idx].lstrip())
        for i in range(type_line_idx + 1, len(lines)):
            stripped = lines[i].strip()
            if not stripped or stripped.startswith("#"):
                continue
            current_indent = len(lines[i]) - len(lines[i].lstrip())
            if current_indent <= type_indent:
                break
            if re.match(r"^\s+collections\s*:", lines[i]):
                search_start = i
                break

    # Find the last list item (- entry) under this dep_type (or collections subkey)
    search_indent = len(lines[search_start]) - len(lines[search_start].lstrip())
    item_indent = search_indent + 2  # default
    last_item_idx = search_start
    for i in range(search_start + 1, len(lines)):
        stripped = lines[i].strip()
        if not stripped or stripped.startswith("#"):
            last_item_idx = i
            continue
        current_indent = len(lines[i]) - len(lines[i].lstrip())
        if current_indent <= search_indent:
            break  # left the block
        if stripped.startswith("- "):
            item_indent = current_indent
            last_item_idx = i

    # Insert new entries after the last list item
    insert_lines = [f"{' ' * item_indent}- {entry}\n" for entry in new_entries]
    for offset, new_line in enumerate(insert_lines):
        lines.insert(last_item_idx + 1 + offset, new_line)

    ee.path.write_text("".join(lines))
    changes.append(f"Added to {ee.path.name} [{dep_type}]: {', '.join(new_entries)}")
