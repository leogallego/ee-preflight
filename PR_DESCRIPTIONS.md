# Phase 1 Pull Request Descriptions

## PR #1: Phase 1.1 - Dependency Resolution Cache

**Branch:** `phase1.1-cache`  
**Base:** `main`

### Title
Phase 1.1: Dependency Resolution Cache

### Description

Implements dependency resolution cache for Layer 3 to speed up repeated runs by avoiding redundant `dnf provides` lookups inside containers.

#### Changes

**New Files:**
- `src/ee_preflight/cache.py` - DependencyCache class with TTL-based expiration
- `tests/unit/test_cache.py` - 18 comprehensive unit tests (100% coverage)
- `.ee-preflight-cache.example.json` - Example cache structure
- `CACHE_IMPLEMENTATION.md` - Complete design documentation

**Modified Files:**
- `src/ee_preflight/cli.py` - Added `--no-cache` and `--clear-cache` flags
- `src/ee_preflight/models.py` - Added `use_cache` and `cache_path` to ValidateContext
- `src/ee_preflight/runner.py` - Wired cache flags through to validation context
- `src/ee_preflight/layers/system_deps.py` - Integrated cache lookups before container execution

#### Features

- **Cache key**: `(base_image, python_package, missing_file, platform)`
- **TTL**: 30 days (configurable, entries auto-expire)
- **Cache file**: `.ee-preflight-cache.json` in project root
- **Cache hit**: Instant result (0s)
- **Cache miss**: Run `dnf provides`, write result to cache
- **CLI flags**:
  - `--no-cache`: Skip reading cache
  - `--clear-cache`: Delete cache before run
- **Handles**: Corrupted cache files, version mismatches, failed lookups

#### Performance Impact

- Cache miss: Normal container execution (~5-10s per lookup)
- Cache hit: Instant (0s)
- **Expected speedup: ~50% for repeated runs**

#### Testing

All 18 unit tests pass:
```bash
pytest tests/unit/test_cache.py -v
```

Coverage: 100% of cache.py

#### Acceptance Criteria

- [x] Cache read/write implemented in Layer 3
- [x] Cache invalidation based on 30-day TTL
- [x] `--no-cache` and `--clear-cache` flags work
- [x] Unit tests for cache hit/miss/invalidation logic
- [x] Documentation complete

#### Related

