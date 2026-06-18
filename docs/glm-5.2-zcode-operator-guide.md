# GLM-5.2 ZCode Operator Guide

<p align="right">
  <a href="./glm-5.2-zcode-operator-guide.md"><kbd>English</kbd></a>
  <a href="./glm-5.2-zcode-operator-guide.ja.md"><kbd>日本語で読む</kbd></a>
</p>

This guide turns the public GLM-5.2 release information into a practical
Codex-to-ZCode operating system.

Sources:

- https://z.ai/blog/glm-5.2
- https://docs.z.ai/guides/llm/glm-5.2
- https://huggingface.co/zai-org/GLM-5.2

## Read This After The Setup Guide

Start with the repository README first. This guide is the second step: use it
when the target repo already has ZCode routing hints and you want to decide
which tasks should go to ZCode.

Before using this guide, confirm:

1. ZCode is installed and signed in.
2. The target repo has already run
   `zcode-install-repo /ABSOLUTE/PATH/TO/YOUR/TARGET_REPO`.
3. `zcode-auto-route --workspace /ABSOLUTE/PATH/TO/YOUR/TARGET_REPO --objective "..."`
   returns a route decision.
4. Codex has chosen a small allowed-file set and a real validation command.

You can run the commands from any Terminal folder when the workspace path is
absolute. Replace every `/ABSOLUTE/PATH/TO/YOUR/TARGET_REPO` example with the
absolute path printed by `pwd` inside your target repo.

## What Matters For Codex Delegation

GLM-5.2 is positioned as a long-horizon engineering model with a usable 1M
context, 128K maximum output tokens, thinking modes, tool/function calling,
context caching, structured output, and MCP support. The key practical point is
not "paste more context"; it is that the model is trained for sustained coding
agent trajectories where architecture, standards, and earlier decisions need to
remain stable.

For ZCode, that means Codex should delegate tasks where long memory and
multi-step execution matter, while keeping final acceptance and safety gates in
Codex.

The release material also frames GLM-5.2 as usable through ZCode, Claude Code,
OpenCode, hosted APIs, and open weights. Treat that as a benchmark opportunity:
compare the same model under different agent harnesses instead of assuming the
model alone determines the result.

## Time-Sensitive Plan Notes

The Z.AI blog describes Coding Plan quota and ZCode quota promotions that are
date- and plan-dependent. Do not hard-code those claims into benchmark
decisions. When quota efficiency matters, verify the current plan page or app UI
on the test day and record the date, timezone, visible quota, and whether the
run happened in a peak or off-peak window.

ZCode 3.1.0 added a Usage and Quota entry point, 3.1.1 improved task startup,
model retention, remote workspace behavior, and tool environment inheritance,
and 3.1.2 added proxy certificate/bypass controls while fixing resumed-task
thinking level and MCP HTTP header handling. For supervisor runs, capture Usage
Stats before and after each task with `zcodectl usage`, then record
`tokens_used` and `quota_percent_used` in the evaluation ledger. Treat remote
or WSL workspaces as higher-audit surfaces until the local snapshot can prove
exactly what changed.

The installed 3.1.2 desktop bundle includes a headless CLI at
`/Applications/ZCode.app/Contents/Resources/glm/zcode.cjs`; this environment
reports bundled CLI version `0.14.8`. For Codex
orchestration, prefer `zcodectl run-packet` over GUI/CDP whenever possible:
the CLI accepts `--prompt`, `--cwd`, `--mode`, `--target`, `--resume`, and
`--json`, which makes it a cleaner automation surface for bounded packets.

Current ZCode Agent docs say project instructions are read from user-level
`~/.zcode/AGENTS.md` and the current workspace `AGENTS.md`, with workspace
instructions acting as the primary project source. `CLAUDE.md` is only a
one-time onboarding migration source, not a continuously read runtime file.
Keep the bounded worker contract in the workspace `AGENTS.md` when delegating.

Current ZCode subagent docs list only the built-in read-only Explore subagent
as supported. Do not depend on user-defined custom subagent markdown files for
runtime behavior; turn reusable workflows into Skills or Commands instead.

## Task Classes

Use `zcode_supervisor packet --task-class <class>` to tell ZCode how to use
GLM-5.2.

