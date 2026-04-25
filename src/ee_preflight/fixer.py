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
import shutil
from pathlib import Path

import yaml

from .models import DepFormat, EEDefinition, Finding, pkg_name


def backup_ee_files(ee: EEDefinition) -> list[str]:
    """Create .bak copies of all EE-related files before --fix modifies them.

    Call once at the start of a --fix run. Only backs up files that exist.

    Returns:
        List of backup file paths created.
    """
    backed_up: list[str] = []
    files = [ee.path]
    for dep in (ee.galaxy, ee.python, ee.system):
        if dep and dep.format == DepFormat.FILE and dep.file_path and dep.file_path.exists():
            files.append(dep.file_path)
    for path in files:
        bak = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, bak)
        backed_up.append(str(bak))
    return backed_up


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


def apply_layer0_fixes(ee: EEDefinition, findings: list[Finding]) -> list[str]:
    """Apply Layer 0 fixes (stray collections, missing dep files).

    Called before Layer 1 so that the EE definition can be re-parsed with
    corrected structure before galaxy resolution proceeds.

    Args:
        ee: Parsed execution environment definition
        findings: Layer 0 findings to act on

    Returns:
        List of human-readable change descriptions
    """
    changes: list[str] = []
    has_stray = any(f.code == "stray_collections" for f in findings)
    if has_stray:
        _fix_stray_collections(ee, changes)
    for f in findings:
        if f.code == "missing_file" and f.source == "system":
            _fix_missing_dep_file(ee, "system", changes)
    return changes


def _collection_name(entry: str | dict) -> str:
    """Extract the collection name from an entry (string or dict)."""
    if isinstance(entry, dict):
        return entry.get("name", "")
    return str(entry)


def _fix_stray_collections(ee: EEDefinition, changes: list[str]) -> None:
    """Move root-level 'collections' into dependencies.galaxy.

    Handles four cases:
    A) galaxy has FILE format + file missing → create file from root collections
    B) galaxy has FILE format + file exists → merge into existing file
    C) galaxy has INLINE format → merge via _add_inline_deps
    D) galaxy is None → add inline deps block to EE YAML

    After merging, the root-level 'collections' key is removed from the EE file.

    Args:
        ee: Execution environment definition
        changes: List to append change descriptions to
    """
    root_collections = ee.raw.get("collections", [])
    if not root_collections:
        return

    if ee.galaxy is not None and ee.galaxy.format == DepFormat.FILE:
        if ee.galaxy.file_path and not ee.galaxy.file_path.exists():
            # Case A: FILE format, file missing – create from root collections
            seen: set[str] = set()
            deduped: list = []
            for c in root_collections:
                name = _collection_name(c)
                if name not in seen:
                    seen.add(name)
                    deduped.append(c)
            data = {"collections": deduped}
            ee.galaxy.file_path.write_text(yaml.dump(data, default_flow_style=False))
            changes.append(
                f"Created {ee.galaxy.file_path.name} from root-level collections"
            )
        elif ee.galaxy.file_path and ee.galaxy.file_path.exists():
            # Case B: FILE format, file exists – merge and deduplicate
            existing_data = yaml.safe_load(ee.galaxy.file_path.read_text()) or {}
            existing_list = existing_data.get("collections", [])
            existing_names = {_collection_name(e) for e in existing_list}
            new_entries = [
                c for c in root_collections
                if _collection_name(c) not in existing_names
            ]
            if new_entries:
                merged = existing_list + new_entries
                existing_data["collections"] = merged
                ee.galaxy.file_path.write_text(
                    yaml.dump(existing_data, default_flow_style=False)
                )
                names_str = ", ".join(_collection_name(c) for c in new_entries)
                changes.append(
                    f"Merged root collections into {ee.galaxy.file_path.name}: {names_str}"
                )
            else:
                changes.append(
                    f"Root collections already present in {ee.galaxy.file_path.name}"
                )
    elif ee.galaxy is not None and ee.galaxy.format == DepFormat.INLINE:
        # Case C: INLINE format – merge via _add_inline_deps
        entry_strings = [
            _collection_name(c) for c in root_collections
        ]
        _add_inline_deps(ee, "galaxy", entry_strings, changes)
    else:
        # Case D: No galaxy dep – add inline deps block
        _add_inline_galaxy_from_root(ee, root_collections, changes)

    # Remove root-level 'collections' key from the EE file
    _remove_root_key(ee.path, "collections")
    changes.append("Removed root-level 'collections' key from EE file")


