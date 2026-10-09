# Local engineering workspace

This repository tracks the Orca named-role sources in `agents/team/`, their offline
tests in `tests/`, and the version-control policy. The default-deny `.gitignore`
excludes other Orca projects and runtime material. Tomato's skill at
`agents/team/roles/tomato/skill` is a separate nested repository.

- Apply the current human user's instructions before older skill or repository guidance.
- The current roster is three roles — Tomato (consultation, Fable / medium), Banana
  (engineering lead, Codex implementation, infrastructure maintenance) and
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

The setup rationale is `VERSION-CONTROL.md`; `README.md` and `docs/README.md` are the
directory entry points. The completed 2026-10-02 handoff is kept in
`docs/history/HANDOFF-agents-git-20261002.md`; its old root path is a compatibility link.

## Codex implementation / Orca quality boundary

The Owner's 2026-10-07 JST policy is to use no Devin in Orca workflows. Use Banana's
Codex (Sol) path for development. Do not launch, resume, retry, or fall back to Devin
through local CLI, external Issue adapters, Linear Playbooks, or automations. Do not
apply Devin-triggering labels such as `!implement` or `!plan`. Preserve installed
Devin CLI/configuration and historical records; this policy does not authorize account
deletion or subscription changes. Read existing local receipts when needed to establish
ownership, and do not infer that an existing external session has stopped.

Use `agents/team/references/team-topology.md` and `agents/team/references/banana-engineering.md`
for the responsibility split. Tomato covers broad consultation and intent; Banana has its own
engineering domain. They exchange scoped requests, questions and reports rather than sharing a
permanent supervisory hierarchy. Banana owns engineering intake, scopes one development checkout,
uses Codex as its implementation engine, and hands the pinned result to an uninvolved Potato in
a separate checkout. Banana also owns the consolidated infrastructure maintenance. Orca owns
acceptance, CI/QA, independent review, correction requests, and completion after guarded merge.
Preserve project CI, review/signing and human gates. Empty adapter configuration must fail closed;
fixture receipts do not prove an external migration. Live automation/session/state changes are
distinct from source changes and must be verified before claiming activation.

## Private source package (2026-10-09)

The root is the private Orca/Orbit integration source, with pinned private source
submodules at apps/orbit and agents/team/roles/tomato/skill. Component source is
edited in those actual checkouts; do not maintain copy-based mirrors. Preserve
existing child worktrees and common Git directories. Commit/test/scan/push a
component before updating its parent gitlink. Do not automatically commit or push.
Run scripts/check and inspect each exact index plus the histories being published.
Private repository visibility does not permit credentials, private brain or runtime
state in source. Use docs/package for install, update, removal and provenance.
Do not change target projects' CI/verdict/trust/approval/sandbox settings while
packaging. No new subagents or self-approval; a test result is not a signed verdict.
