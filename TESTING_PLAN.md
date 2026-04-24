# Testing Plan for Docker Runtime Support

## Overview

This document outlines the testing strategy for the Docker runtime support implementation in ee-preflight Phase 1.2.

## Test Structure

### Unit Tests (`tests/unit/test_container.py`)

Unit tests verify the ContainerRuntime class behavior in isolation without requiring actual container runtimes.

**Test Categories:**

1. **Auto-detection tests**
   - `test_auto_detect_podman_first` - Verifies podman is preferred when both available
   - `test_auto_detect_docker_fallback` - Verifies docker is used when podman unavailable
   - `test_auto_detect_no_runtime` - Verifies error when no runtime available

2. **Explicit runtime selection tests**
   - `test_explicit_podman` - Verifies podman can be explicitly selected
   - `test_explicit_docker` - Verifies docker can be explicitly selected
   - `test_explicit_invalid_name` - Verifies invalid runtime names are rejected
   - `test_explicit_unavailable` - Verifies error when requested runtime unavailable

3. **Command execution tests**
   - `test_pull_command` - Verifies pull command construction
   - `test_run_command` - Verifies run command with --rm flag
   - `test_pull_timeout` - Verifies pull uses 300s timeout
   - `test_run_custom_timeout` - Verifies custom timeout support
   - `test_run_default_timeout` - Verifies default 300s timeout

4. **Property tests**
   - `test_available_property_true` - Verifies available returns True when runtime exists
   - `test_available_property_false` - Verifies available returns False when no runtime

**Running unit tests:**
```bash
pytest tests/unit/test_container.py -v
```

**Expected Result:** All tests should pass without requiring podman or docker installed.

### Integration Tests (`tests/integration/test_layer3.py`)

Integration tests verify end-to-end functionality with real container runtimes.

**Test Categories:**

1. **Existing tests (enhanced)**
   - `test_system_deps_skipped_without_flag` - Layer 3 skipped without --container-test
   - `test_system_deps_runs_with_flag` - Layer 3 runs with --container-test

2. **New auto-detection tests**
   - `test_runtime_auto_detection` - Verifies auto-detection works correctly

3. **New runtime-specific tests**
   - `test_runtime_explicit_podman` - Tests with explicit podman (skip if unavailable)
   - `test_runtime_explicit_docker` - Tests with explicit docker (skip if unavailable)

4. **New error handling tests**
   - `test_runtime_invalid` - Verifies invalid runtime rejection
   - `test_runtime_unavailable` - Verifies unavailable runtime error
   - `test_runtime_error_propagates_to_layer` - Verifies errors propagate to Layer 3

**Running integration tests:**
```bash
# All integration tests (requires podman or docker)
pytest tests/integration/test_layer3.py -v -m integration

# Only if you have podman
pytest tests/integration/test_layer3.py::test_runtime_explicit_podman -v

# Only if you have docker
pytest tests/integration/test_layer3.py::test_runtime_explicit_docker -v
```

**Expected Result:** Tests pass when corresponding runtime is available, skip otherwise.

## Manual Testing Scenarios

### Scenario 1: Auto-detection with Podman

**Prerequisites:** Podman installed, Docker not installed (or Docker removed from PATH temporarily)

**Command:**
```bash
ee-preflight tests/integration/fixtures/minimal-ee/execution-environment.yml --container-test --verbose
```

**Expected Behavior:**
- Should auto-detect and use podman
- Layer 3 should show "Pulling base image" message
- Should successfully pull and run containers with podman

### Scenario 2: Auto-detection with Docker

**Prerequisites:** Docker installed, Podman not installed (or Podman removed from PATH temporarily)

**Command:**
```bash
ee-preflight tests/integration/fixtures/minimal-ee/execution-environment.yml --container-test --verbose
```

**Expected Behavior:**
- Should auto-detect and use docker
- Layer 3 should show "Pulling base image" message
- Should successfully pull and run containers with docker

### Scenario 3: Explicit Podman Selection

**Prerequisites:** Podman installed

**Command:**
```bash
ee-preflight tests/integration/fixtures/minimal-ee/execution-environment.yml --container-test --runtime podman --verbose
```

**Expected Behavior:**
- Should use podman explicitly
- Should work even if docker is also available
- Layer 3 should complete successfully

### Scenario 4: Explicit Docker Selection

**Prerequisites:** Docker installed

**Command:**
```bash
ee-preflight tests/integration/fixtures/minimal-ee/execution-environment.yml --container-test --runtime docker --verbose
```

**Expected Behavior:**
- Should use docker explicitly
- Should work even if podman is also available
- Layer 3 should complete successfully

### Scenario 5: Invalid Runtime Name

**Prerequisites:** Any setup

**Command:**
```bash
ee-preflight tests/integration/fixtures/minimal-ee/execution-environment.yml --container-test --runtime invalid
```

