# Local engineering workspace

This repository tracks only the named-agent and review infrastructure sources in
`agents/`, their offline tests in `tests/`, and the version-control policy.
The default-deny `.gitignore` excludes other Orca projects and runtime material.

- Apply the current human user's instructions before older skill or repository guidance.
- Preserve other roles' changes. Melon owns review evidence implementation and its tests;
  Kiwi owns Tomato observation implementation in its separate repository.
- Do not modify live packet/ledger/log/state files, tokens, keys, persona/brain material,
  or Codex trust/approval/sandbox settings as part of an ordinary code change.
- Do not use Git-check bypasses or unsafe launch flags to start named agents.
- For the 2026-10-02 handoff, do not post externally, update Linear, operate PRs, or
  start/stop the CI supervisor or edit its LaunchAgent.
- Test using isolated fixtures and temporary state; do not spend model calls to test
  the review backend. Report actual commands, exit codes, scope, and limitations.
- An implementation test result is not an independent review PASS. Do not self-approve
  or start additional subagents. Final concafe verdicts require the separate task,
  effective model/effort, and independence required by the current Owner instructions.
- Re-scan the exact index before committing. Never force-add ignored runtime or
  secret files. Symlinks must be inspected and must not import machine-local configs.

The authoritative setup rationale is `VERSION-CONTROL.md`. The concrete work request
is `HANDOFF-agents-git-20261002.md`.
