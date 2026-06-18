# ZCode Parallel Playbook

Use parallelism only when it reduces supervision, not when it creates merge risk.

## Safe Parallel Patterns

### Native Explore subagent

Use inside one ZCode task when work is read-heavy:

```text
First use Explore to map the problem, list relevant files, and identify the
main risks in read-only mode. Then continue in the main task and keep
implementation scoped to the allowed files in the Codex packet.
```

Current ZCode docs do not support user-defined custom subagents from Markdown
files. Do not rely on `@zcode-reviewer`, `@zcode-implementer`, or similar custom
roles at runtime; convert repeated workflows into Skills or Commands instead.

### Isolated workspaces

Use separate ZCode tasks only when each task has its own workspace or worktree.

Good:

- one fixture per benchmark
- one branch/worktree per implementation attempt
- review-only tasks that do not edit files

Bad:

- two tasks editing the same files
- Full Access in a shared production workspace
- parallel tasks without a Codex audit snapshot

## Merge Policy

Codex chooses one result after audit. Do not merge ZCode outputs blindly.

Acceptance order:

1. validation passes
2. forbidden/out-of-scope changes are absent
3. diff is smaller and clearer
4. token/approval/time cost is lower
5. residual risk is explicit

## GLM-5.2 Explore Pattern

For hard tasks, split thinking before editing:

```text
Use Explore to reduce context waste, map boundaries, trace the defect, and
collect standards risks in read-only mode. Only then make the minimal
allowed-file change in the main task.
```

Keep all implementation in one worker unless each worker has an isolated
workspace.
