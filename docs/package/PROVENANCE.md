# Source provenance

The integration entry uses the existing local Orca source history, first imported
for this package from full SHA `14921d30df31ec33fddeb6e17509f19d90f5586e`.
It includes the Owner-authorized working-copy source state captured on 2026-10-09,
plus packaging, notices, setup/check tooling and portability fixes. Pre-existing
uncommitted work was snapshotted locally before modifications and preserved.

Orbit's previous baseline was `838a7f85988aa18f3840833d2518d74df7a352e1` in
`KAMP-fk/orbit-console`. Tomato's baseline was
`41450c219fe327db03cf7352176cca46f2fd5305` in the local skill repository.
Their package versions are the full SHAs recorded as submodule gitlinks, not these
historical baselines. Their complete prior histories and existing child worktrees
remain intact. Source paths on this Mac point to these same active checkouts.

No upstream Orca/Tailscale implementation, downloaded skill collection, private
brain, live terminal history, runtime observation state or executable installer was
imported. Orbit dependency notices come from installed package versions and their
original LICENSE/NOTICE files; inventory includes notice and lockfile hashes.

Before initial push, inspect each exact Git index and HEAD history using
`scripts/scan-source.py`; inspect symlinks and intentional gitlinks. This pattern
check has limited coverage and does not certify that every possible secret format
or third-party origin has been detected. Future binary distributions require their
own complete dependency/provenance analysis.