def _add_inline_galaxy_from_root(
    ee: EEDefinition, collections: list, changes: list[str]
) -> None:
    """Add inline galaxy collections to an EE that has no galaxy dep.

    Inserts ``dependencies: galaxy: collections: [...]`` into the EE YAML.

    Args:
        ee: Execution environment definition
        collections: List of collection entries from root level
        changes: List to append change descriptions to
    """
    lines = ee.path.read_text().splitlines(keepends=True)

    # Find dependencies: line
    dep_line_idx = None
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("dependencies:"):
            dep_line_idx = i
            break

    if dep_line_idx is None:
        # No dependencies key – append one at end of file
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append("dependencies:\n")
        dep_line_idx = len(lines) - 1

    # Determine indentation
    base_indent = len(lines[dep_line_idx]) - len(lines[dep_line_idx].lstrip())
    child_indent = base_indent + 2

    # Find insertion point: after last child of dependencies
    last_dep_entry_idx = dep_line_idx
    for i in range(dep_line_idx + 1, len(lines)):
        stripped = lines[i].strip()
        if not stripped or stripped.startswith("#"):
            last_dep_entry_idx = i
            continue
        current_indent = len(lines[i]) - len(lines[i].lstrip())
        if current_indent > base_indent:
            last_dep_entry_idx = i
        else:
            break

    # Build the galaxy block
    insert_lines = [f"{' ' * child_indent}galaxy:\n"]
    insert_lines.append(f"{' ' * (child_indent + 2)}collections:\n")
    for c in collections:
        name = _collection_name(c)
        if name:
            insert_lines.append(f"{' ' * (child_indent + 4)}- name: {name}\n")

    for offset, new_line in enumerate(insert_lines):
        lines.insert(last_dep_entry_idx + 1 + offset, new_line)

    ee.path.write_text("".join(lines))
    names_str = ", ".join(_collection_name(c) for c in collections if _collection_name(c))
    changes.append(f"Added inline galaxy collections to EE: {names_str}")


def _fix_missing_dep_file(ee: EEDefinition, dep_type: str, changes: list[str]) -> None:
    """Create an empty dependency file for a missing reference.

    Args:
        ee: Execution environment definition
        dep_type: Dependency type ("galaxy", "python", or "system")
        changes: List to append change descriptions to
    """
    dep_ref = getattr(ee, dep_type, None)
    if dep_ref is None or dep_ref.file_path is None:
        return
    if dep_ref.file_path.exists():
        return
    dep_ref.file_path.touch()
    changes.append(f"Created empty {dep_ref.file_path.name}")


def _remove_root_key(yaml_path: Path, key: str) -> None:
    """Remove a root-level YAML key and all its indented content.

    Reads the file line by line, identifies the root-level key, skips it and
    all subsequent lines that are indented (belong to its block), then writes
    the remaining lines back.

    Args:
        yaml_path: Path to the YAML file
        key: Root-level key name to remove (e.g., "collections")
    """
    lines = yaml_path.read_text().splitlines(keepends=True)
    result: list[str] = []
    skipping = False

    for line in lines:
        stripped = line.strip()
        if skipping:
            # Keep skipping indented lines or blank lines within the block
            if not stripped:
                # Skip blank lines within the block
                continue
            indent = len(line) - len(line.lstrip())
            if indent > 0:
                continue
            # Hit another root-level key – stop skipping
            skipping = False

        if not skipping:
            # Check if this line starts the target root key
            if stripped.startswith(f"{key}:") or stripped == f"{key}":
                indent = len(line) - len(line.lstrip())
                if indent == 0:
                    skipping = True
                    continue
            result.append(line)

    yaml_path.write_text("".join(result))
