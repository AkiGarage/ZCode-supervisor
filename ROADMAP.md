# Roadmap

## v0.0.2

Focus: prove the ZCode worker model on harder real-app tasks without increasing
human supervision.

Planned benchmark tracks:

- Public installer: open a clean public product repo at
  `AkiGarage/ZCode-supervisor`, keep the private development repo separate, and
  make `uvx --from zcode-supervisor zcode-install-repo <repo>` the primary
  setup path. Keep GitHub Release archives attested and checksumed for
  high-assurance users. Homebrew stays archived unless explicitly revived.
- Multi-file implementation: bounded feature or bug fix across several modules.
- Long-context navigation: task that requires reading architecture, tests, and
  cross-file call chains before editing.
- Parallel subagent workflow: use ZCode subagents for read-only mapping,
  root-cause analysis, standards review, and scoped implementation.
- Token and quota efficiency: use the Usage Stats snapshot workflow to record
  consumed tokens, consumed quota percent, elapsed time, approvals, changed
  files, tests, and repair loops.
- Safety audit: run packet, snapshot, audit, secret scan, changed-file limits,
  and independent Codex validation for every run.

Adoption rule:

- Prefer ZCode only when it improves completion quality or reduces human
  supervision without worse diff hygiene, hidden state, or review burden.
