# ee-preflight

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
             [--keep-venv] [--container-test] [--json] [--verbose]
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

## Project background

ee-preflight was developed on the
[`ee-preflight` branch](https://github.com/leogallego/ansible-ee-builds/tree/ee-preflight)
of [leogallego/ansible-ee-builds](https://github.com/leogallego/ansible-ee-builds),
an Ansible Execution Environment definitions repository.

For more context on the design and the problems that motivated this tool, see:

- [Design document](docs/design.md) -- architecture decisions, layer design, and the choice of `ade` over `ansible-galaxy`
- [Build report](docs/build-report.md) -- the real-world EE build failures that ee-preflight was built to catch

## License

Apache-2.0
