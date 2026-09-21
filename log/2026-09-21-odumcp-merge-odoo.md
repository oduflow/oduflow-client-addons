# 2026-09-21 — odumcp-merge — unified MCP verification

## Context and Status

Executed now through the odusfera Oduflow MCP, team 1. Scope: merge platform
`odumcp` from platform commit `979f5b0` into client-addons Odoo 19 base `8a01240`.
Status: in progress. Production environments are outside this deployment.

## Source and Images

Repository: https://github.com/oduflow/oduflow-client-addons.git.
Branch: `merge/odumcp-platform`. Image: `odoo:19.0` (digest unknown).
Environment: `odumcp-merge`; database: `oduflow_1_odumcp-merge`.
Container: `oduflow-1-odumcp-merge-odoo`.
URL: https://odumcp-merge.oduflow.odusfera.pl.
Workspace: `/srv/oduflow-data/team_1/workspaces/odumcp-merge`.
Odoo HTTP routing and persistent storage were provisioned by Oduflow; internal
network and volume IDs were not inspected. No custom DNS, VPN, ACL, port or
secret configuration was applied. `.oduflow/requirements.txt` was installed.

## Credentials, Backup and Rollback

No production credentials or data were copied. Tests generate temporary keys in
rolled-back test transactions. No backup or rollback was performed; this is a
fresh disposable environment. Module data is retained during upgrade checks.

## Operations

- 17:17 UTC: `create_environment(env_name="odumcp-merge", branch="merge/odumcp-platform", repo_url="https://github.com/oduflow/oduflow-client-addons.git", odoo_image="odoo:19.0", template_name="none", auto_install_modules="odumcp")`. Fresh installation of client base `8a01240` succeeded.
- 17:23 UTC: `pull_and_apply(env_name="odumcp-merge", upgrade="odumcp", summary_only=True)` upgraded to `9d2767c`; exit 0, output `afcbd9fc`.
- 17:23 UTC: `run_odoo_tests(env_name="odumcp-merge", modules="odumcp", summary_only=True)` ran 107 tests: 1 failure, 0 errors, output `813dfec6`. The inherited expiry fixture used wall-clock time while SQL validates against transaction time; adjusted the fixture relative to PostgreSQL transaction time.
- Local standalone server tests: `pytest --cov=odumcp_server --cov-report=term-missing`: 102 passed, 95.19% coverage. Server source and deployment resources unchanged.

## Final State and Follow-up

Verification continues; final result and environment cleanup will be appended.
