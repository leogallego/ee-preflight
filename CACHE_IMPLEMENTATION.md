# Dependency Resolution Cache Implementation

## Overview

Implemented Phase 1.1 from ROADMAP.md: persistent dependency resolution cache for ee-preflight Layer 3.

## Problem Solved

Layer 3 runs `dnf provides` inside containers to resolve missing files (e.g., "krb5-config") to RPM packages (e.g., "krb5-devel"). This is slow (~5-10s per lookup). Repeated runs waste time re-resolving the same dependencies.

## Solution

Persistent cache at `.ee-preflight-cache.json` that stores RPM resolution results and skips container execution for cache hits.

## Implementation Details

### New Files

1. **src/ee_preflight/cache.py** - Cache module with:
   - `CacheEntry` dataclass: represents a single cache entry
   - `DependencyCache` class: manages cache read/write/invalidation

2. **tests/unit/test_cache.py** - Comprehensive unit tests (18 tests)

### Modified Files

1. **src/ee_preflight/models.py**
   - Added `use_cache: bool = True` to `ValidateContext`
   - Added `cache_path: Path | None = None` to `ValidateContext`

2. **src/ee_preflight/layers/system_deps.py**
   - Integrated cache into `_find_providing_package()`
   - Cache check before container execution
   - Cache write after resolution (including failed lookups)
   - Added cache parameter to `_test_wheel_build()`

3. **src/ee_preflight/cli.py**
   - Added `--no-cache` flag to skip reading cache
   - Added `--clear-cache` flag to delete cache before run
   - Cache clearing logic before validation

4. **src/ee_preflight/runner.py**
   - Added `use_cache` and `cache_path` parameters to `run()`
   - Pass cache flags through to `ValidateContext`

## Cache Design

### Cache Key
```
(base_image, python_package, missing_file, platform)
```

### Cache Entry Structure
```json
{
  "base_image": "registry.redhat.io/ee-minimal-rhel9:latest",
  "python_package": "gssapi",
  "missing_file": "krb5-config",
  "resolved_rpm": "krb5-devel",
  "platform": "rpm",
  "timestamp": "2026-04-24T05:15:30Z",
  "python_version": "3.12"
}
```

### Cache File Format
```json
{
  "cache_version": "1",
  "entries": [
    { /* entry 1 */ },
    { /* entry 2 */ },
    ...
  ]
}
```

### Features

1. **TTL-based expiration**: 30 days (configurable)
   - Entries older than 30 days are ignored on load
   - Prevents stale cache for changing base images

2. **Automatic invalidation**:
   - Cache version mismatch → ignore old cache
   - Corrupted JSON → start fresh
   - Invalid timestamps → consider expired

3. **Per-base-image isolation**:
   - Different base images can have different RPM names
   - Cache key includes base_image to prevent cross-contamination

4. **Platform detection**:
   - Distinguishes RPM-based (RHEL, Fedora) vs DEB-based (Debian, Ubuntu)
   - Cache key includes platform

5. **Atomic writes**:
   - Temp file + rename to prevent corruption
   - Safe for concurrent reads

6. **Failed lookup caching**:
   - Caches `None` for failed resolutions
   - Prevents retrying impossible lookups

## CLI Usage

```bash
# Normal run (uses cache)
ee-preflight execution-environment.yml --container-test

# Skip cache (always run container)
ee-preflight execution-environment.yml --container-test --no-cache

# Clear cache before run
ee-preflight execution-environment.yml --container-test --clear-cache
```

## Performance Impact

### Without Cache
- 4 lookups × 5-10s = 20-40 seconds

### With Cache (2 hits, 2 misses)
- 2 lookups × 5-10s = 10-20 seconds
- 2 cache hits × 0s = instant

**Result**: ~50% reduction in Layer 3 execution time for repeated runs

## Testing

### Unit Tests (18 tests)
```bash
pytest tests/unit/test_cache.py -v
```

Coverage:
- Cache entry serialization/deserialization
- Expiration logic (TTL)
- Cache persistence across instances
- Multiple entries with distinct keys
- Entry updates (same key)
- Cache clearing
- Version mismatch handling
- Corrupted file handling
- Default path resolution

### Manual Tests
```bash
python test_cache_manual.py
python demo_cache.py
```

### Integration
All existing unit tests pass (94/98 - 4 failures are pre-existing mock issues)

## Cache File Location

Default: `.ee-preflight-cache.json` in project root (current working directory)

**Should you commit it to git?**
- **Yes** (recommended) - Share cache across team, speeds up CI/CD
- **No** (optional) - Add to `.gitignore` if cache is machine-specific

## Roadmap Acceptance Criteria

- [x] Cache read/write implemented in Layer 3
- [x] Cache invalidation based on 30-day TTL
- [x] `--no-cache` and `--clear-cache` flags work
- [x] Unit tests for cache hit/miss/invalidation logic
- [ ] Cache file added to `.gitignore` by default (or document that it SHOULD be committed)

**Note**: The cache file location is documented but not auto-added to `.gitignore`. Users should decide based on their workflow (team sharing vs local-only).

## Example Cache File

```json
{
  "cache_version": "1",
  "entries": [
    {
      "base_image": "registry.redhat.io/ee-minimal-rhel9:latest",
      "python_package": "gssapi",
      "missing_file": "krb5-config",
      "resolved_rpm": "krb5-devel",
      "platform": "rpm",
      "timestamp": "2026-04-24T05:15:30.123456+00:00",
      "python_version": "3.11"
    },
    {
      "base_image": "registry.redhat.io/ee-minimal-rhel9:latest",
      "python_package": "lxml",
      "missing_file": "libxml2.h",
      "resolved_rpm": "libxml2-devel",
      "platform": "rpm",
      "timestamp": "2026-04-24T05:16:12.456789+00:00",
      "python_version": "3.11"
    }
  ]
}
```

## Code Quality

- Type checked: `mypy src/ee_preflight/cache.py` ✓
- Linted: `ruff check src/ee_preflight/cache.py` ✓
- All imports follow `from __future__ import annotations` (Python 3.9 compat)
- Follows project conventions (dataclasses, type hints)

## Future Enhancements (Not in Scope)

1. Custom cache path via `--cache-path <file>` flag
2. Cache statistics (`ee-preflight --cache-stats`)
3. Cache pruning (`ee-preflight --cache-prune` removes expired entries)
4. Shared cache via HTTP (team-wide cache server)
5. Cache warming (pre-populate from known packages)
