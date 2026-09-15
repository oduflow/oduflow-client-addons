# Oduscale Services

This directory contains service configuration examples for Oduscale. Odoo runs
in an Oduflow environment; Headscale and the VPN gateway run as separate Oduflow
services with persistent volumes.

## Services and Configuration

| Service | Role | Files |
| --- | --- | --- |
| Headscale | Tailscale control server: registers devices, assigns VPN addresses, distributes DNS and access policy. Oduscale calls its internal API. | [config.yaml](headscale/config.yaml), [policy.hujson](headscale/policy.hujson) |
| Tailscale gateway | Joins the VPN as the Odoo gateway and forwards VPN TCP port 80 to the Odoo container on port 8069. | [serve.json](gateway/serve.json) |

The Headscale example uses SQLite with WAL and persistent state, MagicDNS, and
an access policy allowing members to reach port 80 on the gateway tagged
`tag:odoo`. The gateway stores its Tailscale identity in a persistent volume.
Odoo authentication is still required after connecting through the VPN.

These files contain values from the demo installation. Before reuse, adapt the
public control-server URL, VPN prefixes, DNS domain, gateway user/tag policy and
Odoo container address. Image versions, volume names and public routes belong in
the installation's journal entry; the configuration files alone do not create
services or provision credentials.

## Documentation

- [Oduscale administrator guide](../doc/admin_guide.md): deployment procedure, module setup, credentials, backups and operations.
- [Deployment journal](../../../log/README.md): concrete installations, updates and verification results.
- [Historical hr-headscale installation](../../../log/2026-09-14-hr-headscale-oduscale.md): recorded hosts, versions, commands and checks.

## Recording Work

Follow the [repository agent rules](../../../AGENTS.md#oduflow-deployment-journal).
Start each operation from the [journal template](../../../log/TEMPLATE.md), fill in actual
values and outcomes, and redact secrets before saving command output.
