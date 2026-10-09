# Tailscale access

Install the official client independently and log in with the installer user's
account. Neither the client nor its auth/node keys are part of this package.
The current server listens only on `127.0.0.1`; preserve that boundary.

```dotenv
ORBIT_ORIGIN=https://your-mac.your-tailnet.ts.net
ORBIT_ALLOWED_USERS=you@example.com
```

Check the existing endpoint before selecting a free HTTPS port:

```sh
tailscale serve status --json
tailscale serve --bg --https=443 http://127.0.0.1:4310
```

Use the selected port in ORBIT_ORIGIN if it is not 443. Do not overwrite another
Serve endpoint. Configure tailnet access policy and Orbit's exact user allowlist.
Serve's user headers identify user-owned client devices; tagged **client** devices
do not provide those identity headers and are rejected by this auth model. A server
tag is a separate matter. Keep Funnel disabled for this application.
[Serve and identity headers](https://tailscale.com/docs/features/tailscale-serve)

The loopback proxy model trusts local processes on the server Mac. Host/Origin,
CSRF and allowlist checks remain in place; publishing the repository privately is
independent of runtime network access.

HTTPS certificate names are recorded in Certificate Transparency. Use a machine
name without private information. Certificates do not make the web app public.
[HTTPS certificates](https://tailscale.com/docs/how-to/set-up-https-certificates)

The public Tailscale core is BSD-3-Clause, but this is not a license to bundle the
whole official macOS product or resell the hosted service. Each installer uses
their own account and appropriate plan. The current Personal plan is for
non-commercial use; assess business use separately from repository visibility.
[Open-source scope](https://tailscale.com/opensource),
[Terms](https://tailscale.com/terms), [Plans](https://tailscale.com/pricing).
