# Local Git boundary (2026-10-03 JST)

The Owner asked to handle `HANDOFF-agents-git-20261002.md`. Adopt option (3):
version only the affected engineering sources, using two local repositories.

- `/Users/kamp/orca`: allow `agents/linear-inreview-reviewer`, `agents/review-relay`,
  `agents/named-team`, and their shared offline `tests`. Root policy and the handoff
  are tracked. Other top-level files/directories are denied by default.
- `/Users/kamp/.claude/skills/Tomato`: allow the skill source, selected bin commands,
  modules, references, and new offline tests. This is the real source directory;
  no copied source or symlink deployment is introduced.

This boundary lets Melon and Kiwi use their normal launchers from actual Git
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
