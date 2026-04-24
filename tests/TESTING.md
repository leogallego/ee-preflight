# Test Coverage for ee-preflight

This document describes the comprehensive test suite for ee-preflight.

## Test Organization

### Unit Tests (`tests/unit/`)

Unit tests use mocks and fixtures to test individual components in isolation without requiring external dependencies like `ade`, `podman`, or network access.

- **test_cli.py**: CLI argument parsing, output formatting (JSON/human), exit codes
- **test_container.py**: Container runtime detection, podman/docker fallback
- **test_ee_parser.py**: EE YAML parsing, v2/v3 support, inline/file dependencies
- **test_fixer.py**: Auto-fix logic for bindep.txt/requirements.txt, inline YAML modifications
- **test_models.py**: Data models, serialization, validation
- **test_runner.py**: Orchestration logic, layer execution, venv management

### Integration Tests (`tests/integration/`)

Integration tests verify end-to-end workflows and may require external tools.

- **test_layer0.py**: Pre-checks validation (YAML lint, file references)
- **test_layer1.py**: Galaxy resolution with `ade install`
- **test_layer2.py**: Python dependency diffing
- **test_layer3.py**: Container-based system dependency testing
- **test_fix_workflow.py**: `--fix` workflow (bindep.txt, requirements.txt, inline YAML)
- **test_build_workflow.py**: `--build` integration with ansible-builder
- **test_edge_cases.py**: Empty EE, mixed formats, non-standard Python versions

## Coverage Requirements

Target: 90%+ coverage across all modules.

### Key Areas Covered

#### 1. Fix Workflow (`test_fix_workflow.py`)

- Creating new bindep.txt/requirements.txt files
- Appending to existing dependency files
- Idempotency (no duplicate entries)
- Inline YAML modifications
- Mixed dependency formats (file + inline)
- YAML structure preservation (comments, indentation)

#### 2. Build Workflow (`test_build_workflow.py`)

- Successful build execution
- Custom tag support (`--tag`)
- Build failures and error reporting
- Timeout handling
- Build args from environment variables
- Skipping build on validation errors
- Integration with `--fix` flag
- Venv preservation with `--keep-venv`

#### 3. Edge Cases (`test_edge_cases.py`)

- Empty EE definitions (no dependencies)
- Inline-only dependencies
- File-only dependencies
- Mixed dependency formats
- Missing dependency files
- Non-standard Python versions
- Python deps with environment markers
- Container runtime detection and fallback
- Build args extraction (multiple ARGs, defaults)
- Venv lifecycle management

#### 4. CLI (`test_cli.py`)

- Argument parsing (--fix, --build, --tag, --venv, etc.)
- JSON output formatting
- Human-readable output formatting
- Verbose mode (INFO findings)
- Exit code handling (0 on success, 1 on errors)
- Missing EE file error

#### 5. Container Runtime (`test_container.py`)

- Podman preference over Docker
- Docker fallback
- Error when no runtime available
- Pull/run operations
- Timeout handling
- Custom timeout support

#### 6. Runner Orchestration (`test_runner.py`)

- Layer skipping on missing files
- Layer skipping on galaxy errors
- Python build findings forcing container test
- Fix workflow re-validation
- Build skipping on errors
- Venv path generation
- Python build findings setting layer 2 to fail

#### 7. Fixer Logic (`test_fixer.py`)

- Creating new dependency files
- Appending to existing files
- Idempotency checks
- Inline dependency modifications
- Dependency reference injection
- Package name normalization
- Handling version specifiers, extras, markers

## Running Tests

### Unit Tests Only

```bash
pytest tests/unit/ -v
```

### Integration Tests Only

```bash
pytest tests/integration/ -v -m integration
```

### All Tests

```bash
pytest tests/ -v
```

### Coverage Report

```bash
pytest tests/ -v --cov=ee_preflight --cov-report=term-missing --cov-report=html
```

The HTML coverage report will be generated in `htmlcov/index.html`.

## Test Fixtures

### Unit Test Fixtures (`tests/unit/conftest.py`)

- `tmp_ee_dir`: Minimal v3 EE with file-based galaxy deps
- `inline_ee_dir`: v3 EE with inline galaxy deps
- `ee_definition`: Parsed EEDefinition from tmp_ee_dir

### Integration Test Fixtures (`tests/integration/conftest.py`)

- `minimal_ee_path`: Path to minimal EE fixture
- `inline_ee_path`: Path to inline EE fixture

## Test Markers

- `@pytest.mark.integration`: Tests requiring external tools (ade, podman)

## Mocking Strategy

Unit tests mock:
- `subprocess.run` for external commands
- `shutil.which` for runtime detection
- Layer validation functions to isolate orchestration logic
- File system operations where appropriate

Integration tests use:
- Real file system operations
- Actual external tools when available
- Skip markers when tools unavailable

## Coverage Goals by Module

| Module | Target | Focus Areas |
|--------|--------|-------------|
| cli.py | 95%+ | All CLI flags, output formats, exit codes |
| runner.py | 90%+ | Orchestration, layer skipping, venv mgmt |
| fixer.py | 95%+ | All fix operations, inline/file formats |
| ee_parser.py | 95%+ | v2/v3 parsing, all dep formats |
| models.py | 100% | Data models, serialization |
| container.py | 90%+ | Runtime detection, operations |
| layers/*.py | 85%+ | Layer-specific validation logic |

## Future Enhancements

- Property-based testing for fixer idempotency
- Performance tests for large EE definitions
- Integration tests with real ansible-builder
- Cross-platform container runtime tests
