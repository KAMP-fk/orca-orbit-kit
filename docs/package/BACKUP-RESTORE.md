# Back up source and private state separately

Source recovery: clone the integration repo recursively at its recorded commit.
This restores original source, templates and component SHAs. It does not restore
credentials, role memories, terminal sessions or workspaces.

Private state must be backed up through a separate encrypted path. Orbit defaults
to `~/.local/share/orbit-console`; its history/plans/catalog and action receipts must
not enter Git. Preserve source state and receipt identity when restoring the same
server; do not start two servers against one writable state directory. Stop the
relevant service deliberately before making a consistency-sensitive copy.

Preserve the brain vault separately under its own access policy. Never bundle
persona or private diary content with a source release. On another machine, log in
to Tailscale and the agent clients as a new device; do not copy their node keys or
authentication files. Verdict key handling follows the Owner's Keychain policy.

The 2026-10-09 migration's source snapshots and complete Git bundles are local at
`~/Reports/orca-orbit-packaging-2026-10-09/before/`. These are recovery evidence,
not part of the package. The active Orbit and Tomato histories stay in their source
repositories so existing child worktrees retain their Git common directory.
