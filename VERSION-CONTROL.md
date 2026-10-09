# Local Git boundary (2026-10-03 JST)

The Owner asked to handle `HANDOFF-agents-git-20261002.md`. Adopt option (3):
version only the affected engineering sources, using two local repositories.

- `/Users/kamp/orca`: allow `agents/team` and shared offline `tests`.
  Root policy, directory guides, the completed handoff in `docs/history/`, and
  `tools/ci/` sources are tracked. Local operations evidence in `docs/operations/`
  and other top-level paths are denied by default. The old handoff root path is a
  repository-relative compatibility link. The legacy root CI script and Dockerfile
  are also repository-relative links, so existing invocations work in new checkouts.
- `/Users/kamp/orca/agents/team/roles/tomato/skill`: Tomato's separate source repository.
  Its `.git` and complete history were moved with the directory; the outer Orca
  repository excludes this nested repository. Persona/brain remains outside it.

The 2026-10-06 Owner instructions keep Tomato, Banana and Review as three roles.
Banana owns engineering intake, Codex implementation and consolidated infrastructure
maintenance. Review stays independent and uses an on-demand project checkout.
Shared helpers live in `agents/team/bin` and `lib`; role-specific sources live in
`roles/tomato`, `roles/banana` and `roles/potato`. Acceptance and relay sources now
belong to `roles/potato/acceptance` and `roles/potato/relay`; `roles/review` is the
compatibility link and `review` remains the durable role ID.
The old source locations are compatibility symlinks, excluded from new Git additions.
Installed commands, skills, profiles and the owned startup block use canonical paths.
Profile files do not replace the base Codex configuration. Historical/runtime content
and unconfigured external Devin adapters are preserved. The Owner's 2026-10-07 JST
policy excludes Devin from Orca workflows; preserved adapters are not an active
implementation or fallback path. See `AGENTS.md` and
`agents/team/references/banana-engineering.md` for the current policy.
See `agents/team/references/directory-layout.md` for the actual paths and migration.

This boundary lets the unified Banana role use its normal launcher from actual Git
repositories and makes edits reversible. No Git-check bypass or trust change is
needed. The wider Orca runtime, nested repositories/workspaces, CI-runner operation,
logs, packet/ledger/state trees, local verification artifacts, and backups are excluded.
No remote is configured or publication requested.

Before initialization, read every regular file under `agents`, `tests`, and Tomato
using a byte-stream scanner; do not follow symlinks. Detect private keys, GitHub and
provider tokens, AWS IDs, JWTs, credential URLs and long credential assignments.
Only metadata and hashes are recorded in the excluded local report
`reports/agents-git-secret-scan-20261003.json`; values are never emitted.
Each tracked candidate has a SHA256 snapshot. Validate any candidate findings and
the exact Git index before committing the baseline.

Pattern matching cannot prove absence of secrets. Unknown formats, compressed or
encrypted content and low-entropy values can evade it. Excluded unrelated nested
repos/workspaces and CI-runner files are not part of the content scan. Scan failures
or unresolved tracked candidate findings block a commit.

Runtime exclusions and credential patterns are explicit in `.gitignore`. An ignore
file does not override an existing tracked entry, so inspect the index on every
commit. Add a new source root intentionally; never use `git add -f` for runtime data.

The 2026-10-06 consolidation keeps three local roles (Tomato, Banana, Review).
Owned legacy Kiwi/Melon/Potato/Peach links are retired without deleting runtime history.
Banana remains separate from independent review. See agents/team/references/agent-consolidation.md.

## Private package boundary (2026-10-09)

The Owner authorized a private GitHub source package and a single editing entry.
This root is now the integration source. Orbit lives at apps/orbit, with the old
~/Projects/orbit-console path retained locally as a link to the same source.
Orbit and Tomato keep their own histories and active child worktrees as pinned
private submodules. The root's gitlinks identify component versions; dirty component
source appears in git status and git diff --submodule=diff. Commit and push the
component first, then record its SHA here. No automatic commits or pushes.

Packaging sources under scripts/, config/, docs/package/, the root LICENSE and
THIRD_PARTY_NOTICES are allowed. Runtime/default-deny boundaries remain in effect.
The earlier 'no remote / no publication requested' description is historical.
Local before/ bundles and snapshots are preserved in ~/Reports, outside Git.
