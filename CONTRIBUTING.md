# Contributing to ee-preflight

Thank you for your interest in contributing to ee-preflight! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Development Setup](#development-setup)
- [Running Tests](#running-tests)
- [Code Style](#code-style)
- [Submitting Changes](#submitting-changes)
- [Reporting Issues](#reporting-issues)
- [Project Structure](#project-structure)

## Development Setup

### Prerequisites

- Python 3.11 or higher (3.12 and 3.13 also supported)
- git
- podman or docker (optional, for Layer 3 integration tests)

### Initial Setup

1. Clone the repository:

   ```bash
   git clone https://github.com/leogallego/ee-preflight.git
   cd ee-preflight
   ```

2. Create a virtual environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install in development mode with all extras:

   ```bash
   pip install -e ".[dev,lint,build]"
   ```

   This installs:
   - Core dependencies (pyyaml, ansible-dev-environment)
   - Development tools (pytest, pytest-cov, ruff, mypy)
   - Optional extras (ansible-lint, ansible-builder)

4. Verify the installation:

   ```bash
   ee-preflight --help
   pytest --version
   ruff --version
   mypy --version
   ```

### Setting up Automation Hub Access (Optional)

If you need to test with collections from Red Hat Automation Hub:

1. Get an offline token from [console.redhat.com](https://console.redhat.com/ansible/automation-hub/token)
2. Export it as an environment variable:

   ```bash
   export AH_TOKEN=<your-offline-token>
   ```

## Running Tests

ee-preflight has two types of tests:

### Unit Tests

Unit tests run quickly and do not require external dependencies (no ade, podman, or network access). They use fixtures and mocks.

```bash
# Run all unit tests
pytest tests/unit/ -v

# Run with coverage
pytest tests/unit/ -v --cov=src/ee_preflight --cov-report=term-missing

# Run a specific test file
pytest tests/unit/test_fixer.py -v

# Run a specific test
pytest tests/unit/test_fixer.py::TestApplyFixes::test_apply_fixes_creates_bindep -v
```

### Integration Tests

Integration tests require external tools and are marked with `@pytest.mark.integration`. They need:
- ade (installed automatically with the package)
- podman or docker (for Layer 3 tests)
- Network access (to fetch collections from Galaxy/Automation Hub)

```bash
# Run all integration tests
pytest tests/ -v -m integration

# Run integration tests for a specific layer
pytest tests/integration/test_layer1.py -v

# Skip integration tests (run only unit tests)
pytest tests/unit/ -v
```

### Running All Tests

```bash
# Run everything (unit + integration)
pytest tests/ -v

# With coverage report
pytest tests/ -v --cov=src/ee_preflight --cov-report=html
# Open htmlcov/index.html in your browser
```

### Test Fixtures

Common fixtures are defined in `tests/unit/conftest.py` and `tests/integration/conftest.py`:

- `tmp_ee_dir`: Creates a temporary directory with a minimal execution-environment.yml
- `sample_ee`: Provides a parsed EEDefinition object
- Use these fixtures to avoid duplicating test setup code

## Code Style

ee-preflight follows strict code quality standards:

### Linting with Ruff

```bash
# Check all code
ruff check src/ tests/

# Auto-fix issues where possible
ruff check src/ tests/ --fix

# Format code
ruff format src/ tests/
```

Ruff is configured in `pyproject.toml` with:
- Line length: 120 characters
- Target: Python 3.11
- Selected rules: E, F, W, I, UP, B, SIM

### Type Checking with mypy

```bash
# Check type hints
mypy src/ee_preflight/
```

Type checking requirements:
- All functions must have type hints
- `from __future__ import annotations` must be at the top of every module
- `disallow_untyped_defs = true` is enforced

### Code Style Guidelines

1. **Imports**: Use ruff to organize imports automatically
   - Standard library imports first
   - Third-party imports second
   - Local imports last

2. **Type hints**: Required for all function signatures
   ```python
   from __future__ import annotations
   
   def validate_deps(ee: EEDefinition) -> list[Finding]:
       ...
   ```

3. **Docstrings**: Use for public functions and classes
   ```python
   def parse_ee(path: Path) -> EEDefinition:
       """Parse execution-environment.yml and return structured definition.
       
       Args:
           path: Path to execution-environment.yml file
           
       Returns:
           Parsed EE definition with resolved file paths
       """
   ```

4. **Error handling**: Prefer explicit error messages
   ```python
   if not ee_path.exists():
       raise FileNotFoundError(f"EE file not found: {ee_path}")
   ```

### Pre-commit Checklist

Before submitting a PR, ensure:

```bash
# 1. All tests pass
pytest tests/unit/ -v

# 2. No linting issues
ruff check src/ tests/

# 3. No type errors
mypy src/ee_preflight/

# 4. Code is formatted
ruff format src/ tests/
```

## Submitting Changes

### Pull Request Process

1. **Fork the repository** and create a feature branch:

   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/issue-number-description
   ```

2. **Make your changes** following the code style guidelines

3. **Add tests** for new functionality:
   - Unit tests are required for all new code
   - Integration tests are required for new validation layers or container logic

4. **Update documentation** if needed:
   - Update README.md for user-facing changes
   - Update CLAUDE.md for architecture changes
   - Add docstrings for new public APIs

5. **Run the pre-commit checklist** (see above)

6. **Commit your changes** with clear, descriptive messages:

   ```bash
   git add .
   git commit -m "Add support for custom registry authentication"
   ```

   Good commit messages:
   - Start with a verb in imperative mood: "Add", "Fix", "Update", "Remove"
   - Keep the first line under 72 characters
   - Add details in the body if needed

7. **Push to your fork**:

   ```bash
   git push origin feature/your-feature-name
   ```

8. **Create a Pull Request** on GitHub:
   - Use a clear, descriptive title
   - Reference any related issues: "Fixes #123"
   - Describe what changed and why
   - Include test results if relevant

### PR Review Process

- All PRs require passing CI checks (tests, linting, type checking)
- Maintainers will review your code and may request changes
- Once approved, your PR will be merged into the main branch

### What to Include in Your PR

- Clear description of the problem being solved
- Test coverage for new code
- Documentation updates for user-facing changes
- No unrelated changes (submit those separately)

## Reporting Issues

### Bug Reports

When reporting a bug, include:

1. **ee-preflight version**: `pip show ee-preflight`
2. **Python version**: `python --version`
3. **Operating system**: Linux distribution, macOS version, etc.
4. **Container runtime** (if relevant): `podman --version` or `docker --version`
5. **Command that failed**: The exact command you ran
6. **Expected behavior**: What you expected to happen
7. **Actual behavior**: What actually happened
8. **Minimal reproduction**: The smallest execution-environment.yml that triggers the issue
9. **Full output**: Include `--verbose` output if possible

Example:

```markdown
**Version**: ee-preflight 0.1.0, Python 3.11.8, Fedora 39

**Command**:
    ee-preflight my-ee/execution-environment.yml --container-test --verbose

**Expected**: Layer 3 should detect missing libxml2-devel

**Actual**: Layer 3 passes but ansible-builder build fails with missing headers

**Sample EE**: [attach execution-environment.yml]

**Output**: [attach full --verbose output]
```

### Feature Requests

When requesting a feature, include:

1. **Use case**: What problem are you trying to solve?
2. **Proposed solution**: How would you like it to work?
3. **Alternatives**: What workarounds are you using now?
4. **Impact**: How would this help other users?

### Questions

For questions about usage:
- Check the [README.md](README.md) first
- Look at the [examples/](examples/) directory for sample EEs
- Search [existing issues](https://github.com/leogallego/ee-preflight/issues)
- Open a new issue with the "question" label

## Project Structure

```
ee-preflight/
├── src/ee_preflight/
│   ├── cli.py           # Argument parsing and output formatting
│   ├── runner.py        # Orchestrates layers, manages venv lifecycle
│   ├── models.py        # Data classes: Finding, LayerResult, EEDefinition
│   ├── ee_parser.py     # Parse execution-environment.yml
│   ├── fixer.py         # --fix: write missing deps back to EE files
│   ├── container.py     # ContainerRuntime abstraction (podman/docker)
│   └── layers/
│       ├── prechecks.py    # Layer 0: YAML lint, file refs, build args
│       ├── galaxy.py       # Layer 1: ade install for collection resolution
│       ├── python_deps.py  # Layer 2: discovered dep diffing
│       └── system_deps.py  # Layer 3: container wheel build test
├── tests/
│   ├── unit/            # Fast tests, no external dependencies
│   └── integration/     # Tests requiring ade, podman, network
├── docs/
│   ├── design.md        # Architecture and design decisions
│   └── build-report.md  # Real-world build failures that motivated ee-preflight
└── examples/            # Sample EE definitions

```

### Key Design Decisions

- **ade over ansible-galaxy**: Uses `ade install` for Layer 1 because it provides discovered_requirements.txt with platform-specific markers
- **Container-based RPM resolution**: Layer 3 runs `dnf provides` inside the target container, not on the host
- **Future annotations**: All modules use `from __future__ import annotations` for Python 3.9 compatibility (even though minimum target is 3.11)
- **Single-pass validation**: All layers run in one pass and report all issues together

See [docs/design.md](docs/design.md) for more details.

## Development Tips

### Testing a Local Change

```bash
# Install your working copy
pip install -e .

# Test it on a real EE
ee-preflight path/to/execution-environment.yml --verbose

# Use --keep-venv to inspect what collections were installed
ee-preflight path/to/execution-environment.yml --keep-venv --verbose
ls -la /tmp/ade-venv-*/  # Find the temp venv
```

### Debugging Layer Issues

```bash
# Run with verbose output
ee-preflight my-ee/execution-environment.yml --verbose

# Get JSON output for programmatic inspection
ee-preflight my-ee/execution-environment.yml --json | jq

# Keep the venv to inspect installed collections
ee-preflight my-ee/execution-environment.yml --keep-venv --verbose
source <venv-path>/bin/activate
pip list | grep ansible
```

### Adding a New Validation Layer

1. Create a new file in `src/ee_preflight/layers/`
2. Implement a function that returns `LayerResult`
3. Add the layer to `runner.py`'s orchestration logic
4. Write unit tests in `tests/unit/`
5. Write integration tests in `tests/integration/`
6. Update README.md to document the new layer
7. Update CLAUDE.md with architecture notes

## License

By contributing to ee-preflight, you agree that your contributions will be licensed under the Apache-2.0 License.

## Questions?

If you have questions about contributing, open an issue with the "question" label or reach out to the maintainers.

Thank you for contributing!
