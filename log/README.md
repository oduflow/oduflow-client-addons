# Deployment Journal

Concrete Oduflow service operations are recorded here in English. General service
descriptions are in the [module deployment overviews](../README.md#services); reusable Oduscale
instructions are in the [administrator guide](../addons/oduscale/doc/admin_guide.md).

Use `YYYY-MM-DD-<environment>-<service-or-stack>.md` with the UTC operation date.
Append timestamped operations for the same scope and day; create a new entry for
another day. Preserve prior observations and label retrospective imports clearly.
Copy the [template](TEMPLATE.md), follow the [agent rules](../AGENTS.md#oduflow-deployment-journal)
and add an index row. Record unknown or inapplicable details explicitly.

| Date (UTC) | Environment | Scope | Result / provenance |
| --- | --- | --- | --- |
| 2026-09-19 | terrific-squid-qa | [Odoo 19 PR verification](2026-09-19-terrific-squid-qa-odoo.md) | Fresh installation and 76 module tests passed; environment retained for user testing. |
| 2026-09-18 | odulogin-test | [Odoo 19 test environment](2026-09-18-odulogin-test-odoo.md) | Fresh installation and 8 module tests passed; retrospective entry imported on 2026-09-19. |
| 2026-09-15 | hr-headscale | [Environment removal](2026-09-15-hr-headscale-environment.md) | Teardown succeeded and absence verified; separate VPN services retained. |
| 2026-09-15 | hr-headscale | [OduMCP installation](2026-09-15-hr-headscale-odumcp.md) | Installed and verified; 327 tests passed; predecessor absent before rename. |
| 2026-09-14 | hr-headscale | [Oduscale, Headscale and VPN gateway](2026-09-14-hr-headscale-oduscale.md) | Historical installation reported successful; imported from the deployment README on 2026-09-15. |

Journal entries describe observations at their recorded dates, not guaranteed
current state. Secret values must never be included.

- [2026-09-19: Odoo 18 installation](2026-09-19-client-addons-18-install.md) — installed; 265 tests passed; temporary environment removed.

- [2026-09-20 — client addon branch regression](2026-09-20-client-addons-regression-odoo.md)

- [2026-09-21 — unified MCP verification](2026-09-21-odumcp-merge-odoo.md)
- [2026-09-21 — unified MCP clean installation](2026-09-21-odumcp-merge-fresh-odoo.md)
