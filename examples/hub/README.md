# Automation Hub Execution Environment

This execution environment includes Red Hat certified collections from Automation Hub, which require authentication.

## Contents

- `execution-environment.yml` - EE definition with AH_TOKEN build argument
- `requirements.yml` - Mix of certified (Automation Hub) and community (Galaxy) collections
- `bindep.txt` - System dependencies

## Purpose

This example demonstrates:
- Authenticating with Red Hat Automation Hub using AH_TOKEN
- Mixing certified and community collections
- Using build arguments in execution environments
- Declaring build arguments in `additional_build_steps`

## Collections Included

### Certified Collections (require AH_TOKEN)

- `ansible.controller` - Manage Ansible Automation Platform Controller
- `ansible.eda` - Event-Driven Ansible automation

### Community Collections (public)

- `ansible.posix` - POSIX system management
- `community.general` - General purpose modules

## Authentication Setup

### Getting Your Automation Hub Token

1. Log in to [console.redhat.com](https://console.redhat.com/ansible/automation-hub/token)
2. Click "Load token" to reveal your offline token
3. Copy the token value

### Setting the Token

Export the token as an environment variable:

```bash
export AH_TOKEN=<your-offline-token>
```

Alternatively, create a `.env` file (DO NOT commit this to git):

```bash
echo "AH_TOKEN=<your-offline-token>" > .env
source .env
```

Add `.env` to your `.gitignore`:

```bash
echo ".env" >> .gitignore
```

## Validation

Run ee-preflight with authentication:

```bash
export AH_TOKEN=<your-token>
ee-preflight examples/hub/execution-environment.yml --verbose
```

Expected output:

```
ee-preflight: examples/hub/execution-environment.yml

Layer 0: Pre-checks ✓
  ℹ Found build arg: AH_TOKEN (set in environment)
  ℹ Found galaxy file: requirements.yml
  ℹ Found system deps file: bindep.txt
Layer 1: Galaxy Resolution ✓
  ℹ 4 collections resolved and installed
  ℹ Authenticated with Automation Hub
Layer 2: Dependency Validation ✓
  ℹ All declared system deps match discovered deps
Layer 3: Container Wheel Test (skipped)

Result: PASS (0 error(s), 0 warning(s))
```

### Without Authentication

If you run without AH_TOKEN, Layer 0 will warn about the missing build argument:

```bash
ee-preflight examples/hub/execution-environment.yml
```

Output:

```
Layer 0: Pre-checks ✗
  ✗ Build arg AH_TOKEN is not set in environment
    → Export AH_TOKEN before running ee-preflight
```

And Layer 1 will fail when trying to access certified collections:

```
Layer 1: Galaxy Resolution ✗
  ✗ Failed to install ansible.controller: 401 Unauthorized
    → Check AH_TOKEN environment variable
```

## Auto-fix and Build

Once authenticated, auto-fix and build:

```bash
export AH_TOKEN=<your-token>
ee-preflight examples/hub/execution-environment.yml --fix --build
```

The AH_TOKEN is automatically passed to `ansible-builder build` via the environment.

## Build Arguments

The `additional_build_steps` section declares the AH_TOKEN build argument:

```yaml
additional_build_steps:
  prepend_galaxy:
    - ARG AH_TOKEN
```

This tells ansible-builder to:
1. Accept AH_TOKEN as a build argument
2. Make it available during the Galaxy collection install step
3. Not persist the token in the final image (it's only used during build)

## System Dependencies

The `bindep.txt` includes additional dependencies for certified collections:

- `python311-devel` - Python development headers
- `gcc` - C compiler
- `openssl-devel` - OpenSSL development headers (for cryptography packages)
- `libffi-devel` - Foreign function interface library (for cryptography)

These are commonly needed by Automation Platform collections.

## Container Testing

Test with Layer 3 to verify all Python packages build correctly:

```bash
export AH_TOKEN=<your-token>
ee-preflight examples/hub/execution-environment.yml --container-test --verbose
```

This will:
1. Pull the base image
2. Test building Python wheels inside the container
3. Verify all system dependencies are present

## Registry Authentication

This example uses both registries that require authentication:

1. Red Hat Container Registry (for base image):
   ```bash
   podman login registry.redhat.io
   ```

2. Red Hat Automation Hub (for collections):
   ```bash
   export AH_TOKEN=<your-token>
   ```

## Customizing

### Adding More Certified Collections

Find available collections at [console.redhat.com](https://console.redhat.com/ansible/automation-hub):

```yaml
collections:
  - name: ansible.controller
    version: ">=4.5.0"
  - name: ansible.eda
    version: ">=1.4.0"
  - name: redhat.insights
    version: ">=1.0.0"
  - name: redhat.satellite
    version: ">=4.0.0"
```

Re-run ee-preflight to detect missing dependencies:

```bash
export AH_TOKEN=<your-token>
ee-preflight examples/hub/execution-environment.yml --fix --verbose
```

### Using Galaxy Server URL

If your organization uses a private Automation Hub, configure it in `ansible.cfg`:

```ini
[galaxy]
server_list = automation_hub, galaxy

[galaxy_server.automation_hub]
url=https://your-hub.example.com/api/galaxy/
token=<your-token>

[galaxy_server.galaxy]
url=https://galaxy.ansible.com/
```

Or set the `ANSIBLE_GALAXY_SERVER_LIST` environment variable.

## Security Notes

- **Never commit AH_TOKEN to version control**
- Add `.env` to `.gitignore`
- Use CI/CD secrets for automation (GitHub Secrets, GitLab CI/CD Variables, etc.)
- Tokens expire after 30 days of inactivity - rotate them regularly
- Treat offline tokens like passwords

## Testing the Built Image

After building with authentication:

```bash
# List installed collections (certified + community)
podman run --rm my-hub-ee:latest ansible-galaxy collection list

# Verify ansible.controller is installed
podman run --rm my-hub-ee:latest ansible-galaxy collection list | grep ansible.controller

# Run a playbook that uses certified collections
podman run --rm -v $(pwd):/work:Z my-hub-ee:latest ansible-playbook /work/controller-config.yml
```

## Troubleshooting

### Token Expired

If you get authentication errors, check if your token is expired:

1. Go to [console.redhat.com](https://console.redhat.com/ansible/automation-hub/token)
2. Click "Load token"
3. If it says expired, regenerate a new token
4. Update your `AH_TOKEN` environment variable

### Wrong Token

Make sure you are using the Automation Hub token, not:
- Red Hat Customer Portal password
- OpenShift token
- GitHub token

The token should start with `eyJ...` and be very long (hundreds of characters).

### Collection Not Found

If a certified collection is not found:

1. Verify you have a valid Red Hat subscription
2. Check that the collection is available in your Automation Hub instance
3. Verify the collection name and namespace are correct

## Notes

- Certified collections receive Red Hat support
- Community collections are maintained by the Ansible community
- Mixing both types in one EE is common and supported
- Layer 3 helps catch dependency issues before production deployments
