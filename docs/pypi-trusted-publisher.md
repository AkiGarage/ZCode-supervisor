# PyPI Trusted Publisher Handoff

This repo publishes Python packages only through PyPI Trusted Publishing. Do
not add PyPI API tokens to GitHub secrets.

## Current Status

- Public repo: `AkiGarage/ZCode-supervisor`
- Package name: `zcode-supervisor`
- Current version: `0.0.1`
- Current tag: `v0.0.1`
- Release archive: `https://github.com/AkiGarage/ZCode-supervisor/releases/tag/v0.0.1`
- TestPyPI status: not published yet
- PyPI status: not published yet
- Homebrew: archived

The first TestPyPI upload already built and attested the wheel/sdist, then
failed safely with `invalid-publisher`. That means TestPyPI did not have a
matching pending Trusted Publisher for this GitHub OIDC claim:

```text
repo:AkiGarage/ZCode-supervisor:environment:testpypi
```

## Manual Setup

Create a pending publisher in TestPyPI account settings:

```text
Project name: zcode-supervisor
Owner: AkiGarage
Repository name: ZCode-supervisor
Workflow filename: pypi-publish.yml
Environment name: testpypi
```

Create a pending publisher in PyPI account settings:

```text
Project name: zcode-supervisor
Owner: AkiGarage
Repository name: ZCode-supervisor
Workflow filename: pypi-publish.yml
Environment name: pypi
```

Pending publishers do not reserve the package name until first publish. Run the
TestPyPI publish soon after setup.

## Preflight

Before retrying TestPyPI, run:

```bash
scripts/check-pypi-release-readiness --target testpypi
```

It should stop with a manual action until both pending publishers are configured.
After manually creating them, run:

```bash
scripts/check-pypi-release-readiness \
  --target testpypi \
  --trusted-publishers-configured
```

The command must print `"safe_to_dispatch": true` before dispatching the
workflow.

## TestPyPI Publish

Dispatch only from the tag:

```bash
gh workflow run pypi-publish.yml \
  -R AkiGarage/ZCode-supervisor \
  --ref v0.0.1 \
  -f tag=v0.0.1 \
  -f publish_target=testpypi \
  -f trusted_publishers_configured=true
```

Watch the run:

```bash
gh run list -R AkiGarage/ZCode-supervisor --workflow pypi-publish.yml --limit 3
gh run watch <run-id> -R AkiGarage/ZCode-supervisor --exit-status
```

After success, verify TestPyPI:

```bash
curl -fsS https://test.pypi.org/pypi/zcode-supervisor/json | jq '.info.version'
uvx --index-url https://test.pypi.org/simple/ \
  --from zcode-supervisor \
  zcode-install-repo --help
```

## PyPI Publish

Do not publish to PyPI until TestPyPI shows version `0.0.1` and the install
smoke test passes.

Before PyPI, run:

```bash
scripts/check-pypi-release-readiness \
  --target pypi \
  --trusted-publishers-configured
```

Only continue if it prints `"safe_to_dispatch": true`.

The `pypi` GitHub environment is restricted to `v*` tags and requires
`AkiGarage` approval. Dispatch:

```bash
gh workflow run pypi-publish.yml \
  -R AkiGarage/ZCode-supervisor \
  --ref v0.0.1 \
  -f tag=v0.0.1 \
  -f publish_target=pypi \
  -f trusted_publishers_configured=true
```

After success, verify:

```bash
curl -fsS https://pypi.org/pypi/zcode-supervisor/json | jq '.info.version'
uvx --from zcode-supervisor zcode-install-repo --help
```