| Task class | Use when | Default effort | Context strategy |
|---|---|---:|---|
| `small-fix` | Narrow bug or tiny implementation | `high` or `max` | Read only touched files and tests |
| `root-cause` | Bug spans call chains, config, logs, or state | `max` | Trace related modules before editing |
| `architecture` | Need project inventory or refactor plan | `max` | Preserve module boundaries and contracts |
| `production-gate` | Need strict standards compliance | `max` | Include rules, lint/build/test commands, prohibited ops |
| `mobile-debug` | Client/mobile/ADB/logcat/screenshots loop | `max` | Include reproduction path and runtime evidence |
| `research` | Automated research or performance optimization | `max` | Keep source map and verification plan |
| `long-horizon` | Multi-step build/test/fix loops | `max` | Use `/goal` with explicit completion criteria |

## Effort Policy

Use `max` for:

- long-horizon implementation
- cross-module debugging
- production-grade standard checks
- architecture mapping
- mobile/client debugging
- tasks expected to require several repair iterations

Use `high` for:

- cheap health checks
- simple read-only review
- small code edits with tight allowed files
- benchmark probes where latency matters

The GLM-5.2 release material emphasizes flexible effort as a way to trade
latency/cost against coding capability. Do not spend `max` effort on trivial
probing unless the result will be reused.

## Context Policy

Treat 1M context as architectural continuity, not a license to dump everything.

Good context:

- repo standards
- module boundary map
- failing tests
- call chain snippets
- relevant config
- logs and reproduction steps
- accepted constraints and prohibited operations

Bad context:

- raw whole-repo dumps for a one-file fix
- duplicate transcripts
- secrets or `.env*`
- build outputs and caches
- screenshots/logs without a reproduction question

## UX-Safe Automation Rules

Prefer guardrails that remove human review work instead of adding new rituals.

- Block `Full Access` unless the packet marks the workspace as `worktree`,
  `disposable`, or `fixture`.
- Set `--max-changed-files` for narrow tasks so broad edits fail audit without
  manual inspection.
- Keep `--risk-budget low` by default. Raise it only when Codex has already
  chosen the broader scope.
- Reject destructive validation commands at packet creation; validation should
  prove safety, not change state destructively.

## ZCode Prompt Pattern

```text
/goal You are a ZCode worker under Codex audit.
Workspace: <workspace>
Workspace kind: <regular|worktree|disposable|fixture>
Objective: <specific outcome>
GLM-5.2 task class: <task-class>
GLM-5.2 effort: max
Risk budget: low
Max changed files: <limit or not set>
Context policy: <why this context is enough>
Allowed files: <paths>
Forbidden files: <paths>
Validation: <command>

Before editing, map the relevant module boundaries and call chain if the task
class is root-cause, architecture, production-gate, mobile-debug, or
long-horizon. Do not change tests unless they are explicitly allowed. Run
validation and report changed files, result, and residual risk.
```

## ZCode Mode Policy

- `Plan`: uncertain requirements, migrations, data loss risk, security work.
- `Auto Edit`: normal implementation where command execution still deserves
  review.
- `Full access`: disposable fixture or isolated worktree only, with mandatory
  snapshot/audit.
- `/goal`: objective tasks with exact validation and a clear stop condition.

## Best ZCode-GLM-5.2 Jobs

1. Project inventory before a refactor.
2. Cross-module root cause analysis.
3. Long-running implementation with repeated test/fix loops.
4. Production standards stress test.
5. Client/mobile debugging with logs, screenshots, and runtime feedback.
6. Performance optimization with benchmark evidence.

## Anti-Patterns

- Asking ZCode to own planning, implementation, and final acceptance.
- Running Full Access in a shared production workspace.
- Allowing changes outside `allowed_files`.
- Feeding the whole repository when a targeted packet would work.
- Accepting a pass without Codex re-running validation.
- Comparing ZCode and other workers without measuring approvals, time, file
  churn, tests, and token/quota data when visible.

## Local/Open-Weight Note

The Hugging Face model card lists GLM-5.2 under an MIT license and documents
SGLang, vLLM, xLLM, Transformers, and KTransformers deployment paths. The model
card also lists a very large parameter count and BF16/F32 tensor types. For this
project, local serving is a research path, not the default Codex worker route.
The default route remains ZCode or hosted API access with Codex-side
supervision.
