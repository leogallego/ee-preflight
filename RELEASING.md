# Release Guide

This document describes the process for releasing a new version of ee-preflight to PyPI.

## Prerequisites

Before you start a release:

1. All CI checks are passing on `main` branch
2. All planned features/fixes for the release are merged
3. Documentation is up to date
4. You have maintainer access to the GitHub repository

## Release Process

### 1. Update the version

Edit `pyproject.toml` and update the version number:

```toml
[project]
name = "ee-preflight"
version = "0.2.0"  # Update this line
```

Follow [Semantic Versioning](https://semver.org/):
- **MAJOR** version for incompatible API changes
- **MINOR** version for new functionality in a backwards compatible manner
- **PATCH** version for backwards compatible bug fixes

For pre-release versions, use suffixes:
- `0.2.0a1` for alpha releases
- `0.2.0b1` for beta releases
- `0.2.0rc1` for release candidates

### 2. Update the changelog

If you maintain a `CHANGELOG.md`, add an entry for the new version:

```markdown
## [0.2.0] - 2026-04-23

### Added
- New feature X
- New feature Y

### Fixed
- Bug fix Z

### Changed
- Breaking change A
```

### 3. Commit the version bump

```bash
git checkout -b release-v0.2.0
git add pyproject.toml CHANGELOG.md
git commit -m "Bump version to 0.2.0"
git push origin release-v0.2.0
```

### 4. Create and merge a pull request

Create a PR for the release branch and get it reviewed and merged into `main`.

### 5. Create and push a git tag

Once the PR is merged to `main`:

```bash
git checkout main
git pull origin main
git tag -a v0.2.0 -m "Release v0.2.0"
git push origin v0.2.0
```

**Important:** The tag MUST start with `v` (e.g., `v0.2.0`, not `0.2.0`) to trigger the release workflow.

### 6. Monitor the release workflow

The release is now automated via GitHub Actions:

1. Go to https://github.com/leogallego/ee-preflight/actions
2. Find the "Release" workflow for your tag
3. Watch the workflow steps:
   - **build**: Builds the source distribution and wheel
   - **publish-pypi**: Publishes to PyPI using trusted publishing (OIDC)
   - **create-release**: Creates a GitHub release with changelog

The entire process takes about 2-3 minutes.

### 7. Verify the release

Once the workflow completes:

1. **Check PyPI**: Visit https://pypi.org/project/ee-preflight/ and verify the new version is live
2. **Check GitHub Releases**: Visit https://github.com/leogallego/ee-preflight/releases and verify the release was created
3. **Test installation**: In a fresh virtual environment:
   ```bash
   pip install ee-preflight==0.2.0
   ee-preflight --help
   ```

### 8. Announce the release

Consider announcing the release:
- GitHub Discussions (if enabled)
- Project README or documentation site
- Social media or relevant communities

## Troubleshooting

### Release workflow fails at publish-pypi step

**Cause:** PyPI trusted publishing is not configured correctly.

**Solution:**
1. Go to https://pypi.org/manage/account/publishing/
2. Add a new trusted publisher:
   - **PyPI Project Name:** `ee-preflight`
   - **Owner:** `leogallego`
   - **Repository name:** `ee-preflight`
   - **Workflow name:** `release.yml`
   - **Environment name:** `release`

### Version already exists on PyPI

**Cause:** You're trying to re-release a version that already exists.

**Solution:** You cannot replace an existing version on PyPI. You must:
1. Delete the git tag: `git tag -d v0.2.0 && git push origin :refs/tags/v0.2.0`
2. Bump to a new version (e.g., `0.2.1`)
3. Follow the release process again

### GitHub release creation fails

**Cause:** Permission issues with the GitHub token.

**Solution:** The workflow needs `contents: write` permission, which is already configured. If this fails, check repository settings under Settings → Actions → General → Workflow permissions.

## Pre-release Testing

Before doing an official release, you can test the packaging locally:

```bash
# Install build tools
pip install build twine

# Build the package
python -m build

# Check the package
twine check dist/*

# Test installation locally
pip install dist/ee_preflight-0.2.0-py3-none-any.whl
ee-preflight --help

# Upload to Test PyPI (optional)
twine upload --repository testpypi dist/*
```

## Rolling Back a Release

If a critical bug is found after release:

1. **Do not delete the PyPI release** (PyPI does not allow re-uploading the same version)
2. Instead, immediately release a new patch version with the fix (e.g., `0.2.1`)
3. Mark the buggy release as "yanked" on PyPI (this hides it from `pip install` but keeps it accessible for existing users)
4. Update documentation to warn about the buggy version

To yank a release on PyPI:
```bash
pip install twine
twine upload --repository pypi --skip-existing dist/*  # if needed
# Then go to https://pypi.org/project/ee-preflight/ and use the web UI to yank the version
```

## Release Checklist

Use this checklist when cutting a release:

- [ ] All tests pass on `main`
- [ ] Version number updated in `pyproject.toml`
- [ ] `CHANGELOG.md` updated (if maintained)
- [ ] Release branch created and PR opened
- [ ] PR reviewed and merged to `main`
- [ ] Git tag created (`v` prefix) and pushed
- [ ] Release workflow completed successfully
- [ ] PyPI release verified
- [ ] GitHub release verified
- [ ] Installation tested in fresh environment
- [ ] Release announced (if applicable)

## Automation Details

The release process uses GitHub Actions with the following features:

### PyPI Trusted Publishing (OIDC)

No API tokens are stored as secrets. Instead, GitHub's OIDC provider authenticates directly with PyPI. This is more secure and easier to maintain.

**Setup required once:**
- Create the `release` environment in GitHub repository settings
- Configure the trusted publisher on PyPI (see troubleshooting above)

### GitHub Release Notes

The workflow automatically:
- Extracts the version from the git tag
- Generates a changelog from git commits since the last tag
- Includes SHA256 checksums of the release artifacts
- Attaches the wheel and source distribution files
- Marks releases as "prerelease" if the tag contains `alpha`, `beta`, or `rc`

### Build Verification

The CI workflow (`ci.yml`) includes jobs that:
- Build the package on every commit
- Verify package metadata with `twine check`
- Test installation from the built wheel
- Verify the CLI is accessible after installation

This ensures that every commit produces a valid, installable package.
