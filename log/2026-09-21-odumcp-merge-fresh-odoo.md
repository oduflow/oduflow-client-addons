# 2026-09-21 — odumcp-merge-fresh — clean MCP installation

## Context and Source

Executed now through odusfera Oduflow MCP, team 1, to verify a fresh installation
of unified `odumcp` version `19.0.1.4.0`. Status: succeeded.
Repository: https://github.com/oduflow/oduflow-client-addons.git;
branch `merge/odumcp-platform`, tested commit `249a01c`.
Image: `odoo:19.0`, observed runtime `19.0-20260908`; digest unknown.

## Environment and Operations

- 17:25 UTC: `create_environment(env_name="odumcp-merge-fresh", branch="merge/odumcp-platform", repo_url="https://github.com/oduflow/oduflow-client-addons.git", odoo_image="odoo:19.0", template_name="none", auto_install_modules="odumcp")` completed successfully in 39.9 seconds. Base and MCP installed successfully.
- Database: `oduflow_1_odumcp-merge-fresh`; container:
  `oduflow-1-odumcp-merge-fresh-odoo`; workspace:
  `/srv/oduflow-data/team_1/workspaces/odumcp-merge-fresh`.
- Public URL: https://odumcp-merge-fresh.oduflow.odusfera.pl.
  Oduflow managed routing and storage; network and volume IDs were not inspected.
  No custom DNS, VPN, ACL, ports or environment secrets were configured.
- 17:26 UTC: `run_odoo_tests(env_name="odumcp-merge-fresh", modules="odumcp", summary_only=True)` passed all 107 tests, 0 failures and 0 errors; output `77d666ba`.
- 17:26 UTC: `delete_environment(env_name="odumcp-merge-fresh")` succeeded.

## Credentials, Backup and Final State

No production data or credentials were copied. Temporary test keys were generated
inside rolled-back test transactions. No backup or rollback was performed.
The disposable environment and its data were removed after verification.
No browser visual check or production rollout was performed.
The standalone server remained unchanged and passed 102 local tests; see
[upgrade verification](2026-09-21-odumcp-merge-odoo.md).
