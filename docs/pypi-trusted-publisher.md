# PyPI Trusted Publisher Handoff

This repo publishes Python packages only through PyPI Trusted Publishing. Do
not add PyPI API tokens to GitHub secrets.

## Current Status

- Public repo: `AkiGarage/ZCode-supervisor`
- Package name: `zcode-supervisor`
- Current version: `0.0.1`
- Current tag: `v0.0.1`
- Release archive: `https://github.com/AkiGarage/ZCode-supervisor/releases/tag/v0.0.1`
- TestPyPI status: `0.0.1` published
- PyPI status: `0.0.1` published
- Homebrew: archived

The first TestPyPI upload before publisher setup built and attested the
wheel/sdist, then failed safely with `invalid-publisher`. After pending
publishers were configured, `0.0.1` was published to both TestPyPI and PyPI
through GitHub OIDC and Trusted Publishing.

The required GitHub OIDC claim shape is:

```text
repo:AkiGarage/ZCode-supervisor:environment:testpypi
```

## Manual Setup For New Maintainers

The current project already has working publishers. For a new package,
organization, or replacement account, create a pending publisher in TestPyPI
account settings:

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

Pending publishers do not reserve the package name until first publish.

## Preflight For The Next Version

Before retrying TestPyPI for a new version, set the tag you are releasing:

```bash
TAG=v0.0.2
```

Then run:

```bash
scripts/check-pypi-release-readiness \
  --target testpypi \
  --tag "$TAG" \
  --version "${TAG#v}" \
  --trusted-publishers-configured
```

The command must print `"safe_to_dispatch": true` before dispatching the
workflow.

## TestPyPI Publish For A New Version

For `v0.0.1`, the tag predates the later workflow guard input, so the
successful historical run used only `tag` and `publish_target`. Future tags
should be created after the guarded workflow is present, then dispatched from
the tag with the guarded input:

```bash
gh workflow run pypi-publish.yml \
  -R AkiGarage/ZCode-supervisor \
  --ref "$TAG" \
  -f tag="$TAG" \
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
  --extra-index-url https://pypi.org/simple/ \
  --from zcode-supervisor \
  zcode-install-repo --help
```

## PyPI Publish For A New Version

Do not publish to PyPI until TestPyPI shows the new version and the install
smoke test passes.

Before PyPI, run:

```bash
scripts/check-pypi-release-readiness \
  --target pypi \
  --tag "$TAG" \
  --version "${TAG#v}" \
  --trusted-publishers-configured
```

Only continue if it prints `"safe_to_dispatch": true`.

The `pypi` GitHub environment is restricted to `v*` tags and requires
`AkiGarage` approval. Dispatch:

```bash
gh workflow run pypi-publish.yml \
  -R AkiGarage/ZCode-supervisor \
  --ref "$TAG" \
  -f tag="$TAG" \
  -f publish_target=pypi \
  -f trusted_publishers_configured=true
```

After success, verify:

```bash
curl -fsS https://pypi.org/pypi/zcode-supervisor/json | jq '.info.version'
uvx --from zcode-supervisor zcode-install-repo --help
```
