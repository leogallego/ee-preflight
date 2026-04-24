# Execution Environment Examples

This directory contains sample Ansible Execution Environment definitions demonstrating various use cases and ee-preflight features.

## Available Examples

### 1. Minimal (`minimal/`)

The simplest possible EE with no collections, no dependencies - just a base image.

**Use case:** Starting point for learning ee-preflight or building custom EEs from scratch.

**What you'll learn:**
- Basic execution-environment.yml structure
- Running ee-preflight validation
- Building a minimal EE

**Quick start:**
```bash
ee-preflight examples/minimal/execution-environment.yml
ee-preflight examples/minimal/execution-environment.yml --build
```

### 2. Standard (`standard/`)

A typical EE with commonly used collections from Ansible Galaxy.

**Use case:** General-purpose automation with popular collections (ansible.posix, community.general, ansible.utils).

**What you'll learn:**
- Using external dependency files (requirements.yml, bindep.txt)
- System dependency declaration
- Auto-fixing missing dependencies
- Container testing

**Quick start:**
```bash
ee-preflight examples/standard/execution-environment.yml --verbose
ee-preflight examples/standard/execution-environment.yml --fix --build
ee-preflight examples/standard/execution-environment.yml --container-test
```

### 3. Automation Hub (`hub/`)

EE with Red Hat certified collections requiring Automation Hub authentication.

**Use case:** Enterprise environments using Red Hat Ansible Automation Platform with certified collections.

**What you'll learn:**
- Authenticating with Red Hat Automation Hub via AH_TOKEN
- Using build arguments in execution environments
- Mixing certified and community collections
- Managing authentication tokens securely

**Quick start:**
```bash
export AH_TOKEN=<your-offline-token>
ee-preflight examples/hub/execution-environment.yml --verbose
ee-preflight examples/hub/execution-environment.yml --fix --build
```

## General Usage

Each example directory contains:
- `execution-environment.yml` - The EE definition file
- `README.md` - Detailed documentation for that example
- Additional files as needed (requirements.yml, bindep.txt, etc.)

### Validating an Example

```bash
# Basic validation
ee-preflight examples/<example-name>/execution-environment.yml

# Verbose output (shows all checks)
ee-preflight examples/<example-name>/execution-environment.yml --verbose

# With container testing (Layer 3)
ee-preflight examples/<example-name>/execution-environment.yml --container-test

# JSON output
ee-preflight examples/<example-name>/execution-environment.yml --json | jq
```

### Auto-fixing Issues

If ee-preflight detects missing dependencies:

```bash
ee-preflight examples/<example-name>/execution-environment.yml --fix
```

This will automatically:
- Create bindep.txt if missing
- Add missing system dependencies
- Update execution-environment.yml with dependency file references

### Building an Example

After validation passes:

```bash
ee-preflight examples/<example-name>/execution-environment.yml --build
```

Or combine validation, fixing, and building:

```bash
ee-preflight examples/<example-name>/execution-environment.yml --fix --build
```

With a custom tag:

```bash
ee-preflight examples/<example-name>/execution-environment.yml --build --tag my-ee:v1.0
```

## Prerequisites

### Required

- Python 3.11+ (3.12 and 3.13 also supported)
- ee-preflight installed: `pip install ee-preflight`

### Optional

- ansible-builder (for --build flag): `pip install ee-preflight[build]`
- ansible-lint (for YAML linting): `pip install ee-preflight[lint]`
- podman or docker (for --container-test flag)

### Registry Authentication

Some examples use the Red Hat Container Registry (`registry.redhat.io`). To pull these images:

```bash
podman login registry.redhat.io
# or
docker login registry.redhat.io
```

Use your Red Hat account credentials.

## Modifying Examples

Feel free to modify these examples to learn how ee-preflight behaves:

### Add a Collection

Edit `requirements.yml`:

```yaml
collections:
  - name: community.docker
    version: ">=3.0.0"
```

Re-run ee-preflight:

```bash
ee-preflight examples/standard/execution-environment.yml --verbose
```

ee-preflight may suggest adding system dependencies (like `docker` package or development libraries).

### Remove a System Dependency

Comment out a line in `bindep.txt`:

