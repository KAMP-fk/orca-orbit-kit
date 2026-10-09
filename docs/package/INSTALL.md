# Install, update and remove

The package entry is the private `KAMP-fk/orca-orbit-kit` repository. Orbit and
Tomato are private source submodules; the installer needs read access to all three.
Use the official GitHub login flow, then clone into `~/orca` on a new machine:

```sh
git clone --recurse-submodules https://github.com/KAMP-fk/orca-orbit-kit.git ~/orca
cd ~/orca
python3 scripts/doctor.py
scripts/setup
pnpm --dir apps/orbit check
```

Do not overwrite an existing `~/orca`. On the current Owner machine it is already
the source checkout. Existing workspaces, local histories and ignored runtime
directories are outside the package's tracked source boundary. A clean clone will
not recreate those private data directories or automatically register role homes.
Create/register the role workspace roots in Orca as needed; `agents/team/roles.json`
is the current roster. `config/host.env.example` documents per-machine/project
settings. Store actual settings outside Git and export them in the launching shell.
The supplied role and review workflows retain the current project's contracts.

Install and log in to Orca, Codex and the optional Claude client through their
official clients. Connect Linear through Orca. Respond to folder trust and login
screens yourself. Setup neither grants trust nor replaces the global agent config.
The role instruction paths use the conventional `~/orca` installation; legacy
profiles under role source directories are historical/project-specific references,
not permission to copy trust settings to another machine.

`scripts/setup --check` checks tools/source and existing owned links without
installing or starting anything. `scripts/setup` installs dependencies, installs
owned links and creates a mode-0600 Orbit `.env` only if none exists. It preserves
destination collisions and never overwrites an existing `.env`. It does not start
agents, enable shell autostart, install a service or modify Tailscale.

Set the Orbit `.env` using its example. New installs disable the private journal
and project-specific delivery reader. Set the exact HTTPS origin and allowed
Tailscale user logins before remote use. Keep actual `.env` out of Git.

```sh
pnpm --dir apps/orbit start
# After checking normal startup, install macOS login startup if desired:
pnpm --dir apps/orbit service:install
```

Follow [TAILSCALE.md](TAILSCALE.md) for tailnet HTTPS. The built app includes the
copyright/license texts at `/oss/index.html`, behind the same access checks.

## Edit and update

All edits happen in these actual source checkouts. There is no backup-copy sync.
The Owner's old `~/Projects/orbit-console` path is a local compatibility symlink to
`~/orca/apps/orbit`; new clones do not need that alias.

```sh
# Inspect all sources and submodule changes:
git status
git diff --submodule=diff
git -C apps/orbit status
git -C agents/team/roles/tomato/skill status
```

Inside a clean submodule clone, create an edit branch before committing; submodules
initially check out the recorded SHA in detached HEAD. Commit, test, scan and push
the component first, then commit its new SHA in the integration repository. Do not
automatically commit edits or recursively push active worktrees. Do not replace a
dirty checkout with `submodule update --force` or a reset.

For a clean checkout, update the integration branch with a fast-forward pull and
run `git submodule update --init --recursive`. This adopts recorded component SHAs;
it does not follow floating submodule branches. Run frozen-lockfile install and
the required checks. Before restarting Orbit, confirm there are no pending actions
in `/api/snapshot`; re-registering its service restarts the process.

## Remove

`scripts/uninstall` removes only the existing installer's owned links and owned
autostart block. It retains source, data, authentication and services.
Shell configuration managed by a symlink is preserved. If an owned autostart block
was moved behind that symlink, remove the block in your dotfiles manager before
uninstalling; the installer will not write through the link.
To explicitly
remove the Orbit LaunchAgent, use `pnpm --dir apps/orbit service:remove`. To stop a
Serve endpoint, inspect the current Serve configuration and disable only that
endpoint. Never reset an entire tailnet or delete role workspaces as an uninstall
shortcut. See [BACKUP-RESTORE.md](BACKUP-RESTORE.md).
