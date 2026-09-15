# Oduflow Client Addons for Odoo 19.0

Client addons for Odoo, maintained by Oduflow. Modules live in `addons/`; add this
directory to Odoo's `addons_path`. Deployment resources live in `deploy/`.

## Modules

- [Odubook](addons/odubook/README.md) — multilingual documentation, change history, document shelf and PDF export.
- [Oduscale](addons/oduscale/README.md) — employee VPN access through Headscale and Tailscale, device inventory and access revocation.

## Services

[Deployment resources](deploy/README.md) provide configuration for the services
used by Oduscale:

- **Headscale**: device registration, VPN addressing, DNS and access policy, with
  an internal API used by Odoo.
- **Tailscale gateway**: persistent VPN identity and TCP forwarding to Odoo.

See the [administrator guide](addons/oduscale/doc/admin_guide.md) for installation
and the [deployment journal](deploy/log/README.md) for specific environments and
recorded results.

- [OduPilot](addons/odupilot/README.md) — AI conversations, record questions, tool approvals and developer workspaces.
- [OduMCP](addons/odumcp/README.md) — MCP access policies, approvals, API authentication and audit.

Python dependencies for OduPilot are listed in `.oduflow/requirements.txt`.
Licenses are declared per module: OduPilot retains OPL-1; the other addons use LGPL-3.
