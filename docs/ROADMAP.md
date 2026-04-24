# ee-preflight Roadmap

**Current version:** 0.1.0 (Alpha)  
**Status:** Core validation engine complete (~90%), ready for production use  
**Last updated:** 2026-04-23

This roadmap outlines the evolution of ee-preflight from an internal validation tool to a comprehensive ecosystem for Ansible Execution Environment development.

---

## Phase 1: Production Readiness (v0.2.0)

**Goal:** Make ee-preflight production-ready for PyPI release and community adoption.

**Timeline:** 2-3 weeks

### 1.1 Dependency Resolution Cache

**Problem:** Layer 3 runs `dnf provides` for every missing file on every run. For common packages (e.g., `gssapi` → `krb5-devel`), this is redundant and slow.

**Solution:** Implement a local dependency cache at `.ee-preflight-cache.json`.

**Spec:**
- Cache structure:
  ```json
  {
    "cache_version": "1",
    "entries": [
      {
        "base_image": "registry.redhat.io/ansible-automation-platform-26/ee-minimal-rhel9:latest",
        "python_package": "gssapi",
        "missing_file": "krb5-config",
        "resolved_rpm": "krb5-devel",
        "platform": "rpm",
        "timestamp": "2026-04-23T10:15:30Z",
        "python_version": "3.12"
      }
    ]
  }
  ```
- **Cache key:** `(base_image, python_package, missing_file, platform)`
- **Invalidation:** Entries older than 30 days are ignored (base images change)
- **Cache location:** Project root (`.ee-preflight-cache.json`) — added to `.gitignore` by default (caches are machine/environment-specific)
- **Behavior:**
  - Layer 3 checks cache before running `dnf provides`
  - Cache hits skip container exec (instant results)
  - Cache misses run `dnf provides` and write to cache
  - Cache grows organically as team builds different EEs
- **CLI flags:**
  - `--no-cache`: skip reading cache (always run `dnf provides`)
  - `--clear-cache`: delete `.ee-preflight-cache.json` before run

**Acceptance criteria:**
- [ ] Cache read/write implemented in Layer 3
- [ ] Cache invalidation based on 30-day TTL
- [ ] `--no-cache` and `--clear-cache` flags work
- [ ] Cache file added to `.gitignore` by default
- [ ] Unit tests for cache hit/miss/invalidation logic

**Complexity:** Medium  
**Files affected:** `src/ee_preflight/layers/system_deps.py`, `src/ee_preflight/models.py`

---

### 1.2 Docker Runtime Support

**Problem:** Layer 3 currently only supports `podman`. Many CI environments (GitHub Actions, GitLab CI) default to `docker`.

**Solution:** Add `docker` as a container runtime option via the existing `ContainerRuntime` abstraction.

**Spec:**
- Extend `container.py` to auto-detect `docker` if `podman` is not available
- Runtime selection priority: `podman` → `docker` → fail with clear message
- Add `--runtime {podman|docker}` flag to force a specific runtime
- Both runtimes must support:
  - `pull <image>`
  - `run --rm <image> <cmd>`
  - `exec <container> <cmd>` (for multi-step Layer 3 tests)
- Docker-specific handling:
  - Use `docker run` instead of `podman run`
  - Adjust volume mount syntax if needed (should be compatible)
  - Handle Docker Desktop vs Docker Engine (socket paths)

**Acceptance criteria:**
- [ ] `docker` runtime detection works
- [ ] All Layer 3 tests pass with `docker` runtime
- [ ] `--runtime` flag implemented
- [ ] Integration tests run against both `podman` and `docker` in CI
- [ ] Error message when neither runtime is available

**Complexity:** Low (abstraction already exists)  
**Files affected:** `src/ee_preflight/container.py`, `src/ee_preflight/cli.py`

---

### 1.3 Enhanced Test Coverage

**Problem:** Current test coverage:
- Unit tests: parser, fixer, models ✓
- Integration tests: basic layer execution ✓
- **Missing:** `--fix` workflow tests, `--build` integration, edge cases

**Solution:** Expand test suite to 90%+ coverage.

**Spec:**

**New integration tests:**
1. **`--fix` workflow:**
   - Test auto-fixing missing system deps (append to `bindep.txt`)
   - Test auto-fixing missing Python deps (append to `requirements.txt`)
   - Test auto-fixing inline YAML deps
   - Test idempotency (running `--fix` twice produces same result)
   - Test mixed format EEs (galaxy in file, python inline)

