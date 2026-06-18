---
name: zcode-delegation-eval
description: Evaluate whether ZCode or Claude Code GLM-5.2 should act as Codex's delegated coding worker for a specific task.
---

# ZCode Delegation Eval

Use this skill when comparing ZCode and Claude Code GLM-5.2 quality, quota
efficiency, and supervision cost across bounded coding tasks.

## Contract

- Codex remains planner and final auditor.
- Do not let ZCode and Claude Code both act as project owner for the same repo
  at the same time.
- Start with low-risk fixtures or throwaway branches.
- Record outcomes with `tools/zcode_eval/zcode_eval.py`.
- Treat ZCode GUI automation as experimental unless a stable control surface is
  available.

## Procedure

1. Run `python3 tools/zcode_eval/zcode_eval.py doctor`.
2. Choose one small, verifiable task and write the same acceptance criteria for
   both tools.
3. Run the Claude Code GLM worker with a bounded implementation packet.
4. Run ZCode in Plan, Auto Edit, or Goal mode with the same task.
5. For each run, record:
   - pass / fail / partial / blocked
   - manual interventions
   - `tokens_used` from before/after Usage Stats snapshots when visible
   - `quota_percent_used` from before/after Usage Stats snapshots when visible
   - files changed and line churn
   - validation command and result
   - notes about scope control, recovery, and auditability
   - GLM-5.2 effort, task class, and context strategy
   - risk budget and max changed files, when used
6. Summarize with `python3 tools/zcode_eval/zcode_eval.py summarize`.
   - Inspect recent raw entries with `python3 tools/zcode_eval/zcode_eval.py
     show-log`.
7. Recommend only after multiple task shapes: bug fix, test repair, small
   feature, frontend/browser task, and longer refactor.

## Adoption Rule

Prefer ZCode only if it reduces manual supervision or improves successful
completion without worse diff hygiene, hidden state, or review burden.

## GLM-5.2-Specific Comparison

Compare by task class:

- `small-fix`: speed and approval count
- `root-cause`: call-chain quality and regression checklist
- `architecture`: module map usefulness
- `production-gate`: standards adherence and unauthorized-change rate
- `long-horizon`: completion without drift across multiple iterations

Compare supervision cost by how often Codex had to widen scope, raise risk
budget, remove changed-file limits, or repair unsafe validation setup.
