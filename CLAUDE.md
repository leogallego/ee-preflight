# CLAUDE.md

## Project Overview

ee-preflight is a Python CLI tool that validates Ansible Execution Environment
definitions before running ansible-builder. It runs 4 validation layers
(prechecks, galaxy resolution, dependency validation, container wheel test)
and reports all issues in a single pass.

## Build Commands

    pip install -e ".[dev]"          # install in dev mode
    pytest tests/unit/ -v            # run unit tests
    pytest tests/ -v -m integration  # run integration tests (needs ade + podman)
    ruff check src/ tests/           # lint
    mypy src/ee_preflight/           # type check

## Architecture

src/ee_preflight/
    cli.py         -- arg parsing, output formatting
    runner.py      -- orchestrates layers, manages venv lifecycle
    models.py      -- Finding, LayerResult, Severity, EEDefinition
    ee_parser.py   -- parse execution-environment.yml
    fixer.py       -- --fix: write missing deps back to EE files
    container.py   -- ContainerRuntime abstraction (podman/docker)
    layers/
        prechecks.py    -- Layer 0: YAML lint, file refs, build args
        galaxy.py       -- Layer 1: ade install for collection resolution
        python_deps.py  -- Layer 2: discovered dep diffing
        system_deps.py  -- Layer 3: container wheel build test

## Key Design Decisions

- Uses `ade install` (not `ansible-galaxy`) for Layer 1
- Uses ade's discovered_requirements.txt (not `ansible-builder introspect`) for Layer 2
- All RPM resolution happens inside the target container (Layer 3), not on the host
- `from __future__ import annotations` in all modules (3.9-compat, minimum target is 3.11)
- Core dependencies: pyyaml, ansible-dev-environment (ade), ansible-lint

## Testing

Unit tests must not require ade, podman, or network. Use fixtures and mocks.
Integration tests are marked with @pytest.mark.integration.
