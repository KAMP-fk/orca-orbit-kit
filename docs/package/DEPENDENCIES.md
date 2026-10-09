# Dependencies and support scope

This is a source/configuration package for the existing macOS local Orca workflow.
It does not claim tested Linux/Windows role installation or a self-contained server.

| Dependency | Verified on the migration machine | Role |
| --- | --- | --- |
| Node | 22.22.2; Orbit requires >=22.9 | Server, build |
| pnpm | 10.33.0, recorded in Orbit packageManager | Frozen lockfile install |
| Python | 3.14.8; use >=3.11 | Source tooling and offline tests |
| Git, Bash, jq, zsh | System/Homebrew tools | Source, observation and shell integration |
| Orca CLI | 1.4.222 | Documented worktree/terminal/Linear/automation APIs |
| Tailscale | 1.102.4 | Optional tailnet HTTPS using Serve |
| Codex / Claude | Independently installed and authenticated | Existing role implementations |
| gh | Independently authenticated | Read-only project GitHub observations; private source access |

Orca capability checks: worktree ps, terminal list/read/send, linear list-issues,
linear issue/team states, automations list/runs. Use the guide shipped with the
selected Orca executable; do not invent RPCs or silently select a different build.
Tailscale requires HTTPS-enabled tailnet for Serve.

Install from official channels: [Orca](https://github.com/stablyai/orca),
[Node](https://nodejs.org/), [pnpm](https://pnpm.io/installation),
[Python](https://www.python.org/), [Git](https://git-scm.com/),
[jq](https://jqlang.org/), [GitHub CLI](https://cli.github.com/),
[Tailscale](https://tailscale.com/download).

The current roster, concafe project contracts and legacy review adapters are
project-specific. Changing a configured repository does not make those contracts
generic or transfer authority. Empty implementation/quality adapters remain closed;
the source package must not launch Devin or create trigger labels.
