# Local engineering workspace

This repository tracks the Orca named-role sources in `agents/team/`, their offline
tests in `tests/`, and the version-control policy. The default-deny `.gitignore`
excludes other Orca projects and runtime material. Tomato's skill at
`agents/team/roles/tomato/skill` is a separate nested repository.

- Apply the current human user's instructions before older skill or repository guidance.
- The current roster is three roles — Tomato (consultation, Fable / medium), Banana
  (engineering lead, Devin implementation, infrastructure maintenance) and
  Potato (independent review, Opus 5.5 / high, read-only). `agents/team/roles.json`
  is the source of truth; see `agents/team/README.md` and `references/team-topology.md`.
- Preserve other roles' changes. Banana owns engineering, observation and review
  infrastructure; Tomato observation lives in its nested repository.
- Do not modify live packet/ledger/log/state files, tokens, keys, persona/brain material,
  or Codex trust/approval/sandbox settings as part of an ordinary code change.
- Do not use Git-check bypasses or unsafe launch flags to start named agents.
- Test using isolated fixtures and temporary state; do not spend model calls to test
  the review backend. `agents/team/bin/check` runs syntax checks and both test suites.
  Report actual commands, exit codes, scope, and limitations.
- An implementation test result is not an independent review PASS. Do not self-approve
  or start additional subagents. Final concafe verdicts require the separate task,
  effective model/effort, and independence required by the current Owner instructions.
- Re-scan the exact index before committing. Never force-add ignored runtime or
  secret files. Symlinks must be inspected and must not import machine-local configs.

The setup rationale is `VERSION-CONTROL.md`. The 2026-10-02 handoff that created this
repository is kept as `HANDOFF-agents-git-20261002.md` for history; it is complete.

## Devin implementation / Orca quality boundary

Use `agents/team/references/team-topology.md` and `agents/team/references/banana-engineering.md`
for the responsibility split. Tomato covers broad consultation and intent; Banana has its own
engineering domain. They exchange scoped requests, questions and reports rather than sharing a
permanent supervisory hierarchy. Banana owns engineering intake, scopes one development checkout,
embeds Devin as its implementation engine, and hands the pinned result to an uninvolved Potato in
a separate checkout. Banana also owns the consolidated infrastructure maintenance. Orca owns
acceptance, CI/QA, independent review, correction requests, and completion after guarded merge.
Preserve project CI, review/signing and human gates. Empty adapter configuration must fail closed;
fixture receipts do not prove an external migration. Live automation/session/state changes are
distinct from source changes and must be verified before claiming activation.
