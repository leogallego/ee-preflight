# ee-preflight

[![PyPI version](https://badge.fury.io/py/ee-preflight.svg)](https://badge.fury.io/py/ee-preflight)
[![Python versions](https://img.shields.io/pypi/pyversions/ee-preflight.svg)](https://pypi.org/project/ee-preflight/)
[![License](https://img.shields.io/pypi/l/ee-preflight.svg)](https://github.com/leogallego/ee-preflight/blob/main/LICENSE)
[![CI Status](https://github.com/leogallego/ee-preflight/workflows/CI/badge.svg)](https://github.com/leogallego/ee-preflight/actions)

Pre-build validation for Ansible Execution Environments.

ee-preflight catches dependency conflicts, missing system packages, and
authentication issues **before** you run `ansible-builder build`. It runs
four validation layers in a single pass and reports every problem it finds,
together with actionable fix suggestions.

## Installation

```bash
pip install ee-preflight
```

This installs the `ee-preflight` CLI along with its two Python dependencies
(`pyyaml` and `ansible-dev-environment`). The `ade` CLI tool provided by
`ansible-dev-environment` is used internally for collection resolution.

### Optional extras

```bash
# YAML linting in Layer 0 (ansible-lint is checked at runtime, not required)
pip install ee-preflight[lint]

# Run ansible-builder after validation (--build flag)
pip install ee-preflight[build]

# All development tooling
pip install ee-preflight[dev]
```

## Quick start

```bash
ee-preflight path/to/execution-environment.yml
```

Example output:

```
ee-preflight: path/to/execution-environment.yml

Layer 0: Pre-checks ✓
Layer 1: Galaxy Resolution ✓
Layer 2: Dependency Validation ✓
  ⚠ Undeclared system dep: libxml2-devel
    → Add 'libxml2-devel [platform:rpm]' to bindep.txt
Layer 3: Container Wheel Test (skipped)

Result: PASS (0 error(s), 1 warning(s))
```

## CLI reference

```
ee-preflight [-h] [--fix] [--build] [--tag TAG] [--venv PATH]
             [--keep-venv] [--container-test] [--runtime {podman|docker}]
             [--json] [--verbose]
             ee_path
```

### Positional argument

| Argument | Description |
|----------|-------------|
| `ee_path` | Path to an `execution-environment.yml` file |

### Options

| Flag | Description |
|------|-------------|
| `--fix` | Auto-fix missing dependencies by writing them into the EE definition files (bindep.txt, requirements.txt, or inline in execution-environment.yml) |
| `--build` | Run `ansible-builder build` after all validation layers pass. Skipped if any errors remain. |
| `--tag TAG` | Image tag used by `--build`. Defaults to `<ee-directory-name>:latest`. |
| `--venv PATH` | Path to a virtual environment for collection installation. The venv is kept after the run. |
| `--keep-venv` | Keep the auto-created temporary venv after the run instead of cleaning it up. Useful for inspecting installed collections. |
| `--container-test` | Enable Layer 3: pull the base image and attempt to build wheels for source-only Python packages inside the container. Requires podman or docker. |
| `--runtime {podman\|docker}` | Force a specific container runtime. Default: auto-detect (podman preferred, then docker). Only used when `--container-test` is enabled. |
| `--json` | Output results as JSON instead of human-readable text. |
| `--verbose` | Show passing checks and informational findings that are hidden by default. |

### Examples

Run basic validation:

```bash
ee-preflight my-ee/execution-environment.yml
```

Run all layers including container wheel testing:

```bash
ee-preflight my-ee/execution-environment.yml --container-test
```

Auto-fix discovered issues, then build the image:

```bash
ee-preflight my-ee/execution-environment.yml --fix --build
```

Build with a custom image tag:

```bash
ee-preflight my-ee/execution-environment.yml --fix --build --tag my-registry.example.com/my-ee:v1.0
```

Get machine-readable output for CI pipelines:

```bash
ee-preflight my-ee/execution-environment.yml --json
```

Keep the temporary venv for debugging:

```bash
ee-preflight my-ee/execution-environment.yml --keep-venv --verbose
```

Use an existing venv (skips creating a temporary one):

```bash
ee-preflight my-ee/execution-environment.yml --venv .venv
```

Force Docker runtime (useful in CI environments where Docker is available but Podman is not):

```bash
ee-preflight my-ee/execution-environment.yml --container-test --runtime docker
```

## Validation layers

ee-preflight runs four validation layers in sequence. If a critical failure
occurs in an early layer (such as a missing dependency file), later layers
are skipped.

### Layer 0: Pre-checks

Static validation of the EE definition file itself. No network access or
external tools required (except optionally `ansible-lint`).

**What it catches:**

- YAML syntax and formatting issues (via `ansible-lint`, if installed)
- Missing dependency files referenced by `execution-environment.yml` (e.g., a `requirements.yml` that does not exist)
- Undeclared build arguments (`ARG` directives in `additional_build_steps` without a matching environment variable)
- Malformed base image references

### Layer 1: Galaxy resolution

Resolves and installs all Ansible collections declared in the EE definition
into a temporary virtual environment using `ade install`.

**What it catches:**

- Collection version conflicts (e.g., two collections requiring incompatible versions of a shared dependency)
- Missing or inaccessible collections on Galaxy or Automation Hub
- Authentication failures against Automation Hub (expired or invalid `AH_TOKEN`)
- Transient Galaxy/Automation Hub errors (retried automatically with exponential backoff, up to 3 attempts)

If collections install successfully but some Python dependencies fail to
build (common with source-only packages like `ncclient` or `systemd-python`),
Layer 1 still passes. The Python build failures are forwarded to Layer 2
and automatically trigger Layer 3.

**Automation Hub authentication:** If you need collections from Red Hat
Automation Hub, set the `AH_TOKEN` environment variable before running:

```bash
export AH_TOKEN=<your-offline-token>
ee-preflight my-ee/execution-environment.yml
```

### Layer 2: Dependency validation

Compares the Python and system dependencies discovered by `ade`'s
introspection (from installed collections' `meta/ee-requirements.txt` and
`meta/ee-bindep.txt`) against the dependencies declared in the EE definition.

**What it catches:**

- Undeclared system packages required by collections (e.g., `libssh-devel` needed by `ansible.netcommon` but missing from `bindep.txt`)
- Transitive Python dependencies that collections require but the EE does not declare (reported as informational)
- Python packages that failed to build during Layer 1 (forwarded as errors to this layer)

Layer 2 is platform-aware. It infers the target platform from the base
image name (e.g., `rhel-9`, `rhel-8`, `fedora`) and only flags system
dependencies relevant to that platform.

### Layer 3: Container wheel test

Pulls the actual base image and attempts to build Python wheels for
source-only packages inside the container. This is the most thorough
check: it verifies that the real container environment has the development
headers and libraries needed to compile packages from source.

**What it catches:**

- Missing `-devel` RPMs needed to compile Python C extensions (e.g., `libxml2-devel` for `lxml`, `systemd-devel` for `systemd-python`)
- Missing header files, pkg-config packages, and build tools
- Packages that fail to build even with all declared system dependencies installed

Layer 3 runs only when explicitly requested with `--container-test`, or
when Layer 1 detects Python build failures (in which case it activates
automatically).

Layer 3 uses `dnf provides` inside the container to resolve which RPM
provides a missing file, preferring `-devel` packages. It also performs
cumulative retries: if installing a discovered RPM allows a previously
failing package to build, it retries the remaining failures with the
expanded set of dependencies (up to 3 retry rounds).

**Requirements:** podman or docker must be installed and available in
`PATH`. The base image specified in the EE definition must be pullable
(registry authentication may be needed for `registry.redhat.io` images).

**Container runtime selection:** By default, ee-preflight auto-detects the
available container runtime with the following priority: podman, then docker.
You can override this with `--runtime {podman|docker}` to force a specific
runtime. This is useful in CI environments where only one runtime is available,
or when you need to test compatibility with a specific runtime.

## The `--fix` workflow

The `--fix` flag instructs ee-preflight to automatically apply fixes for
discovered issues. Combined with `--build`, this creates a validate-fix-build
pipeline:

```bash
ee-preflight my-ee/execution-environment.yml --fix --build
```

This does the following:

1. Runs all four validation layers
2. Collects all fixable findings (warnings and errors with a fix suggestion)
3. Writes the fixes to the appropriate files:
   - System packages are appended to `bindep.txt` (or created if it does not exist)
   - New dependency file references are added to `execution-environment.yml`
   - Inline dependencies are appended to the YAML list in `execution-environment.yml`
4. Re-validates Layer 0 and Layer 2 with the updated files
5. If no errors remain, runs `ansible-builder build`

The `--fix` flag is idempotent: running it twice produces the same result.
Existing entries are never duplicated.

Build arguments (like `AH_TOKEN`) are passed through to `ansible-builder`
from the environment automatically.

## JSON output

The `--json` flag produces structured output suitable for CI pipelines and
programmatic consumption:

```json
{
  "ee": "my-ee/execution-environment.yml",
  "result": "pass",
  "layers": [
    {
      "name": "prechecks",
      "status": "pass",
      "findings": []
    },
    {
      "name": "galaxy",
      "status": "pass",
      "findings": [
        {
          "severity": "info",
          "message": "12 collections resolved and installed",
          "fix": null,
          "source": null
        }
      ]
    },
    {
      "name": "python_deps",
      "status": "pass",
      "findings": []
    },
    {
      "name": "system_deps",
      "status": "skipped",
      "findings": []
    }
  ]
}
```

The exit code is `0` when all layers pass and `1` when any error is present.

## Requirements

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.11+ | 3.12 and 3.13 also supported |
| ade (ansible-dev-environment) | 24.0.0+ | Auto-installed as a pip dependency |
| pyyaml | 6.0+ | Auto-installed as a pip dependency |
| ansible-lint | 24.0.0+ | Optional. Enables YAML linting in Layer 0. Install with `pip install ee-preflight[lint]` |
| ansible-builder | 3.0.x | Optional. Required only for `--build`. Install with `pip install ee-preflight[build]` |
| podman or docker | Any | Optional. Required only for `--container-test` (Layer 3) |

## Troubleshooting

This section covers common issues and their solutions.

### Authentication Issues

**Problem: Collections from Automation Hub fail to install**

```
Layer 1: Galaxy Resolution ✗
  ✗ Failed to install collections from Automation Hub
  → Check AH_TOKEN environment variable
```

**Solution:**

1. Get an offline token from [console.redhat.com](https://console.redhat.com/ansible/automation-hub/token)
2. Export it before running ee-preflight:

   ```bash
   export AH_TOKEN=<your-offline-token>
   ee-preflight my-ee/execution-environment.yml
   ```

3. Verify the token is not expired (tokens expire after 30 days of inactivity)

**Problem: Container registry authentication fails (Layer 3)**

```
Layer 3: Container Wheel Test ✗
  ✗ Failed to pull image registry.redhat.io/ansible-automation-platform-24/ee-minimal-rhel9:latest
```

**Solution:**

For Red Hat registries, authenticate with podman or docker first:

```bash
# Using podman
podman login registry.redhat.io

# Using docker
docker login registry.redhat.io
```

Use your Red Hat account credentials when prompted.

### Container Runtime Issues

**Problem: No container runtime found**

```
Layer 3: Container Wheel Test ✗
  ✗ Neither podman nor docker found in PATH
```

**Solution:**

Install podman or docker:

```bash
# Fedora/RHEL/CentOS
sudo dnf install podman

# Ubuntu/Debian
sudo apt-get install podman

# macOS
brew install podman
podman machine init
podman machine start
```

Verify installation:

```bash
podman --version
# or
docker --version
```

**Problem: Permission denied when accessing container runtime**

```
Layer 3: Container Wheel Test ✗
  ✗ permission denied while trying to connect to the Docker daemon socket
```

**Solution:**

For Docker, add your user to the docker group:

```bash
sudo usermod -aG docker $USER
newgrp docker  # or log out and back in
```

For Podman, this usually indicates a rootless configuration issue. Try:

```bash
podman system migrate
```

### Collection Version Conflicts

**Problem: Collections require incompatible versions of a dependency**

```
Layer 1: Galaxy Resolution ✗
  ✗ Collection version conflict
    ansible.netcommon requires ansible.utils>=2.0.0
    cisco.ios requires ansible.utils<2.0.0
```

**Solution:**

1. Check the collection versions in your `requirements.yml`
2. Update to compatible versions:

   ```yaml
   collections:
     - name: ansible.netcommon
       version: ">=5.0.0"  # Compatible with ansible.utils 2.x
     - name: cisco.ios
       version: ">=5.0.0"  # Compatible with ansible.utils 2.x
     - name: ansible.utils
       version: ">=2.0.0"
   ```

3. Or pin to specific working versions:

   ```yaml
   collections:
     - name: ansible.netcommon
       version: "5.3.0"
     - name: cisco.ios
       version: "5.3.0"
     - name: ansible.utils
       version: "2.12.0"
   ```

**Problem: Collection not found on Galaxy**

```
Layer 1: Galaxy Resolution ✗
  ✗ Collection my.collection not found
```

**Solution:**

1. Verify the collection name is correct (check [galaxy.ansible.com](https://galaxy.ansible.com))
2. If it is a private collection, ensure you have access and proper authentication
3. Check if the collection was renamed or moved

### Build Failures

**Problem: ansible-builder build fails after ee-preflight passes**

This should be rare, but can happen if:

1. The base image changed between validation and build
2. A collection was updated on Galaxy between validation and build
3. Network issues during build

**Solution:**

1. Run with `--container-test` to catch more issues:

   ```bash
   ee-preflight my-ee/execution-environment.yml --container-test --fix --build
   ```

2. Compare the failed build output with ee-preflight findings
3. If ee-preflight missed something, please [report an issue](https://github.com/leogallego/ee-preflight/issues)

**Problem: Build succeeds but container crashes at runtime**

```
Error: libfoo.so.1: cannot open shared object file: No such file or directory
```

**Solution:**

This indicates a runtime dependency that is not a build dependency. Layer 3 only tests build-time wheel compilation.

1. Add the runtime dependency to `bindep.txt`:

   ```
   libfoo [platform:rpm]
   ```

2. Re-run with `--fix --build`:

   ```bash
   ee-preflight my-ee/execution-environment.yml --fix --build
   ```

### Cache Issues

**Problem: ee-preflight reports old/stale collection versions**

**Solution:**

1. Clear the ade cache:

   ```bash
   rm -rf ~/.ansible/ade/
   ```

2. If using `--venv`, remove the venv and let ee-preflight create a fresh one:

   ```bash
   rm -rf .venv
   ee-preflight my-ee/execution-environment.yml
   ```

**Problem: Temporary venv fills up disk space**

By default, ee-preflight creates temporary venvs in `/tmp/ade-venv-*` and cleans them up. If cleanup fails:

```bash
# Find orphaned venvs
ls -lhd /tmp/ade-venv-*

# Remove them
rm -rf /tmp/ade-venv-*
```

To avoid this, use a persistent venv with `--venv`:

```bash
python -m venv .venv
ee-preflight my-ee/execution-environment.yml --venv .venv
```

### Platform Detection Issues

**Problem: Wrong system dependencies detected (rpm vs deb)**

```
Layer 2: Dependency Validation ⚠
  ⚠ Undeclared system dep: libxml2-dev
    → Add 'libxml2-dev [platform:dpkg]' to bindep.txt
```

But your base image is RHEL-based (needs `libxml2-devel`, not `libxml2-dev`).

**Solution:**

ee-preflight infers the platform from the base image name. If detection fails:

1. Use an explicit base image name with platform indicator:

   ```yaml
   images:
     base_image:
       name: registry.redhat.io/ansible-automation-platform-24/ee-minimal-rhel9:latest
   ```

2. Or manually correct the fix suggestion when applying it

3. Or use platform-specific markers in `bindep.txt`:

   ```
   libxml2-devel [platform:rpm]
   libxml2-dev [platform:dpkg]
   ```

### YAML Linting Issues

**Problem: Layer 0 reports YAML formatting issues**

```
Layer 0: Pre-checks ✗
  ✗ YAML formatting issue: line too long
```

**Solution:**

1. If you have ansible-lint installed, it is enforcing style rules
2. Fix the issues manually or use ansible-lint to auto-fix:

   ```bash
   ansible-lint --fix execution-environment.yml
   ```

3. Or disable YAML linting by uninstalling ansible-lint:

   ```bash
   pip uninstall ansible-lint
   ```

   Layer 0 will still validate YAML syntax, just not formatting.

### Debugging Tips

**Get verbose output:**

```bash
ee-preflight my-ee/execution-environment.yml --verbose
```

**Get JSON output for analysis:**

```bash
ee-preflight my-ee/execution-environment.yml --json | jq
```

**Inspect the temporary venv:**

```bash
ee-preflight my-ee/execution-environment.yml --keep-venv --verbose
# Look for "Keeping venv at: /tmp/ade-venv-XXXXX"
source /tmp/ade-venv-XXXXX/bin/activate
pip list
ansible-galaxy collection list
```

**Test with container validation:**

```bash
ee-preflight my-ee/execution-environment.yml --container-test --verbose
```

### Still Having Issues?

If you encounter a problem not covered here:

1. Check the [examples/](examples/) directory for sample EE definitions
2. Search [existing issues](https://github.com/leogallego/ee-preflight/issues)
3. Open a new issue with:
   - ee-preflight version (`pip show ee-preflight`)
   - Full command and `--verbose` output
   - Your execution-environment.yml (or a minimal reproduction)

## Project background

ee-preflight was developed on the
[`ee-preflight` branch](https://github.com/leogallego/ansible-ee-builds/tree/ee-preflight)
of [leogallego/ansible-ee-builds](https://github.com/leogallego/ansible-ee-builds),
an Ansible Execution Environment definitions repository.

For more context on the design and the problems that motivated this tool, see:

- [Design document](docs/design.md) -- architecture decisions, layer design, and the choice of `ade` over `ansible-galaxy`
- [Build report](docs/build-report.md) -- the real-world EE build failures that ee-preflight was built to catch

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing guidelines, and PR submission process.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for release history and version notes.

## License

Apache-2.0