```
python311-devel [platform:rpm]
# gcc [platform:rpm]
```

Re-run with container testing:

```bash
ee-preflight examples/standard/execution-environment.yml --container-test
```

Layer 3 may report build failures if Python packages need gcc to compile.

### Test Build Arguments

Add an ARG in `additional_build_steps` without setting it in the environment:

```yaml
additional_build_steps:
  prepend_galaxy:
    - ARG MY_TOKEN
```

Run ee-preflight:

```bash
ee-preflight examples/hub/execution-environment.yml
```

Layer 0 will report the missing build argument.

## Example Comparison

| Feature | Minimal | Standard | Hub |
|---------|---------|----------|-----|
| Collections | None | 3 (Galaxy) | 4 (Hub + Galaxy) |
| Dependency files | None | requirements.yml, bindep.txt | requirements.yml, bindep.txt |
| Authentication | No | No | Yes (AH_TOKEN) |
| Build arguments | No | No | Yes (AH_TOKEN) |
| System dependencies | None | 2 packages | 4 packages |
| Complexity | Beginner | Intermediate | Advanced |

## Creating Your Own EE

Use these examples as templates:

1. Copy an example directory:
   ```bash
   cp -r examples/standard my-custom-ee
   ```

2. Modify the files for your needs:
   - Edit `execution-environment.yml` to change the base image
   - Edit `requirements.yml` to add your collections
   - Edit `bindep.txt` to add system dependencies (if needed)

3. Validate with ee-preflight:
   ```bash
   ee-preflight my-custom-ee/execution-environment.yml --verbose
   ```

4. Auto-fix any issues:
   ```bash
   ee-preflight my-custom-ee/execution-environment.yml --fix
   ```

5. Build the image:
   ```bash
   ee-preflight my-custom-ee/execution-environment.yml --build --tag my-custom-ee:latest
   ```

## Testing Built Images

After building an EE, test it:

```bash
# List installed collections
podman run --rm my-ee:latest ansible-galaxy collection list

# Check Python packages
podman run --rm my-ee:latest pip list

# Run a playbook
podman run --rm -v $(pwd):/work:Z my-ee:latest ansible-playbook /work/site.yml
```

## Common Patterns

### Inline vs External Dependencies

**External files** (recommended for larger EEs):

```yaml
dependencies:
  galaxy: requirements.yml
  system: bindep.txt
```

**Inline** (good for small, self-contained EEs):

```yaml
dependencies:
  galaxy:
    collections:
      - name: ansible.posix
  system:
    - python311-devel [platform:rpm]
```

### Platform-Specific Dependencies

Use platform markers for multi-platform support:

```
# bindep.txt
libxml2-devel [platform:rpm]     # RHEL, Fedora, CentOS
libxml2-dev [platform:dpkg]      # Ubuntu, Debian
```

### Build Steps

Add custom build steps:

```yaml
additional_build_steps:
  prepend_galaxy:
    - ARG BUILD_ARG
  append_final:
    - RUN echo "Custom setup complete"
  prepend_final: |
    RUN dnf install -y custom-package
```

## Troubleshooting

If validation fails, check the [Troubleshooting section](../README.md#troubleshooting) in the main README.

Common issues:
- Missing AH_TOKEN for Automation Hub examples
- Base image registry authentication
- Container runtime (podman/docker) not found for Layer 3

## Contributing Examples

Have a useful EE example? Consider contributing it:

1. Create a new directory under `examples/`
2. Include execution-environment.yml and README.md
3. Document the use case and what users will learn
4. Test with ee-preflight to ensure it validates correctly
5. Submit a pull request

See [CONTRIBUTING.md](../CONTRIBUTING.md) for details.

## Additional Resources

- [ee-preflight README](../README.md) - Full CLI reference and layer documentation
- [Design document](../docs/design.md) - Architecture and design decisions
- [Build report](../docs/build-report.md) - Real-world failure examples
- [ansible-builder documentation](https://ansible-builder.readthedocs.io/) - Official ansible-builder docs
- [Ansible Galaxy](https://galaxy.ansible.com/) - Community collections
- [Automation Hub](https://console.redhat.com/ansible/automation-hub) - Red Hat certified collections
