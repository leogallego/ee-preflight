# Standard Execution Environment

This is a typical execution environment with commonly used collections from Ansible Galaxy.

## Contents

- `execution-environment.yml` - Base EE definition
- `requirements.yml` - Collection dependencies
- `bindep.txt` - System dependencies

## Purpose

This example demonstrates:
- Installing collections from Ansible Galaxy (public)
- Declaring system dependencies for Python package builds
- Using external dependency files (vs inline dependencies)

## Collections Included

- `ansible.posix` - POSIX system management (files, mount, sysctl, etc.)
- `community.general` - General purpose modules and plugins
- `ansible.utils` - Utilities for filtering, validating data

These are three of the most popular collections and are suitable for general Linux/Unix automation.

## Validation

Run ee-preflight on this EE:

```bash
ee-preflight examples/standard/execution-environment.yml --verbose
```

Expected output:

```
ee-preflight: examples/standard/execution-environment.yml

Layer 0: Pre-checks ✓
  ℹ Found galaxy file: requirements.yml
  ℹ Found system deps file: bindep.txt
Layer 1: Galaxy Resolution ✓
  ℹ 3 collections resolved and installed
Layer 2: Dependency Validation ✓
  ℹ All declared system deps match discovered deps
Layer 3: Container Wheel Test (skipped)

Result: PASS (0 error(s), 0 warning(s))
```

## Auto-fix and Build

Let ee-preflight auto-fix any missing dependencies and build:

```bash
ee-preflight examples/standard/execution-environment.yml --fix --build
```

Or test with container validation:

```bash
ee-preflight examples/standard/execution-environment.yml --container-test --verbose
```

## System Dependencies

The `bindep.txt` file includes:
- `python311-devel` - Python development headers (for building C extensions)
- `gcc` - C compiler (required for building many Python packages)

These are common requirements for building Python packages that have C extensions.

## Customizing

### Adding More Collections

Edit `requirements.yml` and add more collections:

```yaml
collections:
  - name: ansible.posix
    version: ">=1.5.0"
  - name: community.general
    version: ">=8.0.0"
  - name: ansible.utils
    version: ">=3.0.0"
  - name: community.docker
    version: ">=3.0.0"
  - name: community.postgresql
    version: ">=3.0.0"
```

Re-run ee-preflight to detect missing dependencies:

```bash
ee-preflight examples/standard/execution-environment.yml --verbose
```

If new system dependencies are needed, ee-preflight will suggest adding them:

```
Layer 2: Dependency Validation ✓
  ⚠ Undeclared system dep: postgresql-devel
    → Add 'postgresql-devel [platform:rpm]' to bindep.txt
```

Auto-fix them:

```bash
ee-preflight examples/standard/execution-environment.yml --fix
```

### Using Inline Dependencies

Instead of external files, you can declare dependencies inline:

```yaml
dependencies:
  galaxy:
    collections:
      - name: ansible.posix
        version: ">=1.5.0"
      - name: community.general
        version: ">=8.0.0"
  python_interpreter:
    package_system: python311
  system:
    - python311-devel [platform:rpm]
    - gcc [platform:rpm]
```

## Base Image Authentication

This example uses the Red Hat registry. Authenticate first:

```bash
podman login registry.redhat.io
```

Or use a public base image:

```yaml
images:
  base_image:
    name: quay.io/ansible/creator-ee:latest
```

## Testing the Built Image

After building, test the image:

```bash
# List installed collections
podman run --rm my-standard-ee:latest ansible-galaxy collection list

# Run a simple playbook
podman run --rm -v $(pwd):/work:Z my-standard-ee:latest ansible-playbook /work/test.yml
```

## Notes

- The `[platform:rpm]` markers in `bindep.txt` ensure these dependencies are only installed on RPM-based systems
- For Debian/Ubuntu base images, use `[platform:dpkg]` instead
- Layer 3 tests Python package builds inside the actual container environment
