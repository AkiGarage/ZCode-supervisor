# Archived Homebrew Release Preparation

Archived status: Homebrew is not the primary distribution path for
ZCode-supervisor. Keep this document as historical packaging reference only.
The active distribution plan is [docs/distribution.md](distribution.md).

This document is the release checklist for distributing ZCode-supervisor through
the public product repo `AkiGarage/ZCode-supervisor` and the Homebrew tap repo
`AkiGarage/homebrew-zcode-supervisor`.

Future release artifacts should live in `AkiGarage/ZCode-supervisor`. The tap
repo should hold only the Formula needed for the short Homebrew command.

The archived Homebrew install command was:

```bash
brew tap AkiGarage/zcode-supervisor
brew install zcode-supervisor
zcode-install-repo /absolute/path/to/target-repo
```

Do not advertise a new Homebrew release until Homebrew is explicitly revived
and all of these
exist:

- a pushed `vX.Y.Z` tag
- a GitHub Release asset named `zcode-supervisor-vX.Y.Z.tar.gz` in
  `AkiGarage/ZCode-supervisor`
- a matching `SHA256SUMS`
- GitHub artifact attestations for the archive and checksums
- a public product repo at `AkiGarage/ZCode-supervisor`
- a public tap repo at `AkiGarage/homebrew-zcode-supervisor`
- a tap formula with the real release URL and SHA256

## Current State

- Public product repo name: `AkiGarage/ZCode-supervisor`
- Private development repo: kept internal; do not make it public in place
- Formula template: `packaging/homebrew/zcode-supervisor.rb`
- Formula updater: `scripts/update-homebrew-formula`
- Release artifact workflow: `.github/workflows/release-artifacts.yml`
- Release-prep CI: `.github/workflows/homebrew-release-validation.yml`
- Tap repo name: `AkiGarage/homebrew-zcode-supervisor`
- User-facing tap command: `brew tap AkiGarage/zcode-supervisor`

Do not make the private development repo public in place; publish a clean
snapshot into the public product repo instead.

The formula installs the source tree into Homebrew `libexec` and writes PATH
wrappers for:

- `zcode-install-repo`
- `zcode-auto-route`
- `zcode-supervisor`
- `zcode-eval`
- `zcode-release-check`

It depends on `python@3.11`, `node@22`, and `git`. It does not run `npm` or
`pip` during install. ZCode desktop app installation remains separate and should
point to the official ZCode docs.

## Prepare A Release Candidate

Before creating a tag, run:

```bash
git status -sb
git diff --check
bash scripts/check.sh
ruby -c packaging/homebrew/zcode-supervisor.rb
```

Then inspect the formula placeholder:

```bash
rg -n 'url|version|sha256|python@3.11|node@22' packaging/homebrew/zcode-supervisor.rb
```

The checked-in formula may contain the next planned version and a placeholder
SHA256. That is expected before a real release artifact exists.

The checked-in formula may also temporarily point at the previous tap-hosted
asset until the matching product-repo release asset exists. For future releases,
run `scripts/update-homebrew-formula` after the product-repo asset is published;
the updater defaults to `AkiGarage/ZCode-supervisor`.

## Build And Attest Release Artifacts

After Aki approves release creation, create and push a tag such as `v0.0.2`.
Then run the `Release artifacts` GitHub Actions workflow for that exact tag.

Use:

- `create_draft_release=false` for validation-only artifact generation.
- `create_draft_release=true` only when creating a draft GitHub Release is
  explicitly approved.

The workflow checks out `refs/tags/<tag>`, runs `bash scripts/check.sh`, creates
`dist/zcode-supervisor-vX.Y.Z.tar.gz`, writes `dist/SHA256SUMS`, attests both
files with `actions/attest-build-provenance@v4`, and uploads workflow artifacts.
Workflow artifacts are useful for validation, but they are not the public
download URL used by Homebrew.

The workflow permissions are intentionally narrow:

- `attestations: write`
- `contents: write`
- `id-token: write`

## Verify The Release Artifact

Download the archive and `SHA256SUMS`, then verify both:

```bash
shasum -a 256 -c SHA256SUMS
gh attestation verify zcode-supervisor-v0.0.2.tar.gz \
  -R AkiGarage/ZCode-supervisor
gh attestation verify SHA256SUMS \
  -R AkiGarage/ZCode-supervisor
```

## Update The Formula

For local validation, update a copied formula with the local archive and an
explicit `file://` URL. Do not copy that formula to the public tap.

For the public tap, first make sure the GitHub Release asset is actually
published and downloadable at:

