# ZCode Quality Gate

Use this gate for ZCode work that should be fast, safe, and auditable.

## Before You Start

Do the one-time target repo setup first:

```bash
zcode-install-repo /ABSOLUTE/PATH/TO/YOUR/TARGET_REPO
```

Run it in Terminal. You may run it from any folder as long as
`/ABSOLUTE/PATH/TO/YOUR/TARGET_REPO` is replaced with the absolute path to the
repo ZCode should help edit.

Then choose the concrete task:

- objective: what should be true when the task is done
- allowed files: the only files ZCode may edit
- forbidden files: files ZCode must not edit
- validation command: the command Codex will rerun after ZCode
- max changed files: a small number for narrow tasks

## Before ZCode

1. Create a task packet:

```bash
python3 tools/zcode_supervisor/zcode_supervisor.py packet \
  --workspace <workspace> \
  --objective "<objective>" \
  --allowed <file> \
  --forbidden <file> \
  --validation "<command>" \
  --effort max \
  --task-class production-gate \
  --risk-budget low \
  --max-changed-files <n> \
  --goal \
  --out artifacts/packets/<task>.json \
  --prompt-out artifacts/packets/<task>.prompt.txt
```

2. Create a snapshot:

```bash
python3 tools/zcode_supervisor/zcode_supervisor.py snapshot \
  --workspace <workspace> \
  --out artifacts/snapshots/<task>.before.json
```

3. Capture Usage Stats before the task:

```bash
node tools/zcode_control/zcodectl.mjs open-usage
node tools/zcode_control/zcodectl.mjs usage --out .local/usage/<task>.before.json
```

4. Submit `packet.prompt` to ZCode. Prefer the bundled headless CLI:

```bash
node tools/zcode_control/zcodectl.mjs cli-preflight
node tools/zcode_control/zcodectl.mjs run-packet \
  --packet artifacts/packets/<task>.json \
  --mode plan \
  --out .local/runs/<task>.zcode.json
```

If the CLI is unavailable, use the desktop app from a file:

```bash
node tools/zcode_control/zcodectl.mjs goal --text-file artifacts/packets/<task>.prompt.txt
```

## After ZCode

Run the audit:

```bash
python3 tools/zcode_supervisor/zcode_supervisor.py audit \
  --workspace <workspace> \
  --snapshot artifacts/snapshots/<task>.before.json \
  --packet artifacts/packets/<task>.json
```

Capture Usage Stats again and append the run:

```bash
node tools/zcode_control/zcodectl.mjs open-usage
node tools/zcode_control/zcodectl.mjs usage --out .local/usage/<task>.after.json
python3 tools/zcode_eval/zcode_eval.py append-result \
  --run-id <run-id> \
  --tool zcode \
  --task-id <task> \
  --task-name "<task name>" \
  --status <pass|fail|partial|blocked> \
  --usage-before .local/usage/<task>.before.json \
  --usage-after .local/usage/<task>.after.json
```

Accept only when:

- no forbidden files changed
- no files outside `allowed_files` changed
- changed file count stays within `max_changed_files` when set
- validation passes
- no secret-like content is introduced
- Codex agrees the behavior matches the acceptance criteria

## Token Efficiency Rules

- Put exact acceptance criteria in the packet.
- List only files ZCode may edit.
- Avoid pasting file contents into the prompt unless the file is tiny.
- Prefer one `/goal` with a validation command over repeated manual nudges.
- Record elapsed time, approvals, changed files, tests, `tokens_used`, and
  `quota_percent_used` when available.

## GLM-5.2 Fields

- `--effort max`: use for long-horizon, root-cause, architecture, production,
  mobile, and multi-round Goal work.
- `--effort high`: use for cheap probes and small reviews.
- `--task-class`: choose `small-fix`, `long-horizon`, `architecture`,
  `root-cause`, `production-gate`, `mobile-debug`, or `research`.
- `--risk-budget low`: default for narrow tasks; raise only when Codex accepts
  broader scope.
- `--max-changed-files`: use for small tasks to prevent broad, surprising diffs.
