# Minimal Execution Environment

This is the simplest possible execution environment with no collections, no Python dependencies, and no system dependencies.

## Contents

- `execution-environment.yml` - Base EE definition with only a base image

## Purpose

Use this as a starting point for:
- Learning ee-preflight
- Testing basic validation
- Building a custom EE from scratch

## Validation

Run ee-preflight on this EE:

```bash
ee-preflight examples/minimal/execution-environment.yml
```

Expected output:

```
ee-preflight: examples/minimal/execution-environment.yml

Layer 0: Pre-checks ✓
Layer 1: Galaxy Resolution ✓
Layer 2: Dependency Validation ✓
Layer 3: Container Wheel Test (skipped)

Result: PASS (0 error(s), 0 warning(s))
```

All layers pass because there are no collections to resolve and no dependencies to validate.

## Building

Build this EE:

```bash
ee-preflight examples/minimal/execution-environment.yml --build
```

Or with a custom tag:

```bash
ee-preflight examples/minimal/execution-environment.yml --build --tag my-minimal-ee:latest
```

## Customizing

To add collections, create a `requirements.yml` file:

```yaml
collections:
  - name: ansible.posix
    version: ">=1.5.0"
```

Then reference it in `execution-environment.yml`:

```yaml
dependencies:
  galaxy: requirements.yml
  python_interpreter:
    package_system: python311
```

Re-run ee-preflight to validate:

```bash
ee-preflight examples/minimal/execution-environment.yml --verbose
```

## Base Image

This example uses the Red Hat Ansible Automation Platform minimal base image:
- `registry.redhat.io/ansible-automation-platform-24/ee-minimal-rhel9:latest`

To use this base image, you need to authenticate with the Red Hat registry:

```bash
podman login registry.redhat.io
# or
docker login registry.redhat.io
```

Alternative base images:
- `quay.io/ansible/creator-ee:latest` - Community-maintained creator EE
- `quay.io/ansible/ansible-runner:latest` - Ansible Runner base image

## Notes

- Layer 3 is skipped by default because there are no Python packages to build
- Use `--container-test` to force Layer 3 and verify the base image is accessible
- This EE is production-ready but only includes ansible-core (no collections)
