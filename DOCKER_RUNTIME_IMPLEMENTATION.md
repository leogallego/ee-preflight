# Docker Runtime Support Implementation

## Summary

This document describes the implementation of Docker runtime support for ee-preflight Layer 3 (container wheel testing) as specified in ROADMAP Phase 1.2.

## Implementation Overview

The following changes have been made to support both Podman and Docker container runtimes:

### 1. Container Runtime Abstraction (`src/ee_preflight/container.py`)

**Changes:**
- Extended `ContainerRuntime.__init__()` to accept an optional `runtime` parameter
- Enhanced `_detect()` method to support both auto-detection and explicit runtime selection
- Auto-detection priority: podman -> docker -> fail with clear message
- Validation of runtime name (must be "podman" or "docker")
- Clear error messages when requested runtime is unavailable

**Key Features:**
- Auto-detection: `ContainerRuntime()` - prefers podman, falls back to docker
- Explicit selection: `ContainerRuntime(runtime="docker")` - forces specific runtime
- Validation: Rejects invalid runtime names with helpful error message
- Error handling: Clear messages when requested runtime is not found in PATH

### 2. CLI Changes (`src/ee_preflight/cli.py`)

**Added:**
- `--runtime {podman|docker}` flag with choices validation
- Help text explaining auto-detection behavior
- Parameter passing through to runner

**Usage:**
```bash
# Auto-detect (default)
ee-preflight my-ee.yml --container-test

# Force podman
ee-preflight my-ee.yml --container-test --runtime podman

# Force docker
ee-preflight my-ee.yml --container-test --runtime docker
```

### 3. Data Model Changes (`src/ee_preflight/models.py`)

**Added:**
- `runtime: str | None = None` field to `ValidateContext` dataclass
- Allows runtime preference to flow through validation pipeline

### 4. Runner Changes (`src/ee_preflight/runner.py`)

**Added:**
- `runtime` parameter to `run()` function
- Runtime parameter passed to `ValidateContext` instances
- Preserved across re-validation after fixes

### 5. Layer 3 Integration (`src/ee_preflight/layers/system_deps.py`)

**Changed:**
- `ContainerRuntime(ctx.runtime)` - passes runtime preference from context
- Error handling propagates runtime errors as Layer 3 findings

### 6. Unit Tests (`tests/unit/test_container.py`)

**New comprehensive test suite covering:**
- Auto-detection behavior (podman preferred)
- Docker fallback when podman unavailable
- Explicit runtime selection (both podman and docker)
- Invalid runtime name rejection
- Unavailable runtime error handling
- Command execution (pull, run with --rm)
- Timeout configuration
- Available property behavior

**Test Coverage:**
- Auto-detection scenarios
- Explicit runtime selection
- Error cases (invalid names, unavailable runtimes)
- Command construction and execution
- Timeout behavior

### 7. Integration Tests (`tests/integration/test_layer3.py`)

**Enhanced tests:**
- Auto-detection validation
- Explicit podman runtime test (skipped if podman not available)
- Explicit docker runtime test (skipped if docker not available)
- Invalid runtime error handling
- Unavailable runtime error propagation to Layer 3
- Error message validation

**Test Markers:**
- All tests marked with `@pytest.mark.integration`
- Runtime-specific tests skip when runtime not available
- Module skipped entirely if no runtime available

### 8. Documentation Updates (`README.md`)

**Added:**
- `--runtime` flag to CLI reference
- Description of auto-detection behavior
- Example usage with Docker runtime
- Container runtime selection explanation in Layer 3 section
- CI/CD use case documentation

## Runtime Detection Logic

```
1. If --runtime specified:
   a. Validate name is "podman" or "docker"
   b. Check if runtime exists in PATH
   c. Use it or fail with clear error

2. If no --runtime specified (auto-detect):
   a. Check for podman in PATH -> use if found
   b. Check for docker in PATH -> use if found
   c. Neither found -> fail with installation message
```

## Error Handling

### Invalid Runtime Name
```
RuntimeError: Invalid runtime 'invalid'. Use 'podman' or 'docker'.
```

### Requested Runtime Not Available
```
RuntimeError: Requested runtime 'docker' not found. Install docker or use --runtime to select another.
```

### No Runtime Available
```
RuntimeError: No container runtime found. Install podman or docker for --container-test
```

## Compatibility

- Both podman and docker support the same command interface:
  - `pull <image>` - Pull container image
  - `run --rm <image> sh -c <command>` - Run command in container with auto-cleanup
- No docker-specific adjustments needed due to interface compatibility
- Timeout handling works identically for both runtimes

## Testing Approach

### Unit Tests (No Runtime Required)
- Mock `shutil.which()` to simulate runtime availability
- Mock `subprocess.run()` to verify command construction
- Test all detection and error paths
- Verify timeout configuration

### Integration Tests (Runtime Required)
- Skip tests when specific runtime not available
- Test actual container operations with real runtimes
- Verify Layer 3 integration end-to-end
- Validate error propagation

### Testing Recommendations
```bash
# Run unit tests (no runtime needed)
pytest tests/unit/test_container.py -v

# Run integration tests (requires podman or docker)
pytest tests/integration/test_layer3.py -v -m integration

# Run all tests
pytest tests/ -v
```

## CI/CD Integration

For CI environments where only Docker is available:

```yaml
# Example CI configuration
script:
  - ee-preflight execution-environment.yml --container-test --runtime docker
```

For CI environments with Podman:

```yaml
# Example CI configuration (auto-detect will prefer podman)
script:
  - ee-preflight execution-environment.yml --container-test
```

## Files Modified

- `src/ee_preflight/container.py` - Runtime detection and abstraction
- `src/ee_preflight/cli.py` - CLI flag and argument parsing
- `src/ee_preflight/models.py` - ValidateContext data model
- `src/ee_preflight/runner.py` - Runner parameter passing
- `src/ee_preflight/layers/system_deps.py` - Layer 3 runtime integration
- `tests/unit/test_container.py` - Unit tests (NEW)
- `tests/integration/test_layer3.py` - Enhanced integration tests
- `README.md` - Documentation updates

## Future Enhancements

Potential future improvements:
- Support for additional runtimes (e.g., nerdctl, containerd)
- Runtime version detection and compatibility checking
- Runtime-specific optimizations
- Parallel container operations for multiple packages
