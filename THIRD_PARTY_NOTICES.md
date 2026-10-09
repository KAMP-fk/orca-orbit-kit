# Third-party components and external products

The Orca integration scripts and configuration in this repository are private
original sources. This repository contains no Orca product executable, Tailscale
client, Codex/Claude CLI, account credentials, downloaded skill collection,
development VM or container image.

Orbit and Tomato are source submodules pinned to full commit IDs. Their own
LICENSE and notices apply. Orbit builds complete installed-version notices into
`dist/oss/`; see `apps/orbit/THIRD_PARTY_NOTICES.md`. The generated inventory
includes development tools and is not a native-binary distribution SBOM.

External dependencies are installed from their official distribution channels:

| Product | Source license / scope | Official source |
| --- | --- | --- |
| Orca | Public repository MIT; retain target-version notices if copying its source | https://github.com/stablyai/orca |
| Tailscale | Public core BSD-3-Clause; official GUI and hosted service also have separate conditions | https://tailscale.com/opensource |
| Git / Bash / Python / Node / jq / pnpm | Separately installed system and development tools, not bundled here | See docs/package/DEPENDENCIES.md |
| Codex / Claude / GitHub / Linear | Separately installed clients or account services; authenticate independently | See docs/package/INSTALL.md |

Referencing an installed CLI is different from redistributing its implementation.
The optional CI Dockerfile is a recipe and does not redistribute an image here.
A future binary, VM or container release requires its own resolved dependency,
copyright, NOTICE and corresponding-source assessment. Root LICENSE applies only
to original material and does not replace third-party permissions.
