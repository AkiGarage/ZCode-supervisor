# Distribution Strategy

This is the active distribution plan for ZCode-supervisor.

## Decision

Current primary public install path:

```bash
uvx --from zcode-supervisor zcode-install-repo /absolute/path/to/target-repo
```

Persistent tool install path:

```bash
uv tool install zcode-supervisor
zcode-install-repo /absolute/path/to/target-repo
```

Current high-assurance fallback:

```bash
gh release download v0.0.1 \
  -R AkiGarage/ZCode-supervisor \
  -p 'zcode-supervisor-v0.0.1.tar.gz' \
  -p SHA256SUMS
shasum -a 256 -c SHA256SUMS
gh attestation verify zcode-supervisor-v0.0.1.tar.gz \
  -R AkiGarage/ZCode-supervisor \
  --source-ref refs/tags/v0.0.1 \
  --source-digest 6525b8a41371a687a9b9ef3513da38eaab52cf9e \
  --signer-workflow AkiGarage/ZCode-supervisor/.github/workflows/release-artifacts.yml
```

Homebrew is archived for now. Keep the Formula and old release docs only as
reference material until there is a clear reason to revive it.

## Why uvx First

ZCode-supervisor is already a Python CLI package with no Python runtime
dependencies. `uvx` can run that CLI in an ephemeral environment, while
`uv tool install` gives repeat users a managed isolated install. This matches
the product shape better than asking users to add a Homebrew tap for a setup
helper.

The package must publish through PyPI Trusted Publishing, not a stored PyPI API
token. The GitHub Actions workflow must use an explicit `pypi` or `testpypi`
environment plus `id-token: write`, and publish only after maintainer approval.

## Safety Contract

- Publish from the clean public repo `AkiGarage/ZCode-supervisor`, not from the
  private development repo.
- Default release workflow mode must build only; publishing is a deliberate
  manual choice.
- Use TestPyPI before first production PyPI publish.
- Do not store PyPI tokens in GitHub secrets.
- Build and inspect the wheel before publishing; the wheel must include
  `tools/zcode_control/*.mjs`.
- Keep GitHub Release archives attested and checksumed for users who want
  independent verification before running local setup.
- Keep Homebrew archived until explicitly revived.

## User-Facing Setup Flow

1. Install ZCode from the official ZCode docs and sign in.
2. Install `uv` if needed.
3. Run `uvx --from zcode-supervisor zcode-install-repo <target-repo>`.
4. Run
   `uvx --from zcode-supervisor zcode-auto-route --workspace <target-repo> --objective "setup smoke check"`.
5. Start real delegated tasks only after Codex chooses allowed files and
   validation.

Useful preflight commands after the PyPI package is installed with
`uv tool install zcode-supervisor`:

```bash
zcodectl cli-preflight
zcodectl vision-preflight --workspace /absolute/path/to/target-repo
```

## Release Flow

1. Re-check `git status -sb`, repo visibility, and clean public scope.
2. Run `git diff --check` and `bash scripts/check.sh`.
3. Build and inspect the wheel locally.
4. Tag from the clean public repo after approval.
5. Run the PyPI workflow in `build-only` mode.
6. Ensure Trusted Publishers exist on TestPyPI and PyPI; see
   [pypi-trusted-publisher.md](pypi-trusted-publisher.md).
7. Run `scripts/check-pypi-release-readiness --target testpypi
   --trusted-publishers-configured`.
8. Publish to TestPyPI after approval and verify install with `uvx`.
9. Run `scripts/check-pypi-release-readiness --target pypi
   --trusted-publishers-configured`.
10. Publish to PyPI after approval.
11. Run the GitHub Release artifact workflow and publish the attested archive for
   high-assurance users.

No step above should rename repos, change visibility, push tags, publish PyPI,
or publish GitHub Releases without explicit maintainer approval.

## References

- uv tools: https://docs.astral.sh/uv/concepts/tools/
- uv installation: https://docs.astral.sh/uv/getting-started/installation/
- PyPI Trusted Publishing: https://docs.pypi.org/trusted-publishers/
- Publishing with a Trusted Publisher: https://docs.pypi.org/trusted-publishers/using-a-publisher/
- Creating a PyPI project with a Trusted Publisher: https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/
- PyPI Trusted Publisher troubleshooting: https://docs.pypi.org/trusted-publishers/troubleshooting/
- PyPI attestations: https://docs.pypi.org/attestations/
- GitHub artifact attestations: https://docs.github.com/actions/security-for-github-actions/using-artifact-attestations/using-artifact-attestations-to-establish-provenance-for-builds
