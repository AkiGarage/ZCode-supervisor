# ZCode Master Operator

Use this when the user asks Codex to operate, benchmark, or delegate work to ZCode.

## Objective

Codex remains the orchestrator and final auditor. ZCode is a GLM-optimized
executor running inside a bounded workspace.

## Workflow

1. Create or select a safe workspace.
   - Prefer a disposable fixture, worktree, or copied benchmark directory.
   - Never use `Full Access` in a production workspace.
2. Write a task packet.
   - objective
   - allowed files
   - forbidden files
   - validation command
   - expected final report
   - approximate prompt-token budget
   - GLM-5.2 task class
   - GLM-5.2 effort
   - risk budget
   - max changed files when the expected diff is small
   - workspace kind
   - context policy
3. Snapshot the workspace before ZCode runs.
   - Prefer `tools/zcode_supervisor/zcode_supervisor.py snapshot`.
   - This is mandatory for `Full Access`.
4. Prefer the bundled ZCode headless CLI when available.
   - Check with `zcodectl cli-preflight`.
   - If `prompt_ready` is false, run
     `zcodectl bootstrap-cli-config --provider zai --model glm-5.2`.
     This copies the local GUI Coding Plan API key into the CLI config with
     redacted output and `0600` permissions.
   - Run packets with `zcodectl run-packet --packet <path> --mode <mode>`.
   - `cli-prompt` and `run-packet` auto-bootstrap by default; use
     `--no-bootstrap` only when intentionally testing preflight failure.
   - Use GUI/CDP only for desktop inspection or visible Usage Stats capture.
5. Choose ZCode mode.
   - `Plan` for ambiguous or risky work.
   - `Auto Edit` for normal implementation.
   - `Full Access` only for disposable workspaces.
6. Use `/goal` for long-running or multi-step tasks.
   - Make success criteria objective and testable.
   - Include the exact validation command.
   - Include forbidden files.
7. Use ZCode's built-in Explore subagent for read-only research when useful.
   - Current ZCode docs list Explore as the only supported subagent.
   - Do not depend on user-defined custom subagent Markdown files for runtime
     behavior.
   - Use Skills or Commands for reusable review, implementation, and test
     debugging workflows.
8. Capture Usage Stats before and after the task.
   - Open Settings usage with `zcodectl open-usage` when needed.
   - Save before and after snapshots with `zcodectl usage --out <path>`.
   - Append the run with `zcode_eval append-result --usage-before <path>
     --usage-after <path>`.
9. Codex audits after ZCode stops.
   - inspect changed files
   - run validation independently
   - compare against the pre-run snapshot
   - block forbidden or out-of-scope edits
   - scan changed files for secret-like content
   - record approvals, duration, changed files, tests, `tokens_used`, and
     `quota_percent_used`
10. Accept, repair, or reject.
   - Ask ZCode for a bounded repair only with a fresh packet.
   - Do not let repeated failed loops continue without a root-cause change.

## Supervisor Commands

```bash
python3 tools/zcode_supervisor/zcode_supervisor.py packet \
  --workspace <workspace> \
  --objective "<objective>" \
  --allowed <file> \
  --forbidden <file> \
  --validation "<command>" \
  --effort max \
  --task-class root-cause \
  --risk-budget low \
  --max-changed-files <n> \
  --goal \
  --out .local/packets/<task>.json \
  --prompt-out .local/packets/<task>.prompt.txt

python3 tools/zcode_supervisor/zcode_supervisor.py snapshot \
  --workspace <workspace> \
  --out .local/snapshots/<task>.before.json

node tools/zcode_control/zcodectl.mjs run-packet \
  --packet .local/packets/<task>.json \
  --mode plan \
  --out .local/runs/<task>.zcode.json

python3 tools/zcode_supervisor/zcode_supervisor.py audit \
  --workspace <workspace> \
  --snapshot .local/snapshots/<task>.before.json \
  --packet .local/packets/<task>.json

node tools/zcode_control/zcodectl.mjs usage \
  --out .local/usage/<task>.after.json

python3 tools/zcode_eval/zcode_eval.py append-result \
  --run-id <run-id> \
  --tool zcode \
  --task-id <task> \
  --task-name "<task name>" \
  --status <pass|fail|partial|blocked> \
  --usage-before .local/usage/<task>.before.json \
  --usage-after .local/usage/<task>.after.json
```

## Goal Prompt Shape

```text
/goal <specific outcome>. Success means <objective criteria>. Work only in
<workspace>. Do not edit <forbidden files>. Run <validation command> and stop
only when it passes. Final report: changed files, validation result, risks.
```

## GLM-5.2 Operating Profile

Use `max` effort for:

- long-horizon implementation
- cross-module debugging
- architecture mapping
- production-grade standards checks
- mobile/client debugging loops
- tasks expected to need repeated repair iterations

Use `high` effort for:

- cheap health checks
- small read-only reviews
- narrow repairs where latency matters

Choose task class deliberately:

- `small-fix`: one narrow behavior or file
- `root-cause`: trace code/config/logs/interfaces before editing
- `architecture`: map module boundaries and contracts
- `production-gate`: enforce style, dependencies, tests, and commit boundaries
- `mobile-debug`: ADB/logcat/screenshots/runtime loop
- `research`: source map plus verification plan
- `long-horizon`: multi-step `/goal` with exact stop condition

## Parallel Pattern

Use the native read-only Explore subagent first:

```text
First use Explore to map the relevant module boundaries, call chain, and risks
in read-only mode. Then continue in the main task with the minimal allowed-file
change and the packet validation command.
```

Use multiple ZCode tasks only across isolated workspaces or branches.

## Low-Babysitting Guardrails

- Let `zcode_supervisor` block regular-workspace `Full Access`; use
  `--workspace-kind worktree`, `disposable`, or `fixture` only when that is true.
- Set `--max-changed-files` for narrow tasks so Codex can reject broad edits
  mechanically.
- Keep `--risk-budget low` unless Codex has already accepted wider blast radius.
- Do not use destructive validation commands; validation should be a proof step.
- For ZCode 3.1.2 and later, use the Settings Usage page as the primary visible
  source for consumed token count and consumed quota percent. Keep raw usage
  snapshots so Codex can audit which UI lines were parsed.
