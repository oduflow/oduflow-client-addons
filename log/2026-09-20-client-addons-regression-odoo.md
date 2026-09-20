# 2026-09-20 — client addons regression — Odoo

## Context and Status
- Purpose: verify the merged 19.0 branch and updated 18.0, 17.0, 16.0 ports, including odulogin, audit reports and managed MCP credentials.
- Start (UTC): 2026-09-20T22:50:54.093857+00:00; operator: repository agent via Odusfera MCP.
- Instance/team: Odusfera; exact team ID unknown. Disposable environments client-sync-19, client-sync-18, client-sync-17, client-sync-16.
- Initial state: no test environments created for this operation; existing unrelated services untouched.
- Status: in progress. Observations below are executed now unless marked planned.

## Source and Images
- Repository: https://github.com/oduflow/oduflow-client-addons; corresponding version branches.
- Images: odoo:19.0, odoo:18.0, odoo:17.0, odoo:16.0; digests unknown.
- Configuration: repository manifests; no custom environment variables or extra repositories.

## Network and Persistence
- Provisioner-managed database, containers, networks and volumes; IDs, names, ownership and mounts unknown until reported.
- Internal Odoo HTTP port: 8069. Public URLs recorded with provisioning results.
- VPN/DNS/ACL settings inherited from the development platform; no changes requested.

## Credentials
- Provisioner-managed temporary development credentials: <redacted>; values not recorded.
- Test-generated API keys remain inside disposable test databases and transaction rollbacks.

## Backup and Rollback
- No backups or production changes. Rollback is deletion of only the disposable environments created here; branch history retains previous versions.

## Operations
- Planned: create_environment with branch matching image major, repo_url above, template_name="none"; install all five modules using pull_and_apply; run_odoo_tests; delete environments.

## Verification
- Pending installation and module test results. Browser UI verification not performed.

## Final State and Follow-up
- In progress; cleanup and deployed commit IDs will be appended below.

### 22:50–22:53 UTC — initial provisioning and installation
- Executed `mcp__odusfera__create_environment` twice: `{"env_name":"client-sync-19","branch":"19.0","repo_url":"https://github.com/oduflow/oduflow-client-addons","odoo_image":"odoo:19.0","template_name":"none"}` and the same with 18 replacing 19. Both base initializations succeeded; development guides loaded immediately.
- Team ID 1. Containers `oduflow-1-client-sync-{19,18}-odoo`; databases `oduflow_1_client-sync-{19,18}`; workspaces `/srv/oduflow-data/team_1/workspaces/client-sync-{19,18}`.
- URLs `https://client-sync-19.oduflow.odusfera.pl` and `https://client-sync-18.oduflow.odusfera.pl`.
- Executed `mcp__odusfera__pull_and_apply(env_name="client-sync-18", install="odubook,odumcp,odupilot,oduscale,odulogin", summary_only=true)` at commit ab11262. Failed exit 255, output `4769350f`: OduLogin window action used Odoo 19 field `group_ids`. Read tail through read_output. Corrected to native `groups_id` in all ports (18: a65b16e; 17: 717e1ef; 16: e892697), committed and pushed.
- Executed the same installation for client-sync-19 at 8b1eb76: exit 0, output `0e953d60`.
- Started `run_odoo_tests(env_name="client-sync-19", modules="odubook,odumcp,odupilot,oduscale,odulogin", summary_only=true)` and retried the explicit installation for client-sync-18 at a65b16e.

