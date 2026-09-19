# 2026-09-18 — odulogin-test — Odoo environment

## Context and Status

- Purpose and scope: create an isolated Odoo 19 database from scratch to verify `odulogin` installation and tests, then leave it available for manual testing.
- Operation start/end (UTC): approximately 07:12–07:14 on 2026-09-18; exact end time was not captured.
- Operator and tool/MCP instance: Codex using `megaflow_velesagro` MCP and local Git.
- Oduflow instance/team: `megaflow.velesagro.pl`, team 1 (inferred from returned database/container names; team display name unknown).
- Environment/database and service names/IDs: `odulogin-test`; `oduflow_1_odulogin-test`; Odoo container `oduflow-1-odulogin-test-odoo`. Service ID unknown.
- Initial state and dependencies: environment did not exist in the returned environment list; Odoo 19 image and repository branch required. No template or production data was used.
- Status: succeeded on 2026-09-18; later availability is not implied.
- Provenance: retrospective entry written 2026-09-19 from the 2026-09-18 MCP responses in the previous Codex turn. No checks in this entry were rerun during import.

## Source and Images

- Repository URL, branch and deployed commit: `https://github.com/oduflow/oduflow-client-addons`, `terrific-squid`, `4868237d2751cd3d60748a888cc3be853807065e`.
- Odoo version/image: `odoo:19.0`; runtime reported Odoo `19.0-20260908`.
- Image digest: unknown; no auxiliary service image was added.
- Configuration: source checkout mounted by Oduflow at `/mnt/extra-addons`; Oduflow configuration at `/etc/odoo/odoo.conf`. No configuration file was edited during this operation. Module contract: `addons/odulogin/__manifest__.py` at the deployed commit.

## Network and Persistence

- Public URL: `http://odulogin-test.megaflow.velesagro.pl/web?debug=1`; TLS was not reported. Public route policy and published host ports were not independently verified.
- Internal container: `oduflow-1-odulogin-test-odoo`; PostgreSQL host shown by the test runner as `oduflow-db`. Internal network and running service ports unknown; test runner briefly listened on port 8089.
- VPN prefixes, DNS and ACL policy: unknown. No VPN or ACL change was made.
- Volumes, mounts, ownership and persistence: Oduflow-managed database and filestore; workspace `/srv/oduflow/data/team_1/workspaces/odulogin-test`. Volume names, ownership and backup scope unknown.
- Non-secret environment variables and runtime options: none supplied to `create_environment`; Oduflow's database connection variables are managed by the service and were not recorded.

## Credentials

- The `admin` password was reset in this disposable database with `reset_admin_password(new_password=<redacted>)`; storage reference, issue and expiry times unknown. The manual target user `odulogin_target` was created with a password supplied to Odoo as `<redacted>`.
- No token, session cookie, password or private key is recorded here. To replace the administrator credential, call `reset_admin_password` for this environment with a newly chosen value and share it through an approved secret channel. Revoke access by rotating credentials or deleting the disposable environment after manual testing.

## Backup and Rollback

- No backup or snapshot was created; this was a fresh disposable database with no production copy.
- No rollback was performed. Recovery would require correcting the module and reapplying it, or reprovisioning a new empty test environment after confirming that the current test data is no longer needed.

## Operations

### 07:12 UTC — publish module revision and provision the test environment

- Precondition: `terrific-squid` had no Oduflow environment. The module source was committed with author and committer `Max <litnimax@users.noreply.github.com>` and pushed as commit `4868237`.
- Executed: `create_environment(branch="terrific-squid", env_name="odulogin-test", template_name="none", repo_url="https://github.com/oduflow/oduflow-client-addons", odoo_image="odoo:19.0", auto_install_modules="odulogin")`.
- Result: Oduflow reported provisioning success in 55.5 seconds; `odoo -i base` and `odoo -i odulogin` completed successfully. No job ID was returned.
- Failure/correction: none. Package installation emitted non-fatal `charset_normalizer` metadata and PATH warnings.

### 07:13 UTC — run module tests

- Executed: `run_odoo_tests(env_name="odulogin-test", modules="odulogin", upgrade=true, summary_only=false)`.
- Result: `8` post-install test methods, `0 failed`, `0 errors`; `12` assertions were reported by the module stats. Output ID `b293b915`.
- Observation: asset generation logged a missing generated attachment and regenerated its bundle. No test failure resulted. This warning was not separately investigated.

### Approximately 07:14 UTC — prepare manual test account

- Executed: `reset_admin_password(env_name="odulogin-test", new_password=<redacted>)`; `odoo_create(env_name="odulogin-test", model="res.users", values={"name":"OduLogin Manual Target","login":"odulogin_target","password":<redacted>,"group_ids":[[6,0,[1]]]})`.
- Result: password reset succeeded; internal user ID `12` created. Subsequent `odoo_search_read` showed `odulogin` installed at `19.0.1.0.0` and target user active, non-share. `get_environment_info` showed Odoo running.

## Verification

| Time (UTC) | Check / command | Expected | Observed | Evidence / output ID |
| --- | --- | --- | --- | --- |
| 2026-09-18 07:12 | `create_environment` auto-install | fresh base and `odulogin` install | both commands succeeded | MCP setup response; no ID |
| 2026-09-18 07:13 | `run_odoo_tests` | module tests pass | 8 methods, 0 failed, 0 errors | `b293b915` |
| Approximately 07:14 | `odoo_search_read` on `ir.module.module` and `res.users` | installed module and active internal target | `odulogin` installed; user ID 12 active and non-share | MCP responses; no IDs |
| Not run | Browser/manual switch and return | user-visible flow works | unverified by Codex; handed to user | — |
| Not run | Public-route restrictions, backup/restore, VPN access | policy and recovery verified | unverified and not part of this test | — |

## Final State and Follow-up

- At the final 2026-09-18 check, Odoo was running at commit `4868237`; the environment was intentionally left for the user's manual test.
- No temporary device, key or file was created outside Oduflow's environment. The test user and database were intentionally retained.
- Remaining limitations: browser flow, current availability, TLS/ACL policy and backup were not verified. An asset-regeneration warning remains unexplained.
- Follow-up: user to test the switch/return UI; repository maintainers to remove the disposable environment only after testing is complete. No deletion was authorized or performed.
- Related guide: `addons/odulogin/doc/admin_guide.md` and `addons/odulogin/doc/tech_spec.md`.
