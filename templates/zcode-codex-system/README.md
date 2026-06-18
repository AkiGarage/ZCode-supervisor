# ZCode Codex System Template

This template makes ZCode a bounded executor while Codex stays the orchestrator
and final auditor.

## Setup In A Target Workspace

You normally do not copy this template by hand. From Terminal, run the installer
from any folder and pass the absolute path to the target repo:

```bash
zcode-install-repo /ABSOLUTE/PATH/TO/YOUR/TARGET_REPO
```

Replace `/ABSOLUTE/PATH/TO/YOUR/TARGET_REPO` with the path printed by `pwd`
inside the repo you want ZCode to help edit. The installer writes the routing
files and an `AGENTS.md` pointer for you.

After setup, run a dry route check before implementation work:

```bash
zcode-auto-route \
  --workspace /ABSOLUTE/PATH/TO/YOUR/TARGET_REPO \
  --objective "Describe the task you want implemented."
```

Only run with `--execute` after Codex has chosen:

- the exact files ZCode may edit
- the validation command Codex will rerun
- the risk budget and changed-file limit

## Copy Targets

- Copy `AGENTS.md` into the target workspace root.
- Treat `.zcode/cli/agents/` as legacy draft role prompts only. Current ZCode
  docs do not support user-defined custom subagents from Markdown files.
- Keep this local to disposable worktrees or test workspaces until the workflow
  is proven on the project.

## Operating Model

1. Codex writes a small implementation packet:
   - objective
   - allowed files
   - forbidden files
   - validation commands
   - expected final report
2. ZCode executes inside the workspace.
3. Codex audits:
   - changed files
   - test output
   - behavior against acceptance criteria
   - hidden risk from broad edits
4. Codex either accepts, asks ZCode for a bounded repair, or reverts only its
   own test-workspace changes.

## Supervisor Gate

Use `tools/zcode_supervisor/zcode_supervisor.py` when the project has access to
this repo's tooling:

- `packet` creates a compact prompt with allowed files, forbidden files,
  validation command, and an approximate prompt-token estimate.
- `snapshot` hashes the workspace before ZCode edits.
- `audit` compares the post-run workspace against the packet and snapshot,
  runs validation, and blocks forbidden edits or secret-like content.

## Mode Policy

- Use `Plan` for risky, unclear, migration, security, or production work.
- Use `Auto Edit` for trusted edit tasks where commands still need scrutiny.
- Use `Full Access` only in disposable worktrees or fixture workspaces.
- Use `Confirm Before Changes` when touching durable config or shared repos.

## Parallel Use

Preferred first layer: ask ZCode to use the built-in read-only Explore subagent
for independent code search, call-chain mapping, or risk discovery. Use Skills
or Commands for reusable review, test-debugging, or docs drafting workflows.

Preferred second layer: Codex creates separate worktrees or fixture directories,
then runs separate ZCode tasks against isolated workspaces. Do not let two ZCode
tasks edit the same files at the same time.

## Goal Mode

Use `/goal` when the desired state is objective and testable:

```text
/goal Fix <specific issue>. Success means <exact behavior>. Do not edit
<forbidden files>. Run <test command> and stop only when it passes.
```

Good goal prompts are specific, verifiable, and include a final report format.

See also:

- `QUALITY_GATE.md`
- `PARALLEL_PLAYBOOK.md`
- `GLM52_PLAYBOOK.md`
