# Changelog

## Unreleased

- Add ZCode Usage Stats snapshots for token and quota percent logging.
- Add `tokens_before`, `tokens_after`, `tokens_used`,
  `quota_percent_before`, `quota_percent_after`, and `quota_percent_used` to
  evaluation records and summaries.
- Add `zcode_eval show-log` for later ledger inspection.
- Add `zcodectl open-usage` and `zcodectl usage` helpers for collecting visible
  ZCode Settings usage values.
- Add bundled ZCode CLI discovery and headless control commands:
  `cli-path`, `cli-preflight`, `cli-doctor`, `cli-version`, `cli-prompt`, and
  `run-packet`.
- Add official ZCode release monitoring against the checked compatibility
  baseline and a scheduled GitHub Actions workflow that opens an update Issue
  when ZCode moves.
- Update the ZCode compatibility baseline to `3.1.2`, refresh release-monitor
  tests, and align docs with the latest ZCode Agent, Skill, Usage Stats, MCP,
  and subagent documentation.
- Add Homebrew release preparation: formula template, formula updater,
  release-artifact workflow with GitHub artifact attestations, release-prep CI,
  and release documentation.
- Add local temporary-tap Homebrew install validation guidance for the planned
  public tap path.
- Switch the active distribution plan to `uvx` / PyPI first, with TestPyPI/PyPI
  Trusted Publishing workflows and GitHub Release verified installer artifacts.
- Archive Homebrew as optional historical packaging instead of the primary
  setup path.
- Document the publication model: public product repo
  `AkiGarage/ZCode-supervisor`, private internal development repo, and
  Formula-only tap repo `AkiGarage/homebrew-zcode-supervisor`.

## v0.0.1 - 2026-06-17

- Add `zcode_supervisor` packet, snapshot, and audit commands.
- Add GLM-5.2 task class, effort, and context policy fields to task packets.
- Add low-babysitting guardrails for Full Access, destructive validation
  commands, risk budget, and changed-file limits.
- Add `zcodectl` helper for ZCode desktop/CDP control.
- Add workspace-local ZCode templates and subagent definitions.
- Add GLM-5.2/ZCode operator guide and specialized long-context subagents.
- Add benchmark fixtures and strict supervisor tests.
- Add public repository metadata and release checks.