**Expected Behavior:**
- Should fail with clear error message
- Error message should mention valid choices: "podman" or "docker"
- Exit code should be non-zero

### Scenario 6: Requested Runtime Unavailable

**Prerequisites:** Only podman installed (or only docker installed)

**Command:**
```bash
# If only podman is installed
ee-preflight tests/integration/fixtures/minimal-ee/execution-environment.yml --container-test --runtime docker

# If only docker is installed
ee-preflight tests/integration/fixtures/minimal-ee/execution-environment.yml --container-test --runtime podman
```

**Expected Behavior:**
- Layer 3 should fail with clear error
- Error message should mention the requested runtime is not found
- Should suggest installing the runtime or using --runtime to select another
- Exit code should be non-zero

### Scenario 7: No Runtime Available

**Prerequisites:** Neither podman nor docker installed (or both removed from PATH temporarily)

**Command:**
```bash
ee-preflight tests/integration/fixtures/minimal-ee/execution-environment.yml --container-test
```

**Expected Behavior:**
- Layer 3 should fail with clear error
- Error message should mention installing podman or docker
- Exit code should be non-zero

### Scenario 8: Runtime Priority

**Prerequisites:** Both podman and docker installed

**Command:**
```bash
ee-preflight tests/integration/fixtures/minimal-ee/execution-environment.yml --container-test --verbose
```

**Expected Behavior:**
- Should auto-detect and use podman (preferred over docker)
- Can verify by checking which binary is called (requires verbose logging or debug mode)

## CI/CD Testing Scenarios

### GitHub Actions with Docker

**Configuration:**
```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run ee-preflight with Docker
        run: |
          pip install -e .
          ee-preflight tests/integration/fixtures/minimal-ee/execution-environment.yml \
            --container-test --runtime docker
```

**Expected:** Should use Docker (pre-installed on GitHub Actions runners)

### GitLab CI with Docker

**Configuration:**
```yaml
test:
  image: python:3.11
  services:
    - docker:dind
  script:
    - pip install -e .
    - ee-preflight tests/integration/fixtures/minimal-ee/execution-environment.yml
        --container-test --runtime docker
```

**Expected:** Should use Docker service

### Testing with both runtimes in CI

**Configuration:**
```yaml
test-podman:
  script:
    - ee-preflight my-ee.yml --container-test --runtime podman

test-docker:
  script:
    - ee-preflight my-ee.yml --container-test --runtime docker
```

**Expected:** Both jobs should pass independently

## Error Message Validation

### Invalid Runtime
```
ee-preflight: error: argument --runtime: invalid choice: 'invalid' (choose from 'podman', 'docker')
```

### Unavailable Runtime (Layer 3 finding)
```
Layer 3: Container Wheel Test ✗
  ✗ Requested runtime 'docker' not found. Install docker or use --runtime to select another.
```

### No Runtime Available (Layer 3 finding)
```
Layer 3: Container Wheel Test ✗
  ✗ No container runtime found. Install podman or docker for --container-test
```

## Compatibility Testing

### Runtime Version Compatibility

Test with different versions of podman and docker:

- Podman 3.x
- Podman 4.x
- Docker 20.x
- Docker 24.x
- Docker 25.x

**Expected:** Should work with all modern versions (2020+)

### Platform Compatibility

Test on different platforms:

- Linux (Ubuntu, RHEL, Fedora)
- macOS (Docker Desktop, Podman Desktop)
- Windows (WSL2 with Docker Desktop)

**Expected:** Should work on all platforms where podman/docker CLI is available

## Performance Testing

### Metric 1: Runtime Detection Time

**Test:** Measure time for runtime detection

**Command:**
```bash
time ee-preflight --help
```

**Expected:** Detection should be instant (<1ms) as it's only PATH lookup

### Metric 2: Container Operations

**Test:** Compare podman vs docker for same operations

**Expected:** Both should complete Layer 3 in similar time (within 10% of each other)

## Regression Testing

Verify existing functionality still works:

1. Run all existing integration tests
2. Verify Layer 0-2 are unaffected
3. Verify --fix and --build flags work with new runtime support
4. Verify JSON output includes runtime information if needed

## Test Execution Checklist

- [ ] Unit tests pass without any runtime installed
- [ ] Integration tests pass with podman
- [ ] Integration tests pass with docker
- [ ] Auto-detection prefers podman when both available
- [ ] Explicit runtime selection works for both runtimes
- [ ] Invalid runtime names are rejected
- [ ] Clear error messages for unavailable runtimes
- [ ] No runtime available produces helpful error
- [ ] CLI help shows --runtime flag
- [ ] README documentation is accurate
- [ ] Existing tests still pass (no regressions)
- [ ] CI/CD examples work