2. **`--build` workflow:**
   - Test `--build` flag triggers `ansible-builder` after successful validation
   - Test `--build` with `--tag` custom tag
   - Test `--build` skipped when errors remain after `--fix`
   - Test build arg passthrough (`ARG AH_TOKEN` → `--build-arg AH_TOKEN`)

3. **Edge cases:**
   - Empty EE definition (no collections, no deps)
   - EE with only inline deps (no external files)
   - EE with only file-based deps (no inline)
   - Base image with non-standard Python version (e.g., 3.13)
   - Transient error retry logic (mock Galaxy 504 → retry → success)

4. **Container runtime tests:**
   - Test both `podman` and `docker` runtimes
   - Test missing container runtime error handling
   - Test Layer 3 skip when `--container-test` not passed and no build failures

**Unit test additions:**
- Platform detection edge cases (unusual base image names)
- Dependency cache hit/miss/invalidation logic
- Retry backoff timing validation
- JSON output schema validation

**Acceptance criteria:**
- [ ] Test coverage ≥90% (measured by pytest-cov)
- [ ] All `--fix` and `--build` workflows have integration tests
- [ ] Edge case tests pass
- [ ] CI runs full test suite (unit + integration)

**Complexity:** Medium  
**Files affected:** `tests/integration/`, `tests/unit/`, `.github/workflows/ci.yml`

---

### 1.4 Documentation & Packaging

**Problem:** Missing docstrings, no contributor guide, not published to PyPI.

**Solution:** Polish documentation and publish to PyPI.

**Spec:**

**Code documentation:**
- Add module-level docstrings to all Python files
- Add function/class docstrings for public APIs
- Document complex logic (e.g., transient error detection, platform matching, cumulative retry)
- Add inline comments for non-obvious code sections

**User documentation:**
- Create `CONTRIBUTING.md` (how to run tests, submit PRs, report issues)
- Create `CHANGELOG.md` (semantic versioning)
- Add troubleshooting guide to README (common errors + fixes)
- Document cache behavior in README
- Add examples/ directory with sample EE definitions

**PyPI packaging:**
- Publish to PyPI as `ee-preflight`
- Set up trusted publishing via GitHub Actions (OIDC)
- Add GitHub release automation (tag → build → publish)
- Add PyPI badge to README
- Add versioning via `setuptools-scm` (already in pyproject.toml)

**Acceptance criteria:**
- [ ] All public functions have docstrings
- [ ] `CONTRIBUTING.md` and `CHANGELOG.md` exist
- [ ] `examples/` directory with 3+ sample EEs
- [ ] Published to PyPI (test.pypi.org first)
- [ ] GitHub release automation works
- [ ] README has troubleshooting section

**Complexity:** Low  
**Files affected:** All `.py` files, README.md, new docs/, `.github/workflows/`

---

## Phase 2: Developer Experience (v0.3.0)

**Goal:** Make ee-preflight the easiest way to scaffold, validate, and build EEs.

**Timeline:** 3-4 weeks

### 2.1 `--init` Scaffolding Mode

**Problem:** Creating a new EE from scratch requires knowing the right `ansible-creator` commands and file structure.

**Solution:** Add `ee-preflight --init` to scaffold a new EE project with validation built in.

**Spec:**
```bash
ee-preflight --init my-new-ee [--template minimal|standard|hub]
```

**Behavior:**
1. Run `ansible-creator init execution_env --project my-new-ee`
2. Apply template customizations:
   - **minimal:** base image = `ee-minimal-rhel9`, no collections
   - **standard:** base image = `ee-supported-rhel9`, common collections (ansible.posix, community.general)
   - **hub:** base image = `ee-minimal-rhel9`, includes `AH_TOKEN` ARG, ansible.cfg for Automation Hub
3. Create `.ee-preflight-cache.json` (empty)
4. Add `.gitignore` with `tmp/`, `context/`, `*.log`
5. Add `README.md` with usage instructions
6. Run `ee-preflight <path>` validation on the scaffolded EE
7. Print next steps:
   ```
   ✓ Created my-new-ee/
   ✓ Validated execution-environment.yml

   Next steps:
     1. cd my-new-ee/
     2. Edit ansible-collections.yml to add your collections
     3. Run: ee-preflight execution-environment.yml --fix --build
   ```

