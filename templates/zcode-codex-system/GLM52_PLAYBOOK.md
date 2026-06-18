# GLM-5.2 Playbook For ZCode

Use this when ZCode is running GLM-5.2.

## Before You Use This Playbook

This is not the install guide. First set up the target repo with:

```bash
zcode-install-repo /ABSOLUTE/PATH/TO/YOUR/TARGET_REPO
```

Run that in Terminal. The current folder does not matter when the target repo
path is absolute. Replace the placeholder with the output of `pwd` from inside
the target repo.

Use this playbook after Codex has a real task, a small edit scope, and a
validation command.

## Defaults

- Use `Max` effort for long-horizon coding, root-cause analysis, architecture
  mapping, production-grade checks, mobile debugging, and multi-round `/goal`
  tasks.
- Use `High` effort for cheap probes, simple read-only reviews, and narrow
  repairs.
- Use 1M context to preserve architecture and decisions, not to copy every file
  into every prompt.
- Keep risk budget low by default; ask Codex to widen it only when the task
  genuinely needs broader changes.
- Respect `max_changed_files` when present so Codex can audit broad edits
  mechanically.

## Before Editing

For `root-cause`, `architecture`, `production-gate`, `mobile-debug`, or
`long-horizon` tasks, first produce:

- relevant module boundaries
- call chain or data flow
- interface contracts
- standards and prohibited operations
- minimal edit plan
- validation and regression checklist

Then implement only the smallest approved path.

## Context Discipline

Read:

- task packet
- repo rules
- relevant tests
- call chain files
- logs/config only when needed

Skip:

- secrets and `.env*`
- build outputs
- dependency folders
- unrelated generated artifacts
- entire repo dumps for one-file fixes

## Final Report

Return:

- task class and effort used
- changed files
- validation command and result
- whether any standards or boundaries were at risk
- whether risk budget or max changed files was close to being exceeded
- residual risk and recommended Codex decision