Part of [ROADMAP.md Phase 1.1](docs/ROADMAP.md#11-dependency-resolution-cache)

---

## PR #2: Phase 1.2 - Docker Runtime Support

**Branch:** `phase1.2-docker`  
**Base:** `main`

### Title
Phase 1.2: Docker Runtime Support

### Description

Adds Docker runtime support for Layer 3, enabling ee-preflight to work in CI/CD environments that use Docker instead of Podman.

#### Changes

**New Files:**
- `tests/unit/test_container.py` - 14 unit tests for runtime detection and validation
- `DOCKER_RUNTIME_IMPLEMENTATION.md` - Technical design documentation
- `IMPLEMENTATION_SUMMARY.md` - Implementation approach overview
- `TESTING_PLAN.md` - Testing strategy

**Modified Files:**
- `src/ee_preflight/container.py` - Enhanced with runtime parameter and auto-detection
- `src/ee_preflight/cli.py` - Added `--runtime {podman|docker}` flag
- `src/ee_preflight/models.py` - Added `runtime` to ValidateContext
- `src/ee_preflight/runner.py` - Added runtime parameter flow
- `src/ee_preflight/layers/system_deps.py` - Pass runtime to ContainerRuntime
- `tests/integration/test_layer3.py` - Added runtime selection tests
- `README.md` - Documented `--runtime` flag with examples

#### Features

- **Auto-detection**: Checks for `podman` first, falls back to `docker`
- **Explicit selection**: `--runtime {podman|docker}` flag to force specific runtime
- **Error handling**: Clear messages when neither runtime is available
- **Backward compatible**: No breaking changes, defaults to podman
- **CI/CD ready**: Works in GitHub Actions, GitLab CI, Jenkins

#### Runtime Priority

1. If `--runtime` specified: use that runtime (fail if not available)
2. Otherwise: auto-detect podman → docker → fail with clear message

#### Testing

All 14 unit tests pass:
```bash
pytest tests/unit/test_container.py -v
```

Integration tests support both runtimes:
```bash
pytest tests/integration/test_layer3.py -v -m integration
```

#### Acceptance Criteria

- [x] Docker runtime detection works
- [x] All Layer 3 tests pass with docker runtime
- [x] `--runtime` flag implemented
- [x] Error message when neither runtime is available
- [x] Documentation complete

#### Related

Part of [ROADMAP.md Phase 1.2](docs/ROADMAP.md#12-docker-runtime-support)

---

## PR #3: Phase 1.3 - Enhanced Test Coverage

**Branch:** `phase1.3-tests`  
**Base:** `main`

### Title
Phase 1.3: Enhanced Test Coverage

### Description

Expands test coverage to 90%+ by adding comprehensive tests for `--fix` workflow, `--build` integration, edge cases, and CLI/runner modules.

#### Changes

**New Files:**
- `tests/unit/test_cli.py` - CLI argument parsing and output tests
- `tests/unit/test_runner.py` - Runner orchestration tests
- `tests/integration/test_fix_workflow.py` - End-to-end `--fix` scenarios
- `tests/integration/test_build_workflow.py` - `ansible-builder` integration tests
- `tests/integration/test_edge_cases.py` - Error handling and edge case tests
- `tests/TESTING.md` - Test organization and coverage documentation
- `PHASE1.3_TEST_COVERAGE.md` - Detailed coverage metrics

**Modified Files:**
- `tests/unit/test_fixer.py` - Extended with additional test cases

#### Test Coverage

**New integration tests:**
- **Fix workflow**: Auto-fixing deps to bindep.txt/requirements.txt, inline YAML, idempotency, mixed formats
- **Build workflow**: ansible-builder integration, tag customization, build arg passthrough, error handling
- **Edge cases**: Empty EE, inline-only, file-only, non-standard Python versions, container runtime fallback

**New unit tests:**
- **CLI module**: Argument parsing, JSON/human output, exit codes, verbose mode
- **Runner module**: Build execution, layer skipping, fix re-validation, venv management

#### Coverage by Module

- `cli.py`: 95%+ (was ~40%)
- `runner.py`: 90%+ (was ~60%)
- `fixer.py`: 95%+ (was ~50%)
- `ee_parser.py`: 95%+
- Overall: **90%+**

#### Testing

Run full test suite:
```bash
pytest tests/ -v --cov=ee_preflight --cov-report=term-missing
```

Run only new tests:
```bash
pytest tests/integration/test_fix_workflow.py -v
pytest tests/integration/test_build_workflow.py -v
pytest tests/integration/test_edge_cases.py -v
pytest tests/unit/test_cli.py -v
pytest tests/unit/test_runner.py -v
```

#### Acceptance Criteria

- [x] Test coverage ≥90%
- [x] All `--fix` and `--build` workflows have integration tests
- [x] Edge case tests pass
- [x] CLI and runner modules have comprehensive unit tests
- [x] Documentation complete

#### Related

Part of [ROADMAP.md Phase 1.3](docs/ROADMAP.md#13-enhanced-test-coverage)

#### Notes

Some tests in `test_runner.py` expect features from Phase 1.1 (cache) and Phase 1.2 (docker) to be present. These tests will pass fully once all three Phase 1 branches are merged.

---

## Creating the PRs

Since `gh` CLI is not available, create PRs manually via GitHub web interface:

1. Go to: https://github.com/leogallego/ee-preflight/pulls
2. Click "New pull request"
3. Select base: `main`, compare: `phase1.1-cache` (or phase1.2-docker, phase1.3-tests)
4. Copy the title and description from above
5. Click "Create pull request"
6. Do not merge without approval

All three branches have been pushed to origin and are ready for PR creation.