**Acceptance criteria:**
- [ ] `--init` flag implemented
- [ ] Templates (minimal, standard, hub) work
- [ ] Scaffolded EE passes validation
- [ ] Integration test for `--init` workflow
- [ ] README template included

**Complexity:** Medium  
**Files affected:** `src/ee_preflight/cli.py`, new `src/ee_preflight/templates/`, tests/

**Dependencies:** `ansible-creator` in optional deps (already declared)

---

### 2.2 GitHub Action

**Problem:** CI pipelines need to run ee-preflight on every PR. No reusable action exists.

**Solution:** Create a GitHub Action wrapper.

**Spec:**

**Action file:** `.github/actions/ee-preflight/action.yml`

```yaml
name: 'ee-preflight validation'
description: 'Validate Ansible Execution Environment definitions'
inputs:
  ee-path:
    description: 'Path to execution-environment.yml'
    required: true
  fix:
    description: 'Auto-fix missing dependencies'
    required: false
    default: 'false'
  container-test:
    description: 'Enable Layer 3 container wheel tests'
    required: false
    default: 'false'
  ah-token:
    description: 'Automation Hub token (for authenticated collections)'
    required: false
runs:
  using: 'composite'
  steps:
    - name: Install ee-preflight
      shell: bash
      run: pip install ee-preflight

    - name: Run validation
      shell: bash
      env:
        AH_TOKEN: ${{ inputs.ah-token }}
      run: |
        FLAGS=""
        [[ "${{ inputs.fix }}" == "true" ]] && FLAGS="$FLAGS --fix"
        [[ "${{ inputs.container-test }}" == "true" ]] && FLAGS="$FLAGS --container-test"
        ee-preflight ${{ inputs.ee-path }} $FLAGS --json
```

**Example usage in user repos:**
```yaml
- uses: leogallego/ee-preflight/.github/actions/ee-preflight@v0.3
  with:
    ee-path: my-ee/execution-environment.yml
    fix: true
    container-test: true
    ah-token: ${{ secrets.AH_TOKEN }}
```

**Acceptance criteria:**
- [ ] Action published in `.github/actions/ee-preflight/`
- [ ] Action works in this repo's CI (dogfooding)
- [ ] README documents action usage
- [ ] Action supports all major flags (fix, container-test, json)

**Complexity:** Low  
**Files affected:** `.github/actions/ee-preflight/`, README.md

---

### 2.3 Watch Mode (`--watch`)

**Problem:** Developers iterate on EE definitions and want instant feedback without re-running the command.

**Solution:** Add `--watch` mode that re-runs validation on file changes.

**Spec:**
```bash
ee-preflight my-ee/execution-environment.yml --watch
```

**Behavior:**
- Watches for changes to:
  - `execution-environment.yml`
  - `requirements.yml` / `requirements.txt`
  - `bindep.txt`
  - Any files referenced in the EE definition
- On change detected:
  - Clear terminal
  - Re-run all layers
  - Print results
- Exit on `Ctrl+C`