```text
https://github.com/AkiGarage/ZCode-supervisor/releases/download/v0.0.2/zcode-supervisor-v0.0.2.tar.gz
```

That normally means running the workflow with `create_draft_release=true`,
verifying the draft assets, then publishing the draft release after approval.
Only after the release asset is public should you update the tap formula with
the default GitHub Release URL:

```bash
python3 scripts/update-homebrew-formula \
  --version v0.0.2 \
  --artifact dist/zcode-supervisor-v0.0.2.tar.gz
```

The script updates:

- `url`
- `version`, when the formula has an explicit `version` line
- `sha256`

It does not create tags, GitHub Releases, or tap repositories.

For a dry run:

```bash
python3 scripts/update-homebrew-formula \
  --version v0.0.2 \
  --artifact dist/zcode-supervisor-v0.0.2.tar.gz \
  --dry-run
```

## Test The Formula Through A Temporary Tap

Prefer a temporary local tap for E2E testing. Some Homebrew environments reject
direct path formula installs, so this better matches the real user path.

```bash
tmp="$(mktemp -d)"
artifact="$tmp/zcode-supervisor-v0.0.2.tar.gz"
tap="$tmp/homebrew-zcode-supervisor-e2e"

git archive \
  --format=tar.gz \
  --prefix="zcode-supervisor-v0.0.2/" \
  -o "$artifact" \
  HEAD

mkdir -p "$tap/Formula"
cp packaging/homebrew/zcode-supervisor.rb "$tap/Formula/zcode-supervisor.rb"

python3 scripts/update-homebrew-formula \
  --version v0.0.2 \
  --artifact "$artifact" \
  --url "file://$artifact" \
  --formula "$tap/Formula/zcode-supervisor.rb"

git -C "$tap" init
git -C "$tap" add Formula/zcode-supervisor.rb
git -C "$tap" commit -m "Add zcode-supervisor formula"

brew tap AkiGarage/zcode-supervisor-e2e "file://$tap"
brew install --build-from-source AkiGarage/zcode-supervisor-e2e/zcode-supervisor
brew test AkiGarage/zcode-supervisor-e2e/zcode-supervisor
```

Smoke test the installed commands from the Homebrew prefix so local wrapper
scripts cannot accidentally shadow the installed package:

```bash
formula="AkiGarage/zcode-supervisor-e2e/zcode-supervisor"
prefix="$(brew --prefix "$formula")"
target="$(mktemp -d)/target"
git init "$target"

"$prefix/bin/zcode-install-repo" "$target"
test -f "$target/.codex/zcode-routing.json"
test -f "$target/.codex/ZCODE_DELEGATION.md"
test -f "$target/.agents/mcp.json"
test -f "$target/AGENTS.md"

"$prefix/bin/zcode-auto-route" \
  --workspace "$target" \
  --objective "setup smoke check"

"$prefix/bin/zcode-supervisor" --help
"$prefix/bin/zcode-eval" --help
"$prefix/bin/zcode-release-check" --help
```

Cleanup:

```bash
brew uninstall AkiGarage/zcode-supervisor-e2e/zcode-supervisor
brew untap AkiGarage/zcode-supervisor-e2e
```

## Publish The Tap

Only after approval:

1. Confirm `AkiGarage/ZCode-supervisor` is the public product repo and contains
   only the approved public snapshot.
2. Confirm `AkiGarage/homebrew-zcode-supervisor` exists as the public Formula
   tap repo.
3. Confirm the GitHub Release is published, not only uploaded as a workflow
   artifact or left as a draft.
4. Confirm the release asset URL in `packaging/homebrew/zcode-supervisor.rb`
   downloads without authentication.
5. Copy the verified formula to `Formula/zcode-supervisor.rb`.
6. Commit the formula update in the tap.
7. Test the public tap:

```bash
brew tap AkiGarage/zcode-supervisor
brew install zcode-supervisor
brew test zcode-supervisor
```

After this passes, update README wording from planned Homebrew install to active
Homebrew install.

## Known Release Notes

- Homebrew `python@3.11` should be invoked through
  `Formula["python@3.11"].opt_libexec/"bin/python3"`.
- Keep `node@22` and the Python `opt_libexec/"bin"` directory on wrapper `PATH`
  so Python scripts can call the bundled Node controller when needed.
- Do not add postinstall network behavior beyond Homebrew fetching the pinned
  release artifact.
- Do not include API keys, ZCode credentials, provider secrets, `.env` files, or
  local Codex state in release artifacts.
