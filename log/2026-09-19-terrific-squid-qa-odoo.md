# 2026-09-19 — terrific-squid-qa — Odoo environment

## Context and Status

- Purpose and scope: verify the complete `terrific-squid` branch, including fresh installation and automated tests for `odulogin` and `odubook`, before merging its PR.
- Operation start/end (UTC): approximately 15:44–15:47 on 2026-09-19; exact end time was not captured.
- Operator and tool/MCP instance: Codex using the `odusfera` MCP instance.
- Oduflow instance/team: `oduflow.odusfera.pl`, team 1 (inferred from resource names; team display name unknown).
- Environment/database and service names/IDs: `terrific-squid-qa`; `oduflow_1_terrific-squid-qa`; Odoo container `oduflow-1-terrific-squid-qa-odoo`. Service ID unknown.
- Initial state and dependencies: a new, empty Odoo 19 environment was requested without a template or production copy; repository branch already existed on GitHub. No other environment was modified.
- Status: succeeded; environment retained for immediate user testing and PR verification.
- Provenance: executed and checked on 2026-09-19; this is not a historical import.

## Source and Images

- Repository URL, branch and deployed commit: `https://github.com/oduflow/oduflow-client-addons`, `terrific-squid`, `3298d31` (the published branch tip at creation).
- Odoo version/image: `odoo:19.0`; exact image digest and build revision unknown.
- Configuration paths and changes: repository requirements at `.oduflow/requirements.txt`; Oduflow runtime configuration at `/etc/odoo/odoo.conf`. No configuration was edited. Module manifests at `addons/odulogin/__manifest__.py` and `addons/odubook/__manifest__.py` in the deployed revision.

## Network and Persistence

- Public URL: `https://terrific-squid-qa.oduflow.odusfera.pl/web?debug=1`; Oduflow reported the HTTPS route, but external browser access and route restrictions were not independently tested.
- Internal container: `oduflow-1-terrific-squid-qa-odoo`; exact internal network names, backend ports, DNS and ACL policy unknown.
- VPN prefixes and tags: unknown; none were changed.
- Persistence: Oduflow-managed PostgreSQL and filestore; workspace `/srv/oduflow-data/team_1/workspaces/terrific-squid-qa`. Volume names, ownership, mount modes and backup scope unknown.
- Non-secret environment variables: none supplied to `create_environment`; Oduflow manages database connection settings.

## Credentials

- No password, token, cookie, secret variable or key was supplied, rotated or recorded. Initial Odoo administrator credential and its storage reference are unknown.
- If credentials are needed for manual testing, provision them through the environment's approved operator process; rotate or revoke them afterward. No credential issuance or expiry was verified.

## Backup and Rollback

- No backup or snapshot was made; the database was initialized from scratch with no production data.
- No rollback was performed. If an application error is discovered, correct the branch and apply an explicit module upgrade; delete or reprovision only after confirming that the retained test database is no longer needed.

## Operations

### 15:44 UTC — provision and install

- Executed: `create_environment(branch="terrific-squid", env_name="terrific-squid-qa", template_name="none", repo_url="https://github.com/oduflow/oduflow-client-addons", odoo_image="odoo:19.0", auto_install_modules="odulogin,odubook")`.
- Result: provisioning succeeded in 28.4 seconds. `odoo -i base` and `odoo -i odulogin,odubook` completed successfully. No job ID was returned.
- Warnings: non-fatal `charset_normalizer` package metadata and PATH warnings during dependency installation. No corrective action was needed for installation.

### Approximately 15:45–15:46 UTC — module tests

- Executed: `run_odoo_tests(env_name="terrific-squid-qa", modules="odubook", upgrade=true, summary_only=true)` and then the same call for `odulogin`.
- Result: `odubook` had 0 failed and 0 errors of 68 tests (`output_id=0a464b06`); `odulogin` had 0 failed and 0 errors of 8 tests (`output_id=1c78cfc8`). Both upgrade-based test commands completed successfully.

### Approximately 15:46 UTC — environment and translation inspection

- Executed: `get_environment_info(env_name="terrific-squid-qa")`; `translation_status` for each module with `langs="pl_PL,ru_RU"`.
- Result: Odoo and shared database were reported running. Both languages returned `NOT ACTIVATED` in this fresh database, so UI translation import was not verified. No language activation or module re-upgrade was performed.

## Verification

| Time (UTC) | Check / command | Expected | Observed | Evidence / output ID |
| --- | --- | --- | --- | --- |
| 2026-09-19 15:45 | Oduflow fresh install | base, `odulogin` and `odubook` install | all succeeded | `create_environment` response; no ID |
| Approximately 15:46 | `run_odoo_tests` for `odubook` | tests pass | 68 tests, 0 failed, 0 errors | `0a464b06` |
| Approximately 15:46 | `run_odoo_tests` for `odulogin` | tests pass | 8 tests, 0 failed, 0 errors | `1c78cfc8` |
| Approximately 15:46 | `get_environment_info` | Odoo running | all containers running | MCP response; no ID |
| Approximately 15:46 | `translation_status` | catalogue state known | Polish and Russian not activated; database import unverified | MCP responses; no IDs |
| Not run | Browser/UI acceptance and public-route ACLs | user-visible paths work | unverified; left for user testing | — |

## Final State and Follow-up

- At the last check, Odoo was running with both modules installed on the published branch. The environment remains for user testing; no cleanup or deletion was performed.
- No temporary devices, keys or files were created outside this Oduflow environment.
- Remaining limitations: UI translation loading, browser flows, external access restrictions and backup/restore were not tested; image digest and runtime volume details are unknown.
- Follow-up: user may test the HTTPS environment; repository maintainer should remove it only when the test URL and data are no longer needed.
- Related guides: `addons/odulogin/doc/admin_guide.md`, `addons/odubook/doc/admin_guide.md`, and their technical specifications. Related previous entry: [2026-09-18 megaflow test](2026-09-18-odulogin-test-odoo.md).