**Implementation:**
- Use `watchdog` library (new dependency)
- Debounce changes (500ms delay to avoid multiple triggers)
- Preserve venv between runs (don't recreate on every change)

**Acceptance criteria:**
- [ ] `--watch` flag implemented
- [ ] File change detection works for all EE files
- [ ] Venv reused between watch iterations
- [ ] Clean terminal output on each run
- [ ] Integration test (mock file changes)

**Complexity:** Medium  
**Files affected:** `src/ee_preflight/cli.py`, `src/ee_preflight/runner.py`, `pyproject.toml`

**Dependencies:** Add `watchdog>=3.0` to core dependencies

---

### 2.4 IDE Integration (VS Code Extension)

**Problem:** Developers working in VS Code want inline validation and quick fixes.

**Solution:** Create a VS Code extension that wraps ee-preflight.

**Spec:**

**Extension features:**
1. **Inline diagnostics:**
   - Show errors/warnings as squiggly underlines in `execution-environment.yml`
   - Show missing deps in `requirements.yml`, `bindep.txt`
   - Diagnostics update on file save

2. **Quick fixes:**
   - "Add missing system dep to bindep.txt" code action
   - "Add missing Python dep to requirements.txt" code action
   - "Pin collection version" code action (for conflicts)

3. **Commands:**
   - "ee-preflight: Validate" — run validation, show in Output panel
   - "ee-preflight: Fix & Build" — run `--fix --build`
   - "ee-preflight: Show Cache" — open `.ee-preflight-cache.json`

4. **Settings:**
   - `ee-preflight.autoValidateOnSave` (default: true)
   - `ee-preflight.containerTest` (default: false)
   - `ee-preflight.pythonPath` (default: use workspace Python)

**Implementation:**
- Extension in TypeScript (VS Code Extension API)
- Calls `ee-preflight --json` in subprocess
- Parses JSON output → VS Code Diagnostic objects
- Code actions apply fixes using `TextEdit`

**Acceptance criteria:**
- [ ] Extension published to VS Code Marketplace
- [ ] Inline diagnostics work
- [ ] Quick fixes work
- [ ] Commands work
- [ ] Settings work
- [ ] README in extension with usage guide

**Complexity:** High (requires TS/VS Code API knowledge)  
**Files affected:** New repo or `vscode-extension/` directory

**Note:** This could be a separate project (`ee-preflight-vscode`) to keep core repo focused.

---

## Phase 3: Advanced Features (v0.4.0)

**Goal:** Add intelligence and optimization features for power users.

**Timeline:** 4-6 weeks

### 3.1 Heavy Collection Warnings

**Problem:** Some collections (e.g., `ansible.eda`) pull in heavy system dependencies. Users unknowingly add them to standard EEs, bloating image size.

**Solution:** Warn when "heavy" collections are detected and suggest alternatives.

**Spec:**

**Heavy collection database:**
```json
{
  "heavy_collections": [
    {
      "name": "ansible.eda",
      "system_deps": ["systemd-devel", "krb5-devel", "python3.12-devel"],
      "python_deps": ["systemd-python", "gssapi", "aiokafka"],
      "size_impact": "~150MB",
      "recommendation": "Consider a dedicated DE (Decision Environment) instead of bloating your standard EE."
    },
    {
      "name": "community.vmware",
      "system_deps": ["libxml2-devel", "libxslt-devel"],
      "python_deps": ["lxml", "pyvmomi"],
      "size_impact": "~80MB",
      "recommendation": "VMware collections require XML processing libraries. Use a vmware-specific EE if possible."
    }
  ]
}
```

**Behavior:**
- Layer 2 checks installed collections against heavy collection database
- If detected, report as WARNING:
  ```
  ⚠ Heavy collection detected: ansible.eda
    System deps: systemd-devel, krb5-devel, python3.12-devel
    Size impact: ~150MB
    → Consider a dedicated DE (Decision Environment) instead of bloating your standard EE.
  ```
- Flag is info-only (doesn't fail validation)
- Database is embedded in ee-preflight (JSON file in `src/ee_preflight/data/`)
- Can be overridden with `--allow-heavy-collections`

**Acceptance criteria:**
- [ ] Heavy collection database created (start with 5-10 collections)
- [ ] Layer 2 checks and warns
- [ ] `--allow-heavy-collections` suppresses warnings
- [ ] Unit tests for detection logic

**Complexity:** Low  
**Files affected:** `src/ee_preflight/layers/python_deps.py`, `src/ee_preflight/data/heavy_collections.json`

---

### 3.2 Base Image Delta Analysis (`ee-supported`)

**Problem:** `ee-supported` base images already include many collections. Users waste time declaring deps that are already present.

**Solution:** Detect base image type and warn about redundant declarations.

**Spec:**

**Base image inventory:**
- Maintain a mapping of `ee-supported` images → included collections
  ```json
  {
    "registry.redhat.io/ansible-automation-platform-26/ee-supported-rhel9:latest": {
      "collections": [
        "ansible.posix:1.5.4",
        "ansible.windows:1.14.0",
        "community.general:6.6.0",
        "..."
      ],
      "python_packages": ["jmespath", "pytz", "requests"],
      "updated": "2026-04-01"
    }
  }
  ```

**Behavior:**
- Layer 0 detects `ee-supported` base image
- Layer 2 compares user's collection requirements against base image inventory
- Report INFO for redundant collections:
  ```
  ℹ Collection already in base image: ansible.posix:1.5.4
    → Remove from requirements.yml to reduce build time (no-op install)
  ```
- Report WARNING if user pins older version than base:
  ```
  ⚠ ansible.posix:1.5.0 in requirements, but base image has 1.5.4
    → This will downgrade the collection (likely unintended)
  ```

**Challenges:**
- Base image inventory requires periodic updates (images change)
- Could scrape image metadata from registry API or inspect locally

**Acceptance criteria:**
- [ ] Base image inventory for `ee-supported-rhel9` (AAP 2.6)
- [ ] Layer 2 detects redundant collections
- [ ] Warnings for version downgrades
- [ ] `--ignore-base-image` flag to skip this check

**Complexity:** Medium (requires image metadata scraping)  
**Files affected:** `src/ee_preflight/layers/prechecks.py`, `src/ee_preflight/data/base_images.json`

---

### 3.3 Dependency Graph Visualization

**Problem:** Complex EEs have deep dependency chains. Hard to understand why a package is needed.

**Solution:** Generate a dependency graph showing collection → Python dep → system dep chains.

**Spec:**
```bash
ee-preflight my-ee/execution-environment.yml --graph deps.svg
```

**Output:** SVG diagram (or DOT file for Graphviz) showing:
```
ansible.eda (collection)
  └─> aiokafka[gssapi] (Python extra)
      ├─> gssapi (Python package)
      │   └─> krb5-devel (system package)
      └─> systemd-python (Python package)
          └─> systemd-devel (system package)
```

**Implementation:**
- Use `graphviz` library (new optional dependency)
- Parse dependency sources from Layer 2 (ade's annotated discovered files)
- Build graph structure
- Render to SVG, PNG, or DOT format

**Acceptance criteria:**
- [ ] `--graph <output>` flag implemented
- [ ] SVG output shows full dependency chain
- [ ] Collections colored differently than Python/system deps
- [ ] README documents graph feature

**Complexity:** Medium  
**Files affected:** `src/ee_preflight/cli.py`, new `src/ee_preflight/graph.py`, `pyproject.toml`

**Dependencies:** Add `graphviz>=0.20` to optional deps

---

### 3.4 Performance Profiling & Benchmarks

**Problem:** Unknown performance characteristics. Is Layer 1 slow because of Galaxy latency or local processing?

**Solution:** Add `--profile` mode that reports timing for each layer and subprocess.

**Spec:**
```bash
ee-preflight my-ee/execution-environment.yml --profile
```

**Output:**
```
Profiling Results:
  Layer 0: Pre-checks ................ 0.12s
  Layer 1: Galaxy Resolution ......... 45.32s
    - ade install .................... 44.87s
    - Output parsing ................. 0.45s
  Layer 2: Dependency Validation ..... 1.23s
    - Read discovered files .......... 0.08s
    - Diff system deps ............... 0.72s
    - Diff Python deps ............... 0.43s
  Layer 3: Container Wheel Test ...... 67.89s
    - Image pull ..................... 12.34s
    - Wheel builds (8 packages) ...... 52.11s
    - RPM resolution ................. 3.44s
  Total: 114.56s
```

**Implementation:**
- Add `--profile` flag
- Wrap each layer and subprocess call with timing
- Store timings in `LayerResult` metadata
- Print timing report at end (or include in JSON output)

**Acceptance criteria:**
- [ ] `--profile` flag implemented
- [ ] Timing report shows all layers and subprocesses
- [ ] JSON output includes timing metadata
- [ ] Unit tests for timing logic (mock subprocess calls)

**Complexity:** Low  
**Files affected:** `src/ee_preflight/runner.py`, `src/ee_preflight/models.py`, `src/ee_preflight/cli.py`

---

## Phase 4: Enterprise & Scale (v1.0.0)

**Goal:** Production-grade features for large organizations and CI/CD pipelines.

**Timeline:** 6-8 weeks

### 4.1 Multi-EE Validation (Monorepo Support)

**Problem:** Large repos have 10+ EEs. Running ee-preflight on each is tedious.

**Solution:** Add multi-EE mode that validates all EEs in a directory tree.

**Spec:**
```bash
ee-preflight --all my-ee-repo/
```

**Behavior:**
- Recursively find all `execution-environment.yml` files
- Validate each in parallel (up to 4 concurrent)
- Aggregate results:
  ```
  ee-preflight: scanning my-ee-repo/

  Found 12 EEs:
    ✓ my-ee-repo/netbox-ee/execution-environment.yml
    ✓ my-ee-repo/vmware-ee/execution-environment.yml
    ✗ my-ee-repo/aws-ee/execution-environment.yml (1 error)
    ...

  Summary: 11 passed, 1 failed
  ```
- Exit code 1 if any EE fails
- JSON output aggregates all results

**Acceptance criteria:**
- [ ] `--all` flag scans directory tree
- [ ] Parallel validation (configurable concurrency)
- [ ] Aggregated summary
- [ ] JSON output includes all EE results
- [ ] Integration test with multi-EE fixture

**Complexity:** Medium  
**Files affected:** `src/ee_preflight/cli.py`, `src/ee_preflight/runner.py`

---

### 4.2 Config File Support (`.ee-preflight.toml`)

**Problem:** Repeating CLI flags on every run is tedious. Need per-project defaults.

**Solution:** Add config file support.

**Spec:**

**Config file:** `.ee-preflight.toml` in EE directory or repo root

```toml
[ee-preflight]
container_test = true
keep_venv = true
verbose = false

[cache]
enabled = true
ttl_days = 30

[heavy_collections]
allow = ["ansible.eda"]  # suppress warnings for these

[fix]
auto_append_bindep = true
auto_append_python = false  # require manual Python dep adds
```

**Behavior:**
- CLI flags override config file values
- Search order: `.ee-preflight.toml` in EE dir → repo root → `~/.config/ee-preflight/config.toml`
- Validate config on load (error on unknown keys)

**Acceptance criteria:**
- [ ] Config file parsing implemented
- [ ] All CLI flags have config equivalents
- [ ] Search order works (EE dir → repo root → user home)
- [ ] `ee-preflight --init` creates default `.ee-preflight.toml`
- [ ] Unit tests for config loading

**Complexity:** Low  
**Files affected:** `src/ee_preflight/cli.py`, new `src/ee_preflight/config.py`, `pyproject.toml`

**Dependencies:** Add `tomli>=2.0` (Python 3.11+ has `tomllib` built-in, but use `tomli` for consistency)

---

### 4.3 Remote Registry Support (Private Registries)

**Problem:** Layer 3 assumes base images are on public registries. Enterprise users need private registry auth.

**Solution:** Add registry authentication support.

**Spec:**

**Auth methods:**
1. **Docker config:** Read from `~/.docker/config.json` (standard Docker auth)
2. **Environment vars:** `REGISTRY_AUTH_USER`, `REGISTRY_AUTH_PASSWORD`
3. **CLI flag:** `--registry-auth <file>` (custom auth config)

**Behavior:**
- Layer 3 detects registry from base image URL
- If registry is not public (not `docker.io`, `quay.io`, `registry.redhat.io`):
  - Check Docker config for auth
  - Fall back to env vars
  - Fall back to unauthenticated pull (may fail)
- Pass auth to `podman login` or `docker login` before `pull`

**Acceptance criteria:**
- [ ] Docker config auth works
- [ ] Env var auth works
- [ ] `--registry-auth` flag works
- [ ] Error message when auth fails (clear instructions)
- [ ] Integration test with mock private registry

**Complexity:** Medium  
**Files affected:** `src/ee_preflight/container.py`, `src/ee_preflight/cli.py`

---

### 4.4 CI/CD Artifacts & Reports

**Problem:** CI pipelines need structured output for reporting and artifact storage.

**Solution:** Generate HTML reports and machine-readable artifacts.

**Spec:**
```bash
ee-preflight my-ee/execution-environment.yml --report-html report.html --report-junit junit.xml
```

**Outputs:**

**HTML report (`report.html`):**
- Summary table (layers, pass/fail, timings)
- Detailed findings (errors, warnings, info)
- Dependency graph (inline SVG)
- Metadata (ee-preflight version, timestamp, base image)
- Styled with inline CSS (no external dependencies)

**JUnit XML (`junit.xml`):**
- Standard JUnit format for CI integration
- Each layer = test suite
- Each finding = test case (failures = errors, warnings = skipped)
- Integrates with GitHub Actions, GitLab CI, Jenkins

**JSON artifact (`results.json`):**
- Already supported with `--json`
- Add metadata: version, timestamp, duration, venv path

**Acceptance criteria:**
- [ ] `--report-html` generates HTML report
- [ ] `--report-junit` generates JUnit XML
- [ ] HTML report includes dependency graph (if `--graph` passed)
- [ ] JUnit XML validates against schema
- [ ] CI workflow uses JUnit XML for test reporting

**Complexity:** Medium  
**Files affected:** `src/ee_preflight/cli.py`, new `src/ee_preflight/reports.py`

---

### 4.5 Dependency Update Notifications

**Problem:** Collections and base images release new versions. Users don't know when to update.

**Solution:** Add `--check-updates` mode that checks for newer versions.

**Spec:**
```bash
ee-preflight my-ee/execution-environment.yml --check-updates
```

**Behavior:**
- Query Galaxy API for each pinned collection
- Compare pinned version vs latest version
- Report updates:
  ```
  ℹ Updates available:
    ansible.posix: 1.5.4 → 1.6.0 (minor update)
    community.general: 12.6.0 → 13.0.0 (major update)
    ansible.controller: 4.7.0 → 4.7.1 (patch update)
  ```
- Optionally auto-update with `--check-updates --fix`:
  - Update `requirements.yml` with latest versions
  - Re-validate after update

**Challenges:**
- Semantic versioning: distinguish major/minor/patch updates
- Automation Hub collections require auth to query

**Acceptance criteria:**
- [ ] `--check-updates` queries Galaxy API
- [ ] Reports available updates (major, minor, patch)
- [ ] `--check-updates --fix` auto-updates `requirements.yml`
- [ ] Re-validation after auto-update
- [ ] Handles Automation Hub collections (with AH_TOKEN)

**Complexity:** Medium  
**Files affected:** `src/ee_preflight/cli.py`, new `src/ee_preflight/updates.py`

---

### 4.6 Plugin System for Custom Layers

**Problem:** Organizations have custom validation needs (e.g., internal policy checks, license scanning).

**Solution:** Add a plugin system for custom validation layers.

**Spec:**

**Plugin API:**
```python
# plugins/license_check.py
from ee_preflight.models import LayerResult, Finding, Severity

def validate(context):
    """Custom layer: check collection licenses."""
    findings = []
    for collection in context.collections:
        if collection.license == "GPL":
            findings.append(Finding(
                severity=Severity.WARNING,
                message=f"{collection.name} uses GPL license",
                fix="Review license compatibility with your organization's policy",
                source=collection.name
            ))
    return LayerResult(name="license_check", status="pass", findings=findings)
```

**Plugin loading:**
```toml
# .ee-preflight.toml
[plugins]
enabled = ["license_check", "internal_policy"]
paths = ["./plugins"]
```

**Behavior:**
- Plugins run after Layer 3
- Plugin failures don't block `--build` (unless plugin sets `critical=True`)
- Plugins have access to full context (venv, parsed EE, installed collections)

**Acceptance criteria:**
- [ ] Plugin API defined and documented
- [ ] Plugin loading from config file
- [ ] Example plugins (license_check, internal_policy)
- [ ] Plugins run after core layers
- [ ] Plugin errors/warnings included in output

**Complexity:** High  
**Files affected:** `src/ee_preflight/runner.py`, `src/ee_preflight/config.py`, new `src/ee_preflight/plugins/`

---

## Phase 5: Community & Ecosystem (v1.1.0+)

**Goal:** Build community around ee-preflight and integrate with broader Ansible ecosystem.

**Timeline:** Ongoing

### 5.1 Ansible Galaxy Integration

**Problem:** Galaxy shows collection metadata but no validation status. Users don't know if a collection will build.

**Solution:** Integrate ee-preflight results into Galaxy badges.

**Spec:**
- Generate a "EE Preflight" badge for collections
- Badge states:
  - ✅ Passes ee-preflight (no system deps)
  - ⚠️ Requires system deps (list them)
  - ❌ Has build failures
- Host badge service at `https://ee-preflight.dev/badge/<collection>`
- Collection maintainers embed in README:
  ```markdown
  ![EE Preflight](https://ee-preflight.dev/badge/ansible.eda)
  ```

**Complexity:** High (requires hosted service)  
**Dependencies:** Badge service infrastructure

---

### 5.2 Devcontainer Auto-Detection

**Problem:** Running ee-preflight inside Ansible devcontainers may fail (docker-in-docker, podman socket paths).

**Solution:** Auto-detect devcontainer environment and adjust runtime paths.

**Spec:**
- Detect devcontainer: check for `/workspace/.devcontainer/` or `REMOTE_CONTAINERS=true` env var
- Adjust container runtime:
  - Use mounted Docker socket (`/var/run/docker.sock`)
  - Use `docker` CLI inside devcontainer (fallback to host podman socket)
- Warn if neither option is available

**Acceptance criteria:**
- [ ] Devcontainer detection works
- [ ] Docker socket mounting works
- [ ] Clear error message if container runtime unavailable

**Complexity:** Medium  
**Files affected:** `src/ee_preflight/container.py`

---

### 5.3 Ansible Dev Tools Integration

**Problem:** Ansible Dev Tools (`ansible-dev-tools` package) bundles `ade`, `ansible-lint`, etc. ee-preflight should integrate.

**Solution:** Add ee-preflight to the `ansible-dev-tools` bundle.

**Spec:**
- Propose ee-preflight as a dependency in `ansible-dev-tools`
- Coordinate with Red Hat Ansible team
- Ensure compatibility with other ADT tools

**Complexity:** Low (political/coordination)  
**Dependencies:** Red Hat Ansible team approval

---

### 5.4 Collection Best Practices Linting

**Problem:** Collection maintainers don't declare system deps in `meta/ee-bindep.txt`. This causes build failures.

**Solution:** Add linting for collection metadata.

**Spec:**
```bash
ee-preflight --lint-collection path/to/my-collection/
```

**Checks:**
- `meta/ee-bindep.txt` exists if collection has Python deps
- `meta/ee-requirements.txt` exists if collection has Python deps
- Python deps in `meta/ee-requirements.txt` are pinned
- System deps use platform markers (`[platform:rpm]`, `[platform:dpkg]`)

**Output:**
```
Linting ansible.myorg.mycollection:

  ✗ Missing meta/ee-bindep.txt
    → Python deps (requests, lxml) may require system packages
  ⚠ meta/ee-requirements.txt has unpinned deps: requests
    → Pin to specific version for reproducibility
```

**Acceptance criteria:**
- [ ] `--lint-collection` flag implemented
- [ ] Checks for missing metadata files
- [ ] Checks for unpinned Python deps
- [ ] Checks for missing platform markers
- [ ] Integration test with fixture collections

**Complexity:** Medium  
**Files affected:** `src/ee_preflight/cli.py`, new `src/ee_preflight/lint.py`

---

## Success Metrics

### Adoption
- [ ] 1,000+ PyPI downloads in first month
- [ ] 50+ GitHub stars
- [ ] 10+ community PRs
- [ ] Mentioned in Ansible blog or official docs

### Quality
- [ ] 90%+ test coverage
- [ ] Zero critical bugs in issue tracker
- [ ] <5 open issues at any time
- [ ] All releases have changelogs

### Performance
- [ ] Layer 1 (Galaxy) < 60s for 20 collections
- [ ] Layer 3 (container test) < 90s for 10 packages
- [ ] Total validation < 3 minutes for typical EE

### Community
- [ ] Featured in Ansible Community meeting
- [ ] Integrated into Ansible Dev Tools
- [ ] Used by Red Hat AAP team (internal validation)

---

## Non-Goals

What ee-preflight will NOT do:

1. **Replace ansible-builder** — ee-preflight validates, ansible-builder builds. They are complementary.
2. **Manage container images** — No image registry push/pull, tagging, or lifecycle management.
3. **Runtime EE orchestration** — No `ansible-runner` integration, no job execution.
4. **Collection development** — No scaffolding for collections (use `ansible-galaxy collection init`).
5. **Become a monorepo** — Keep focused on validation. IDE extensions, GitHub Actions, and badge services can be separate repos.

---

## Versioning Strategy

- **0.x.x:** Alpha/Beta — breaking changes allowed
- **1.0.0:** Stable API — semantic versioning enforced
- **1.x.x:** Minor releases — new features, no breaking changes
- **2.0.0+:** Major releases — only for breaking changes

---

## Maintainer Notes

### Prioritization
- **Phase 1 (Production Readiness):** Must-have for 1.0 release
- **Phase 2 (Developer Experience):** High value, prioritize `--init` and GitHub Action
- **Phase 3 (Advanced Features):** Nice-to-have, prioritize based on community demand
- **Phase 4 (Enterprise):** For large orgs, prioritize multi-EE and config file support
- **Phase 5 (Ecosystem):** Long-term, coordinate with Ansible team

### Community Contributions
Welcome contributions for:
- Heavy collection database expansion
- Base image inventory updates
- Plugin examples
- Bug fixes and documentation

Require maintainer approval for:
- New CLI flags (API surface expansion)
- New dependencies (bloat prevention)
- Breaking changes (version policy)

---

**Last updated:** 2026-04-23  
**Maintainer:** Leonardo Gallego  
**Feedback:** Open an issue at https://github.com/leogallego/ee-preflight/issues
