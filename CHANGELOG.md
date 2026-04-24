# Changelog

All notable changes to ee-preflight will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Versioning Guide

ee-preflight uses semantic versioning (MAJOR.MINOR.PATCH):

- **MAJOR**: Incompatible API changes or major architectural changes
  - Example: Removing a CLI flag, changing JSON output structure
- **MINOR**: New features added in a backwards-compatible manner
  - Example: Adding a new validation layer, new CLI flag
- **PATCH**: Backwards-compatible bug fixes
  - Example: Fixing a false positive, improving error messages

## [Unreleased]

Changes that are in development but not yet released.

---

## [0.1.0] - 2026-04-23

Initial public release of ee-preflight.

### Added

#### Core Validation Layers

- **Layer 0: Pre-checks** - Static validation of EE definition files
  - YAML syntax validation (via optional ansible-lint)
  - Missing dependency file detection
  - Undeclared build argument detection
  - Base image reference validation

- **Layer 1: Galaxy Resolution** - Collection installation and authentication
  - Collection resolution using `ade install`
  - Automation Hub authentication via AH_TOKEN
  - Automatic retry with exponential backoff for transient errors
  - Collection version conflict detection

- **Layer 2: Dependency Validation** - Python and system dependency analysis
  - Platform-aware system dependency checking
  - Undeclared dependency detection from collection metadata
  - Python build failure forwarding from Layer 1
  - Discovered requirements comparison against declared requirements

- **Layer 3: Container Wheel Test** - Real container environment validation
  - Pull base image and test Python wheel builds inside container
  - Automatic activation when Layer 1 detects Python build failures
  - RPM dependency resolution via `dnf provides` inside container
  - Cumulative retry logic for discovered system dependencies
  - Supports both podman and docker

#### CLI Features

- `--fix` flag to automatically apply fixes for discovered issues
- `--build` flag to run `ansible-builder build` after successful validation
- `--tag` flag for custom image tags with `--build`
- `--venv` flag to use an existing virtual environment
- `--keep-venv` flag to preserve temporary venv for debugging
- `--container-test` flag to explicitly enable Layer 3
- `--json` flag for machine-readable output
- `--verbose` flag to show passing checks and informational findings

#### Fixer Module

- Auto-create `bindep.txt` when missing system dependencies are found
- Append to existing dependency files without duplication
- Add dependency file references to `execution-environment.yml`
- Support for both file-based and inline dependency declarations
- Idempotent fixes (safe to run multiple times)

#### Container Runtime Abstraction

- Automatic detection of podman or docker
- Unified interface for container operations
- Image pull with authentication support
- Exec command execution inside containers
- Cleanup of temporary containers

#### Output Formats

- Human-readable console output with status icons (✓, ✗, ⚠, ℹ)
- JSON output for CI/CD integration
- Exit code 0 on success, 1 on errors
- Colored output with actionable fix suggestions

#### Developer Tools

- Comprehensive unit test suite (no external dependencies)
- Integration test suite marked with `@pytest.mark.integration`
- Type hints enforced via mypy
- Code quality enforced via ruff
- Test coverage reporting via pytest-cov

#### Documentation

- Comprehensive README with CLI reference and layer descriptions
- Design document explaining architectural decisions
- Build report with real-world failure examples
- CLAUDE.md with project structure and build commands

### Dependencies

- Python 3.11+ (tested on 3.11, 3.12, 3.13)
- pyyaml >= 6.0
- ansible-dev-environment >= 24.0.0

### Optional Dependencies

- ansible-lint >= 24.0.0 (for YAML linting in Layer 0)
- ansible-builder >= 3.0.0, < 3.1.0 (for `--build` flag)
- podman or docker (for Layer 3 container testing)

---

## Release Template

Use this template for future releases:

```markdown
## [X.Y.Z] - YYYY-MM-DD

Brief description of the release.

### Added
- New features

### Changed
- Changes to existing functionality

### Deprecated
- Features that will be removed in future versions

### Removed
- Features removed in this version

### Fixed
- Bug fixes

### Security
- Security-related fixes
```

---

## Upgrade Notes

### From Pre-release to 0.1.0

This is the first public release. If you were using a development version:

- No breaking changes
- All CLI flags remain the same
- JSON output format is now stable

---

[Unreleased]: https://github.com/leogallego/ee-preflight/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/leogallego/ee-preflight/releases/tag/v0.1.0