### 22:53–22:58 UTC — tests and fixture corrections
- 19.0 full suite at 8b1eb76: 282 tests, 0 failures, 1 error (`2536a8c3`). Error in OduLogin's fake request lacking cookies when installed together with mail. Fixed test fixture, committed/pushed 2e2cde4 and executed pull_and_apply with restart=true (success).
- Targeted rerun: `run_odoo_tests(env_name="client-sync-19", modules="odulogin", test_tags="/odulogin:TestOduLogin.test_session_info_exposes_only_needed_state", upgrade=false, summary_only=true)`: 1 test, zero failures/errors, `7b442710`.
- Installation retry on 18.0 a65b16e succeeded, exit 0, `2dc45ebf`. Pulled cookie fixture 3931dbf with restart=true. Full suite: 282 tests, 1 failure and 1 error, `f4cb2471`. Both in OduLogin tests: hostless test cookie retained old session after rotation; fake request lacked database/registry. Inspected native HttpCase, session rotation and session_info through read-only run_odoo_command. Fixed cookie scoping to actual HTTP host and provided database/registry on fake request. No runtime session logic changed.
- Corrections committed and pushed: 18 e9f97db, 17 a2c8b3d, 16 66dfd7e. Explicit pull_and_apply(restart=true) succeeded for 18/17.
- Targeted rerun on 18: `run_odoo_tests(env_name="client-sync-18",modules="odulogin",test_tags="/odulogin",upgrade=false,summary_only=true)`: 8 tests, zero failures/errors, `a5018847`.
- Read-only ORM inspection on 19 and 18: `run_odoo_shell(auto_commit=false, python_code="print(self.env['ir.module.module'].search([('name','in',['odubook','odumcp','odupilot','oduscale','odulogin'])]).read(['name','state','installed_version']))")`. All five installed; odumcp versions 19/18.0.1.1.0, other modules 19/18.0.1.0.0.
- Executed delete_environment for client-sync-19 and client-sync-18 after their checks; both torn down.
- Created client-sync-17 using the same create_environment arguments with 17; base initialization successful. URL/container/database/workspace follow the same pattern above. Loaded guide 17. Installed all five modules at c34bc2a successfully, exit 0, `30e608e5`.
- Full 17 suite: 282 tests, same 1 failure/1 error in older fixtures, `29b97c98`. Targeted OduLogin rerun after a2c8b3d: 8 tests, zero failures/errors, `0f43f54a` (same arguments as 18 with env_name client-sync-17).
- Created client-sync-16 with corresponding 16 branch/image and template none; base initialization succeeded. URL/container/database/workspace follow the same pattern above. Loaded guide 16. Installation and tests pending.
- Image runtime versions observed: 19.0-20260908 and 18.0-20260908. Test logs include missing demo filestore attachment warnings from fresh provisioned databases; these did not prevent test execution. No production data involved.

### 22:59–23:01 UTC — Odoo 16 verification and cleanup
- Executed pull_and_apply(env_name="client-sync-16", install="odubook,odumcp,odupilot,oduscale,odulogin", summary_only=true) at 66dfd7e: exit 0, output `4e0917aa`.
- Executed run_odoo_tests(env_name="client-sync-16", modules="odubook,odumcp,odupilot,oduscale,odulogin", summary_only=true): **282 tests, 0 failures, 0 errors**, output `ad05e8c1`.
- Read-only ORM inspection (same module query above) confirmed all five modules installed on both 17 and 16. OduMCP version 17/16.0.1.1.0; remaining module versions 17/16.0.1.0.0. Runtime versions 17.0-20260908 and 16.0-20250909.
- Internal login health on 16: run_odoo_command(env_name="client-sync-16", command="python3 -c 'import urllib.request; r=urllib.request.urlopen(\"http://127.0.0.1:8069/web/login\"); print(\"login_http_status\", r.status)'"): exit 0, HTTP 200.
- Executed delete_environment(env_name="client-sync-17") and delete_environment(env_name="client-sync-16"): both torn down. All four temporary environments from this operation are removed.

## Final verification results

| Branch | Final tested code | Installation | Full suite | Corrected targeted rerun |
| --- | --- | --- | --- | --- |
| 19.0 | 2e2cde4 | All five installed | 282 tests, one fixture error before correction | 1 test passed, 7b442710 |
| 18.0 | e9f97db | All five installed | 282 tests, two fixture issues before correction | All 8 OduLogin tests passed, a5018847 |
| 17.0 | a2c8b3d | All five installed | 282 tests, two fixture issues before correction | All 8 OduLogin tests passed, 0f43f54a |
| 16.0 | 66dfd7e | All five installed | 282 tests passed, ad05e8c1 | Not needed |

- Final result: all collected test cases passed, combining full runs and targeted reruns where only test fixtures changed. Full suites were not unnecessarily repeated after fixture-only fixes.
- HTTP test coverage includes authenticated routes, audit authorization/PDF restrictions, and user switching across requests. Browser UI and public routing/VPN end-to-end checks were not run; no claim of browser validation.
- Documentation finalized in English, Polish and Russian after code checks; marker/structure checks and git diff whitespace checks passed.
- Status: succeeded. Operation ended 2026-09-20 23:01 UTC. No remaining disposable services, production mutations, custom keys or backups. Git contains all code and documentation; subsequent commits contain documentation/journal only.
- Follow-up: optional browser validation by maintainers before production adoption; fresh install verified, existing database downgrade not supported.
