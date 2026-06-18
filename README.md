![ZCode Supervisor Toolkit hero](assets/images/zcode-supervisor-toolkit-hero.png)

<p align="center">
  <strong>Language / 言語</strong><br>
  <a href="./README.md"><kbd>English</kbd></a>
  <a href="./README.ja.md"><kbd>日本語で読む</kbd></a>
</p>

# ZCode-supervisor

![Version](https://img.shields.io/badge/version-v0.0.1-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Node](https://img.shields.io/badge/node-%3E%3D22-339933)
![Python](https://img.shields.io/badge/python-%3E%3D3.11-3776AB)

Codex-side tooling for using ZCode as a bounded coding worker while Codex stays
the orchestrator and final auditor.

**日本語版はこちら:** [README.ja.md を開く](./README.ja.md)

This repository is not affiliated with Z.AI or ZCode.

## Quick Start

The current public setup path is `uvx` from this GitHub repo:

```bash
uvx --from git+https://github.com/AkiGarage/ZCode-supervisor.git \
  zcode-install-repo /ABSOLUTE/PATH/TO/YOUR/TARGET_REPO
```

After the first PyPI release, the shorter package command will be:

```bash
uvx --from zcode-supervisor zcode-install-repo /ABSOLUTE/PATH/TO/YOUR/TARGET_REPO
```

Then check the routing decision before the first delegated task:

```bash
zcode-auto-route \
  --workspace /ABSOLUTE/PATH/TO/YOUR/TARGET_REPO \
  --objective "setup smoke check"
```

For development from source, clone this repo and run the underlying Python
command directly:

```bash
git clone https://github.com/AkiGarage/ZCode-supervisor.git
cd ZCode-supervisor
python3 tools/zcode_supervisor/zcode_supervisor.py install-repo \
  --repo /ABSOLUTE/PATH/TO/YOUR/TARGET_REPO \
  --write-agents
```

The Homebrew tap is archived for now; clone `AkiGarage/ZCode-supervisor` for
source work.

Release details and verification commands are in
[docs/distribution.md](docs/distribution.md).

## Ask Codex To Set It Up

If you want Codex to do the setup for you, copy this whole prompt into Codex.
GitHub shows a copy button on the code block. Replace
`/ABSOLUTE/PATH/TO/YOUR/TARGET_REPO` with the absolute path to the repo you want
ZCode to help edit.

```text
You are Codex. Please set up ZCode-supervisor for this target repo:

TARGET_REPO=/ABSOLUTE/PATH/TO/YOUR/TARGET_REPO

Goal:
Make this target repo ready for the ZCode-supervisor workflow where Codex keeps
planning, orchestration, validation, audit, recovery, and final acceptance, and
ZCode only performs bounded implementation through zcodectl run-packet.

Rules:
- Be careful and non-destructive.
- Do not read or print secrets, .env files, credentials, API keys, private keys,
  or token files.
- Do not edit application source code in the target repo during setup.
- If TARGET_REPO is still a placeholder, stop and ask me for the real absolute
  path.
- If a required app or tool is missing, stop with the exact missing prerequisite
  and the next command or official link I should use.
- Do not push, commit, delete branches, or change production behavior.

Steps:
1. Confirm TARGET_REPO exists and is a git repository.
2. Prefer the public GitHub-backed `uvx` path. If `uvx --version` works, set
   INSTALLER_MODE=uvx and do not clone anything. If `uvx` is missing, show this
   official install link and continue with the source fallback:
   https://docs.astral.sh/uv/getting-started/installation/
3. For source fallback only, find this ZCode-supervisor repo locally. Prefer
   ~/dev/ZCode-supervisor if it exists. Set SUPERVISOR_REPO to the real absolute
   path. If it is not present, clone it with:
   mkdir -p ~/dev
   git clone https://github.com/AkiGarage/ZCode-supervisor.git ~/dev/ZCode-supervisor
   If clone fails, stop and report the exact error.
4. Verify local basics:
   - node --version must be >= 22
   - python3 --version must be >= 3.11
   - git --version must work
5. Verify ZCode is installed or give me this official install link:
   https://zcode.z.ai/en/docs/install
6. Run the target repo installer from Terminal or shell. If INSTALLER_MODE=uvx:
   uvx --from git+https://github.com/AkiGarage/ZCode-supervisor.git \
     zcode-install-repo "$TARGET_REPO"
   Otherwise run the source fallback:
   python3 "$SUPERVISOR_REPO/tools/zcode_supervisor/zcode_supervisor.py" install-repo \
     --repo "$TARGET_REPO" \
     --write-agents
7. Verify these files now exist inside TARGET_REPO:
   - .codex/zcode-routing.json
   - .codex/ZCODE_DELEGATION.md
   - .agents/mcp.json
   - AGENTS.md
8. Run a dry route check. If INSTALLER_MODE=uvx:
   uvx --from git+https://github.com/AkiGarage/ZCode-supervisor.git \
     zcode-auto-route \
     --workspace "$TARGET_REPO" \
     --objective "setup smoke check"
   Otherwise run:
   python3 "$SUPERVISOR_REPO/tools/zcode_supervisor/zcode_supervisor.py" auto-route \
     --workspace "$TARGET_REPO" \
     --objective "setup smoke check"
9. If possible, run preflight. If INSTALLER_MODE=uvx:
   uvx --from git+https://github.com/AkiGarage/ZCode-supervisor.git \
     zcodectl cli-preflight
   uvx --from git+https://github.com/AkiGarage/ZCode-supervisor.git \
     zcodectl vision-preflight --workspace "$TARGET_REPO"
   Otherwise run:
   node "$SUPERVISOR_REPO/tools/zcode_control/zcodectl.mjs" cli-preflight
   node "$SUPERVISOR_REPO/tools/zcode_control/zcodectl.mjs" vision-preflight --workspace "$TARGET_REPO"
10. Report:
   - what was written
   - commands run
   - pass/fail result for each check
   - anything I still need to do manually
   - the exact command I should use for the first real delegated task

Success means the target repo has routing files installed, a dry route check
works, and I understand any remaining manual prerequisite.
```

## Setup Guide: Set Up One Target Repo

Use this section when you are starting from zero. The goal is to mark one
existing repository as a place where Codex can plan and audit while ZCode does
bounded implementation work.

### 0. Know The Two Repositories

- **This repo:** `ZCode-supervisor`. It contains the supervisor tools.
- **Target repo:** the repo you want ZCode to help edit. This is the path you
  pass to `zcode-install-repo`.

`/path/to/target-repo` is a placeholder. Replace it with the absolute path to
your own target repo, such as:

```bash
~/work/my-app
```

You can get the absolute path by opening Terminal, moving into the target repo,
and running:

```bash
pwd
```

### 1. Put This Supervisor Repo On Disk

If you are reading this on GitHub and do not have the repo locally yet, clone
it first:

```bash
git clone https://github.com/AkiGarage/ZCode-supervisor.git
cd ZCode-supervisor
pwd
```

The `pwd` output is the absolute path to this supervisor repo. If your clone is
not at `~/dev/ZCode-supervisor`, replace that path in examples with
your own supervisor repo path.

### 2. Install The Required Apps And Tools

Install and sign in to ZCode first:

- ZCode install docs: https://zcode.z.ai/en/docs/install

Minimum local tools:

- ZCode desktop app installed and connected to a model provider.
- Node.js `>=22`.
- Python `>=3.11`.
- Git.
- A POSIX-like shell such as the default macOS Terminal shell.
- Network access to the configured model provider.

Check the local basics:

```bash
node --version
python3 --version
git --version
```

### 3. Run The Installer From Terminal

Run this in Terminal. You may run it from any current folder, because the
target repo is provided as an absolute path:

```bash
zcode-install-repo /ABSOLUTE/PATH/TO/YOUR/TARGET_REPO
```

Example:

```bash
zcode-install-repo ~/work/my-app
```

This command is setup only. Run it once per target repo; it is not a per-task
command.

If `zcode-install-repo` is not found, run the supervisor command directly from
this repo:

```bash
python3 /absolute/path/to/ZCode-supervisor/tools/zcode_supervisor/zcode_supervisor.py install-repo \
  --repo /ABSOLUTE/PATH/TO/YOUR/TARGET_REPO \
  --write-agents
```

If your supervisor repo lives somewhere else, replace
`/absolute/path/to/ZCode-supervisor` with the absolute path from `pwd` in step 1.

### Primary Install Path

The current public setup path is `uvx` from this GitHub repo:

```bash
uvx --from git+https://github.com/AkiGarage/ZCode-supervisor.git \
  zcode-install-repo /ABSOLUTE/PATH/TO/YOUR/TARGET_REPO
```

After the first PyPI release, the shorter package command will be:

```bash
uvx --from zcode-supervisor zcode-install-repo /ABSOLUTE/PATH/TO/YOUR/TARGET_REPO
```

The PyPI package is published through Trusted Publishing, without long-lived
PyPI tokens. High-assurance users can also download the GitHub Release archive,
verify `SHA256SUMS`, and run `gh attestation verify` before using it. Homebrew
is archived for now; see [docs/distribution.md](docs/distribution.md).

### 4. Confirm What Was Written

The installer writes these files inside the target repo:

- `.codex/zcode-routing.json`
- `.codex/ZCODE_DELEGATION.md`
- `.agents/mcp.json`
- `AGENTS.md` pointer text, when `--write-agents` is used

The important rule is simple: Codex keeps planning, orchestration, validation,
audit, recovery, and final acceptance. ZCode only handles bounded
implementation through `zcodectl run-packet`.

### 5. Check The Route Before Editing

Use a dry run before implementation work:

```bash
zcode-auto-route \
  --workspace /ABSOLUTE/PATH/TO/YOUR/TARGET_REPO \
  --objective "Fix the failing ledger summary test."
```

Typical results:

- `needs_codex_planning`: Codex should choose allowed files and validation.
- `delegate_zcode`: the task is ready to run through ZCode.
- `codex_direct`: Codex can handle it directly.
- `ask_user`: pause because the task is high risk.

### 6. Run A Real Delegated Task

After Codex has chosen a tight edit scope and validation command:

```bash
zcode-auto-route \
  --workspace /ABSOLUTE/PATH/TO/YOUR/TARGET_REPO \
  --objective "Fix the failing ledger summary test." \
  --allowed src/ledger.js \
  --validation "npm test" \
  --execute
```

Use `--allowed` for files ZCode may edit. Use `--validation` for the command
Codex will trust as the first safety check. Keep both narrow.

### Troubleshooting The First Run

- `command not found: zcode-install-repo`: use the direct `python3 ... install-repo`
  command shown above, or add this repo's `scripts/` directory to your PATH.
- `repo does not exist`: replace the placeholder with the exact absolute path
  from `pwd`.
- ZCode cannot run prompts: open ZCode once, sign in, configure the provider,
  then run `node tools/zcode_control/zcodectl.mjs cli-preflight` from this repo.
- Vision or screenshot tasks fail preflight: run
  `node tools/zcode_control/zcodectl.mjs vision-preflight --workspace /ABSOLUTE/PATH/TO/YOUR/TARGET_REPO`.

## Repository Snapshot

- **Current version:** `v0.0.1`
- **Primary use case:** delegate bounded coding tasks to ZCode/GLM while Codex
  keeps planning, guardrails, validation, and final review.
- **Main command path:** `node tools/zcode_control/zcodectl.mjs run-packet`
- **Responsibility split:** isolate workspaces, snapshot before execution, audit
  changes after execution, and reject unsafe or out-of-scope diffs.
- **Best for:** low-babysitting AI coding workflows, reproducible tool
  comparisons, token/quota-aware delegation, and supervised benchmark runs.

## Start Here

- New user? Read [Setup Guide](#setup-guide-set-up-one-target-repo), then
  [How Codex And ZCode Share Responsibility](#how-codex-and-zcode-share-responsibility).
- Running ZCode headlessly? Read
  [Requirements And Control Surfaces](#requirements-and-control-surfaces) and
  [ZCode Desktop Control](#zcode-desktop-control).
- Comparing tools or tracking usage? Read
  [Usage, Token, And Quota Logging](#usage-token-and-quota-logging).
- Planning future work? See [ROADMAP.md](ROADMAP.md) and
  [CHANGELOG.md](CHANGELOG.md).

## What This Provides

- `zcode_supervisor`: creates task packets, snapshots workspaces, and audits
  ZCode changes after execution.
- `zcodectl`: CLI-first controller for the bundled ZCode headless CLI, with
  optional Electron CDP helpers for desktop inspection.
- Workspace-local ZCode templates for `AGENTS.md`, quality gates, parallel
  work, and Skill-friendly operating playbooks.
- Small benchmark fixtures and tests for the supervisor/audit workflow.
- A GLM-5.2/ZCode operating playbook for long-horizon coding, root-cause
  analysis, production-grade standards checks, and token-efficient delegation.
- Optional repo-local Codex usage hook shim that records session starts/stops
  through `codex-usage-ledger` when configured, with local pending JSONL
  fallback when the central ledger is unavailable.

## Version

Current release: `v0.0.1`

Distribution and release preparation: [docs/distribution.md](docs/distribution.md)

## How Codex And ZCode Share Responsibility

This project is built around a simple responsibility split:

- Codex decides the plan, allowed files, validation command, audit result, and
  final acceptance.
- ZCode does only the bounded implementation work Codex explicitly delegates.

The intended workflow is:

1. Codex creates a compact task packet.
2. Codex snapshots the workspace.
3. ZCode works inside an isolated workspace or worktree.
4. Codex runs the supervisor audit.
5. Codex independently reviews and accepts or rejects the result.

`Full access` should only be used in disposable workspaces or isolated
worktrees. Packet creation blocks regular-workspace `Full access` by default
and rejects obviously destructive validation commands. The supervisor audit
rejects forbidden edits, changes outside the allowed file set, optional changed
file count overages, validation failures, workspace mismatches, and secret-like
content in changed files.

## Command Reference After Setup

The examples in this section use shorter placeholder paths. Replace every
`/path/to/target-repo` or `/path/to/repo` with the absolute path to your real
target repo, just like in the Setup Guide above.

Install repo-local routing hints in a target repository:

```bash
zcode-install-repo /path/to/target-repo
```

Run this once per target repo. It is setup, not a per-task command.

This writes `.codex/zcode-routing.json`, `.codex/ZCODE_DELEGATION.md`, and
`.agents/mcp.json` in the target repo. It also adds a small `AGENTS.md` pointer
so Codex knows the default split: Codex plans, orchestrates, audits, validates,
and final-accepts; ZCode handles only bounded implementation through
`zcodectl run-packet`. The MCP file enables the recommended `zai-mcp-server`
stdio entry for vision packets without writing API keys into the repository.
Re-run with `--force` only when you intentionally want to refresh generated
files or replace an existing `zai-mcp-server` entry.

If the PATH wrapper is unavailable, use the underlying command:

```bash
python3 /path/to/ZCode-supervisor/tools/zcode_supervisor/zcode_supervisor.py install-repo \
  --repo /path/to/target-repo \
  --write-agents
```

## Auto Routing

Installed repos default to `routing_mode: auto`. Future Codex sessions should
run the route check before implementation edits:

```bash
zcode-auto-route \
  --workspace /path/to/target-repo \
  --objective "Fix the failing ledger summary test."
```

This check is optional when you already know the task should run through ZCode;
it is mainly a dry-run for inspecting the route decision. You do not need to run
all three setup/check/execute commands for every task:

- First-time setup: run `zcode-install-repo /path/to/target-repo` once.
- Route inspection: run `zcode-auto-route --workspace ... --objective ...`
  when you want to see the JSON decision.
- Real delegated implementation: run `zcode-auto-route ... --allowed ...
  --validation ... --execute` after Codex has selected the file scope and
  validation command.

If the user explicitly says "use ZCode", "have ZCode do it", or similar, Codex should
treat that as an instruction to use this ZCode-supervisor flow for bounded
implementation work. Codex still owns planning, orchestration, validation,
audit, recovery, and final acceptance.

The router returns JSON so Codex can proceed without asking for routine
decisions:

- `delegate_zcode`: create a packet and run ZCode.
- `needs_codex_planning`: Codex must choose a tight allowed-file set and
  validation command, then rerun with `--execute`.
- `codex_direct`: Codex may handle the task directly because it is read-only,
  trivial, missing routing config, or explicitly marked `no-zcode`.
- `ask_user`: pause for a short plan because the task matches a high-risk
  category such as destructive changes, migrations, credentials, production, or
  money-sensitive work.

For normal implementation after Codex has selected allowed files and validation:

```bash
zcode-auto-route \
  --workspace /path/to/target-repo \
  --objective "Fix the failing ledger summary test." \
  --allowed src/ledger.js \
  --validation "npm test" \
  --execute
```

`--execute` creates the packet, calls `zcodectl run-packet`, writes run results
under `.codex/zcode/runs/`, and keeps Codex responsible for final acceptance.
This is intentionally a smart default rather than a hard lock: high-risk,
read-only, trivial, and `no-zcode` tasks do not get forced through ZCode.

Create a task packet:

```bash
python3 tools/zcode_supervisor/zcode_supervisor.py packet \
  --workspace benchmarks/zcode-goal-mode \
  --objective "Fix summarizeLedger so npm test passes." \
  --allowed src/ledger.js \
  --forbidden test/ledger.test.js \
  --validation "npm test" \
  --effort max \
  --task-class root-cause \
  --risk-budget low \
  --max-changed-files 1 \
  --goal \
  --out .local/packets/ledger.json \
  --prompt-out .local/packets/ledger.prompt.txt
```

Snapshot the workspace:

```bash
python3 tools/zcode_supervisor/zcode_supervisor.py snapshot \
  --workspace benchmarks/zcode-goal-mode \
  --out .local/snapshots/ledger.before.json
```

After ZCode runs, audit the result:

```bash
python3 tools/zcode_supervisor/zcode_supervisor.py audit \
  --workspace benchmarks/zcode-goal-mode \
  --snapshot .local/snapshots/ledger.before.json \
  --packet .local/packets/ledger.json
```

## Requirements And Control Surfaces

This toolkit does not require Codex Computer Use. The preferred automation path
is the ZCode headless CLI bundled inside the ZCode desktop app:

```text
Codex or a normal terminal
  -> node tools/zcode_control/zcodectl.mjs
  -> ZCode bundled CLI
  -> ZCode / GLM task execution
```

Control surface priority:

1. **ZCode bundled headless CLI, recommended and required for headless
   delegation.** `cli-prompt` and `run-packet` use this path. It is the path
   validated by this project on macOS with ZCode 3.1.2.
2. **`cua-driver` plus Electron CDP, optional.** `cua-driver` is an MIT-licensed
   background computer-use driver from the Cua project:
   https://cua.ai/docs/cua-driver/guide/getting-started/introduction
   When available, GUI helpers can use this kind of desktop-control surface to
   inspect visible text, take screenshots, click buttons, and read visible
   Usage Stats without making it the primary delegation path. Thanks to the Cua
   authors for the computer-use driver work; this project uses that capability
   only as an optional diagnostic/control surface.
3. **Codex Computer Use, optional fallback only.** It can operate the GUI when
   available, but this repository does not depend on it and does not require it
   for the primary workflow.

Minimum local tooling:

- ZCode desktop app installed and connected to a model provider.
- Node.js `>=22`.
- Python `>=3.11`.
- Git and a POSIX-like shell for `scripts/check.sh`.
- Network access to the configured model provider.

The latest official ZCode install docs list these supported platforms:

- macOS on Apple Silicon and Intel.
- Windows.
- Linux through the Linux beta group.

See the official ZCode install docs:
https://zcode.z.ai/en/docs/install

Project support status:

| Platform | Status | Notes |
| --- | --- | --- |
| macOS | Tested | ZCode 3.1.2, bundled CLI path `/Applications/ZCode.app/Contents/Resources/glm/zcode.cjs`, bundled CLI version `0.14.8`, GUI config path `~/.zcode/v2/config.json`, CLI config path `~/.zcode/cli/config.json`. |
| Windows | Expected, not verified | ZCode is officially supported and 3.1.2 adds Windows shell selection, but this project still needs Windows-specific CLI path discovery and shell validation. Set `ZCODE_CLI_PATH` if auto-detection does not find the bundled CLI. |
| Linux | Expected/beta, not verified | ZCode Linux packages are distributed through the official beta group, but this project has not validated Linux CLI paths, desktop launch, or config discovery yet. Set `ZCODE_CLI_PATH`, `--source-config`, and `--cli-config` as needed. |

`bootstrap-cli-config` can copy a local ZCode GUI Coding Plan API key into the
ZCode CLI config with `0600` permissions and redacted output. On non-macOS
systems, pass explicit config paths if the defaults do not match the installed
ZCode layout:

```bash
node tools/zcode_control/zcodectl.mjs bootstrap-cli-config \
  --provider zai \
  --model glm-5.2 \
  --source-config /path/to/gui/config.json \
  --cli-config /path/to/cli/config.json
```

## ZCode Desktop Control

`zcodectl` is intentionally small and experimental. Its primary path is the
bundled ZCode headless CLI. Its GUI helpers expect ZCode to be available as a
desktop app and use Electron CDP after launch.

For ZCode 3.1.2 and later, prefer the bundled headless CLI when it is available:

```bash
node tools/zcode_control/zcodectl.mjs cli-path
node tools/zcode_control/zcodectl.mjs cli-preflight
node tools/zcode_control/zcodectl.mjs bootstrap-cli-config \
  --provider zai \
  --model glm-5.2
node tools/zcode_control/zcodectl.mjs cli-doctor
node tools/zcode_control/zcodectl.mjs run-packet \
  --packet .local/packets/ledger.json \
  --mode plan \
  --max-attempts 2 \
  --retry-delay-ms 60000 \
  --usage-snapshot-source auto \
  --out .local/runs/ledger.zcode.json
```

`run-packet` sends the supervisor-generated packet prompt to the bundled
ZCode CLI with the packet workspace as `--cwd`. It avoids GUI/CDP fragility and
is the preferred Codex control path for headless delegation. If the CLI config
is not ready, `cli-prompt` and `run-packet` try to bootstrap it from the local
ZCode desktop GUI config before sending the prompt. Pass `--no-bootstrap` to
disable that behavior. Use `cli-prompt` for ad-hoc prompts:

`run-packet` treats ZCode provider overload as structured supervisor state. It
classifies `ProviderBusinessError`, provider code `1305`, temporary overload
messages, and CLI exit code `143`. Every attempt is audited by the Codex-side
supervisor after the ZCode turn, so validation does not depend on ZCode's
internal Bash/tool permission client. The result returns `supervisor_state`:

- `success`: CLI completed normally and supervisor audit plus validation passed.
- `audit_failed`: CLI completed normally, but supervisor audit or validation
  failed.
- `partial_success`: provider error happened after scoped changes, and audit
  plus validation passed.
- `retryable_provider_error`: provider error happened with no file changes.
- `unsafe_partial`: provider error happened with changed files that failed
  scope, validation, or safety checks.

Safe no-change provider errors retry up to `--max-attempts` with
`--retry-delay-ms` cooldown. Changed files are never blindly retried; they are
audited first. The JSON result includes `cli_ok`, `provider_error`,
`provider_code`, `provider_message`, `provider_id`, `provider_kind`,
`usage_available`, `attempts`, `retry_count`, `retry_delays_ms`,
`safe_to_retry_later`, `partial_artifacts_possible`, `audit`, `validation`,
`validation_ok`, and compact `attempt_results`.

`run-packet` also captures before/after usage snapshots. The default
`--usage-snapshot-source auto` first calls the Z.AI quota API directly using
`ZAI_API_KEY`, `launchctl getenv ZAI_API_KEY`, or the local redacted ZCode CLI
config as the credential source. The API key is never written to result JSON or
logs. If the direct API snapshot is unavailable, `auto` falls back to the
CodexBar CLI:

```bash
codexbar usage --provider zai --format json
```

CodexBar.app does not need to be running for either path. The snapshot is
non-fatal: if both direct API and CodexBar CLI capture are missing or
unavailable, task execution continues and the JSON records the snapshot error.
When capture succeeds, the JSON includes:

- `usage_snapshots.before` and `usage_snapshots.after`: raw provider snapshots
  plus normalized quota windows. Direct Z.AI API snapshots use `source:
  "zai-api"`; CodexBar snapshots use `source: "codexbar"`.
- `usage_accounting.tokens_*`: consumed token fields normalized from the ZCode
  CLI JSON `usage` payload for this run.
- `usage_accounting.quota_percent_*`: before, after, and delta for the primary
  used-percent quota window. `quota_percent_direction` is `used`.
- Direct Z.AI `TOKENS_LIMIT.percentage` is treated as the measured used-percent
  value even when the same window omits finite `usage` and `remaining` token
  counts. The normalized window records `token_counts_available` separately, so
  percent deltas remain available without inventing token-count deltas.
- `usage_accounting.quota_windows`: per-window deltas, including reset-change
  detection so a quota-window reset is not misreported as negative usage.

Use `--usage-snapshot-source zai-api` to require direct Z.AI API capture,
`--usage-snapshot-source codexbar` to require CodexBar CLI capture, or
`--usage-snapshot-source none` to disable snapshot capture. Use
`--usage-provider zai` to make the provider explicit. `--zai-quota-url` can
point at a custom Z.AI-compatible quota endpoint for tests. `--codexbar-path`
or the `CODEXBAR_PATH` environment variable can point at a custom CodexBar CLI
path.

```bash
node tools/zcode_control/zcodectl.mjs cli-prompt \
  --workspace benchmarks/zcode-goal-mode \
  --mode plan \
  --text "Review this fixture and report the failing test cause." \
  --out .local/runs/review.json
```

`bootstrap-cli-config` reads the local ZCode GUI config, finds an existing
Coding Plan API key, and writes the CLI-native config at
`~/.zcode/cli/config.json` with `0600` permissions. Secret values are copied
locally and are not printed in command output. The default provider is `zai`
and the default model is `glm-5.2`.

`cli-preflight` checks the CLI binary, model selection, and whether a Coding
Plan API key is configured. It redacts secret values and reports
`prompt_ready=true` when headless prompts can run.

## Image And Vision Tasks

GLM-5.2 is treated as text-only in this supervisor. For image understanding,
use ZCode's built-in image service through the recommended `zai-mcp-server`
MCP service, then attach workspace-local images through the packet:

```bash
python3 tools/zcode_supervisor/zcode_supervisor.py packet \
  --workspace benchmarks/zcode-goal-mode \
  --objective "Implement the UI state shown in the screenshot." \
  --allowed src/ledger.js \
  --validation "npm test" \
  --vision-image screenshots/state.png \
  --vision-color-sample primary=screenshots/state.png@240,420 \
  --out .local/packets/vision.json
```

`--vision-image` marks image understanding as required and stores the image
paths in the packet. `run-packet` automatically forwards those paths to the
ZCode CLI as repeated `--attach` arguments. Before running a required vision
packet, `run-packet` checks redacted ZCode MCP configuration for the preferred
image service and stops with `vision_service_unavailable` if it is missing,
instead of letting the worker guess from filenames or text.

Use `--vision-color-sample name=image.png@x,y` when a task needs pixel-exact
hex colors. The supervisor reads that PNG pixel locally and injects the exact
uppercase `#RRGGBB` value into the worker prompt, while ZCode still handles the
broader image understanding. The sampler is intentionally narrow: workspace
local, non-secret, non-interlaced 8-bit RGB/RGBA PNG files.

You can check the image-service setup directly:

```bash
node tools/zcode_control/zcodectl.mjs vision-preflight \
  --workspace benchmarks/zcode-goal-mode
```

`zcode-install-repo /path/to/repo` writes `.agents/mcp.json` with the
recommended stdio server:

```json
{
  "mcpServers": {
    "zai-mcp-server": {
      "args": ["-y", "@z_ai/mcp-server"],
      "command": "npx",
      "enable": true,
      "type": "stdio"
    }
  }
}
```

The relevant ZCode docs describe `zai-mcp-server` as the recommended MCP server
for visual understanding of images, screenshots, and interface context:
https://zcode.z.ai/en/docs/mcp-services

The npm package that provides the `zai-mcp-server` binary is
`@z_ai/mcp-server`. It expects `Z_AI_API_KEY`; for required vision packets,
`run-packet` passes an available key to the ZCode child process from the current
environment, `ZAI_API_KEY`, or the local ZCode CLI config without printing the
secret value. Pixel-exact color sampling should still be verified with a
deterministic image tool when exact hex values matter; generic vision can be
close but not always exact.

The GUI/CDP helpers remain available for inspecting the desktop app and reading
visible Settings usage when CDP is exposed:

Example:

```bash
node tools/zcode_control/zcodectl.mjs launch --port 9223
node tools/zcode_control/zcodectl.mjs targets --port 9223
node tools/zcode_control/zcodectl.mjs goal --port 9223 --text-file .local/packets/ledger.prompt.txt
```

If ZCode is already running without a debug port, use
`node tools/zcode_control/zcodectl.mjs launch --port 9223 --new-instance` and
check that the launch output includes `"cdp": {"ok": true, ...}` before running
`targets`, `usage`, or `goal`.

Do not send secrets through `zcodectl eval` or prompt files.

## Usage, Token, And Quota Logging

For every delegated ZCode task, capture Usage Stats before and after the run,
then append the result to the evaluation ledger.

The current ZCode Usage Stats docs split usage into App Usage for local session
records and Coding Plan for remote Z.ai / BigModel quota, GLM-5.2 and
GLM-5-Turbo model usage, and MCP tool-call usage. Treat quota snapshots as
time-sensitive evidence and keep the raw snapshot beside the normalized eval
record.

```bash
node tools/zcode_control/zcodectl.mjs open-usage --port 9223
node tools/zcode_control/zcodectl.mjs usage --port 9223 --out .local/usage/ledger.before.json

# Run the ZCode task.

node tools/zcode_control/zcodectl.mjs open-usage --port 9223
node tools/zcode_control/zcodectl.mjs usage --port 9223 --out .local/usage/ledger.after.json

python3 tools/zcode_eval/zcode_eval.py append-result \
  --run-id zcode-ledger-001 \
  --tool zcode \
  --task-id ledger \
  --task-name "Ledger fixture" \
  --status pass \
  --validation "npm test: pass" \
  --usage-before .local/usage/ledger.before.json \
  --usage-after .local/usage/ledger.after.json
```

`append-result` records `tokens_before`, `tokens_after`, `tokens_used`,
`quota_percent_before`, `quota_percent_after`, and `quota_percent_used`. By
default, quota percent is treated as remaining quota, so consumed quota is
derived as before minus after. If the visible UI is a used-percent counter, pass
`--quota-percent-direction used`.

When recording a provider-error run, `append-result` also accepts optional
metadata: `--supervisor-state`, `--provider-error`, `--provider-code`,
`--provider-message`, `--provider-id`, `--provider-kind`, `--attempts`,
`--retry-count`, `--retryable-provider-error`,
`--partial-artifacts-possible`, `--safe-to-retry-later`, and
`--usage-available` / `--no-usage-available`.

If ZCode does not expose CDP in the current session, you can still record the
same fields explicitly:

```bash
python3 tools/zcode_eval/zcode_eval.py append-result \
  --run-id zcode-ledger-001 \
  --tool zcode \
  --task-id ledger \
  --task-name "Ledger fixture" \
  --status pass \
  --tokens-before 1000 \
  --tokens-after 1450 \
  --quota-percent-before 88.5 \
  --quota-percent-after 87.0
```

Review logs later with:

```bash
python3 tools/zcode_eval/zcode_eval.py show-log
python3 tools/zcode_eval/zcode_eval.py summarize
```

External duel runs can be imported into the same JSONL ledger. The importer
reads `results.json` plus adjacent `_control/zcode/*/zcode-result.json` files
when available, so provider overload rows keep `provider_code`, retryability,
partial-artifact status, usage availability, and quota unavailable reasons:

```bash
python3 tools/zcode_eval/zcode_eval.py import-duel-results \
  --source /path/to/ClaudeCodeGLM-supervisor/work/supervisor_duel_eval/runs/20260617-153042/results.json \
  --path artifacts/evals/zcode-vs-claude.jsonl
```

## ZCode Release Monitoring

ZCode compatibility is pinned against `config/zcode-release-baseline.json`.
Check the official changelog manually with:

```bash
python3 tools/zcode_eval/zcode_release.py check \
  --baseline config/zcode-release-baseline.json \
  --include-installed
```

The GitHub Actions workflow `.github/workflows/zcode-release-monitor.yml` runs
the same release check on a schedule. When the official ZCode version is newer
than the baseline, it runs `bash scripts/check.sh` and opens or updates a GitHub
Issue with the release notes and follow-up checklist.

## Templates

Copy `templates/zcode-codex-system/` into a disposable workspace or worktree to
give ZCode:

- a bounded worker contract via `AGENTS.md`
- Skill-friendly playbooks and a quality gate
- a parallel-work playbook
- a GLM-5.2 operating profile for choosing task class, effort, and context
  strategy

Current ZCode docs say user-defined custom subagents are not supported yet.
Use the built-in read-only Explore subagent for broad code research, and use
Skills or Commands for reusable worker behavior. The legacy
`.zcode/cli/agents/` template files are retained only as draft role prompts,
not as an advertised ZCode runtime feature.

## GLM-5.2 Operating Defaults

- Use `effort=max` for long-horizon implementation, cross-module debugging,
  architecture mapping, production-grade standards checks, and mobile/debugging
  loops.
- Use `effort=high` for cheap probes, narrow reviews, and small repairs where
  speed matters more than deep search.
- Treat 1M context as durable architectural memory, not a reason to dump every
  file into every task.
- Use `/goal` only with objective acceptance criteria and an exact validation
  command.
- Use `--max-changed-files` when the expected diff is small, so broad edits fail
  the audit automatically.
- Use `--workspace-kind fixture|worktree|disposable` before `Full Access`;
  regular workspaces are blocked by default.
- Keep Codex as final auditor even when ZCode completes the task.

See the GLM-5.2 ZCode Operator Guide:
[English](docs/glm-5.2-zcode-operator-guide.md) /
[日本語](docs/glm-5.2-zcode-operator-guide.ja.md).

## Development

Run the full local check:

```bash
bash scripts/check.sh
```

The project uses only the Python and Node standard libraries for its core
checks.

## Roadmap

See [ROADMAP.md](ROADMAP.md) for planned benchmark work.
