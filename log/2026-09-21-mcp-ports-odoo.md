# 2026-09-21 — MCP ports — installation and upgrade checks

## Context and Status
- Started 22:09 UTC; operator: repository agent via Odusfera MCP, team ID pending.
- Scope: port 19.0 through 57ea7ec to 18.0/17.0/16.0; verify fresh installations and upgrades.
- Status: in progress. Entries below record this operation; imported 19.0 journals describe earlier checks, not checks repeated here.
- Initial production state: untouched. Only new disposable environments are used.

## Source and Images
- Repository: https://github.com/oduflow/oduflow-client-addons.
- Branches/images: 18.0 / odoo:18.0, 17.0 / odoo:17.0, 16.0 / odoo:16.0. Digests unknown.
- Old branch heads: b499bd1, be392ed, 99cf545. MCP upgrades from each major's 1.1.0 to 1.4.0.
- Dependencies: .oduflow/requirements.txt; all five client addons installed for integration checks.

## Network and Persistence
- Provisioner-managed database, volumes, network, TLS and routing; exact resource names recorded when returned.
- No custom DNS/VPN/ACL/ports or environment variables. Internal Odoo HTTP port 8069.
- Volume ownership and image digests not inspected.

## Credentials
- Platform-generated environment credentials remain managed by Odusfera, values <redacted>.
- Test keys exist only in disposable databases/rolled-back test transactions; no production credentials used.

## Backup and Rollback
- No backup performed for disposable environments. Rollback: delete only test environments created here; previous code remains in Git.

## Operations
- 22:09 UTC: started create_environment(env_name="mcp-port-18", branch="18.0", repo_url="https://github.com/oduflow/oduflow-client-addons", odoo_image="odoo:18.0", template_name="none", auto_install_modules="odubook,odumcp,odupilot,oduscale,odulogin") at old branch head, before pushing the port. Result pending.

## Verification
- Pending installation, upgrade, module tests and state inspection. Browser UI/public route/VPN checks not planned.

## Final State and Follow-up
- In progress; remove disposable environments when complete.

### 22:10–22:13 UTC — Odoo 18 and 17 upgrade
- mcp-port-18 provisioning succeeded, including installation of all five old modules. Created mcp-port-17 with identical arguments replacing 18 with 17; also succeeded. Development guides loaded after each creation.
- Team 1. For each environment E: URL https://E.oduflow.odusfera.pl; database oduflow_1_E; container oduflow-1-E-odoo; workspace /srv/oduflow-data/team_1/workspaces/E.
- Executed run_odoo_shell(env_name=E, auto_commit=true) with the following code on both old installations:

```python
profile = self.env['odumcp.profile'].create({'name':'Upgrade preservation fixture','code':'upgrade_preservation','default_model_access':'read','rate_limit_per_minute':37})
self.env['ir.config_parameter'].sudo().set_param('odumcp.port_upgrade_profile_id', str(profile.id))
print({'fixture_profile_id': profile.id, 'version': self.env['ir.module.module'].search([('name','=','odumcp')]).installed_version})
```

- Both fixtures had ID 1; old MCP versions 18.0.1.1.0 and 17.0.1.1.0. This committed data is disposable and will be deleted with its environment.
- Port commits: 18.0 1b46527, 17.0 5ff3168, 16.0 58421ca. Published 18/17; 16 publication deferred until old-version test environment is provisioned.
- Executed pull_and_apply(env_name="mcp-port-18", upgrade="odumcp", summary_only=true): exit 0, f6b2a454. Same on mcp-port-17: exit 0, 7780471c.
- Started run_odoo_tests on both environments with modules="odubook,odumcp,odupilot,oduscale,odulogin", summary_only=true; results pending.

### 22:13–22:17 UTC — framework compatibility and upgrade verification
- Full five-module tests: 17 returned 304 tests, 1 failure/0 errors (0fac73a8); 18 returned 304 tests, 1 failure/0 errors (83c17413). Both rejected the missing framework name formatted_read_group as not found (404) instead of policy denied (403).
- Read output failures with read_output(mode="grep",grep="FAIL:") and line context. Reserved web_read/web_save/formatted_read_group explicitly, preserving the upstream method-policy contract even on releases lacking those APIs. Commits: 17 fb2674e, 18 b51e719, 16 f4cbefa.
- After git push, pull_and_apply(env_name=E,restart=true,summary_only=true) succeeded for 17/18. run_odoo_tests(env_name=E,modules="odumcp",summary_only=true) passed 212 tests including dependent OduPilot: 17 output 552eecbb, 18 output 042b2608. Read tail confirmed real completion.
- Before cleanup, run_odoo_shell(env_name=E,auto_commit=false) executed:

```python
p = self.env['odumcp.profile'].browse(int(self.env['ir.config_parameter'].sudo().get_param('odumcp.port_upgrade_profile_id')))
assert p.exists() and p.code == 'upgrade_preservation' and p.rate_limit_per_minute == 37 and p.default_model_access == 'read'
assert self.env.ref('odumcp.profile_administrator').code == 'admin'
assert self.env.ref('odumcp.profile_reader').code == 'readonly'
print('Existing profile ID/settings preserved; seeded profiles present')
print(self.env['ir.module.module'].search([('name','in',['odubook','odumcp','odupilot','oduscale','odulogin'])]).read(['name','state','installed_version']))
```

- All assertions passed for 17/18; all five modules installed, MCP version major.0.1.4.0. delete_environment for mcp-port-17 and mcp-port-18 succeeded.
- Created mcp-port-16 with the original create arguments replacing version with 16, still at 99cf545 before publication. Auto-install of all five old modules succeeded; loaded development guide 16. Created the same preservation fixture (ID 1, version 16.0.1.1.0), then pushed f4cbefa.
- pull_and_apply(env_name="mcp-port-16",upgrade="odumcp",summary_only=true): exit 0, output 6221ca7f. Started full five-module tests.
- Started create_environment(env_name="mcp-fresh-18",branch="18.0",repo_url="https://github.com/oduflow/oduflow-client-addons",odoo_image="odoo:18.0",template_name="none",auto_install_modules="odubook,odumcp,odupilot,oduscale,odulogin") for clean installation at b51e719.

### 22:17–22:20 UTC — Odoo 16 upgrade and clean-install integration
- mcp-port-16 full five-module suite at f4cbefa: **304 tests, 0 failures, 0 errors**, output 709b9be0.
- The preservation/seed inspection above also passed on 16; all five modules installed, MCP 16.0.1.4.0. Deleted mcp-port-16 successfully.
- mcp-fresh-18 clean installation succeeded with all five modules at b51e719. Resource naming follows E pattern above. Loaded guide 18.
- run_odoo_tests(env_name="mcp-fresh-18",modules="odumcp",test_tags="/odumcp",upgrade=false,summary_only=true): 107 tests, 1 failure/0 errors, output 37451db9. Fresh installation of dependent OduPilot adds a read-only AI Agent policy to existing profiles; the upstream assertion that the administrator profile contains no policies was too broad.
- Read-only run_odoo_shell printed profile.policy_ids fields model_id/allow_read/allow_write/allow_create/allow_unlink and profile.user_ids.ids: AI Agent read only, no assigned users. Source inspection confirmed OduPilot's post_init_hook adds it.
- Fixed only test scope: assert no MCP-owned seeded per-model policies, allowing installed extensions to contribute policies. Commits 18 ab89d87, 17 fc199b2, 16 e4a22bd, all pushed. Runtime behavior unchanged.
- pull_and_apply(env_name="mcp-fresh-18",restart=true,summary_only=true) succeeded. Targeted rerun with modules="odumcp",test_tags="/odumcp:TestOduMcp.test_seeded_administrator_profile_opens_everything_but_deletion",upgrade=false,summary_only=true: 1 passed, zero failures/errors, 840a4f67.
- Deleted mcp-fresh-18 successfully. Started mcp-fresh-17 and mcp-fresh-16 using the same fresh create arguments with matching branches/images, at fc199b2/e4a22bd respectively.

### 22:20–22:22 UTC — final clean installations and cleanup
- Clean provisioning of mcp-fresh-17 at fc199b2 and mcp-fresh-16 at e4a22bd succeeded, including all five modules. Loaded the respective development guide immediately after creation. Resource naming follows E pattern above.
- Executed run_odoo_tests(env_name=E,modules="odumcp",test_tags="/odumcp",upgrade=false,summary_only=true): 17 **107 passed**, zero failures/errors, 779ed17d; 16 **107 passed**, zero failures/errors, 3389f3b4.
- delete_environment(env_name="mcp-fresh-17") and delete_environment(env_name="mcp-fresh-16") succeeded. All six temporary environments created in this operation are removed.

## Final verification summary

| Major | Upgrade from 1.1.0 | Five-module suite after upgrade | MCP on fresh install | Final tested code |
| --- | --- | --- | --- | --- |
| 18 | Succeeded; profile ID/settings preserved | 304 cases; framework-name failure fixed, 212 MCP/dependent tests passed on rerun | 107 cases; extension-policy assertion fixed, affected test passed on rerun | ab89d87 |
| 17 | Succeeded; profile ID/settings preserved | 304 cases; framework-name failure fixed, 212 MCP/dependent tests passed on rerun | 107 passed | fc199b2 |
| 16 | Succeeded; profile ID/settings preserved | 304 passed | 107 passed | e4a22bd |

- Final status: succeeded. Runtime/module tests passed after the corrections recorded above. No tests were skipped to hide failures; narrowly repeated the affected test after the final test-only correction.
- All ports include upstream through 57ea7ec. MCP versions: 18.0.1.4.0, 17.0.1.4.0, 16.0.1.4.0.
- Final Python/XML parsing, whitespace checks and documentation checks (default and against pre-port branch heads) passed. English, Polish and Russian documentation synchronized.
- No browser visual check, public route/VPN check, standalone server retest or production rollout performed. Standalone server code was unchanged.
- No remaining temporary environments or unresolved test failures. Maintainers can deploy the appropriate branch and upgrade odumcp in place; no cross-major database migration is provided.
- Historical journals from 19.0 were retained unchanged via Git merge; their earlier installation results were not represented as checks performed in this operation.

Operation completion UTC: 2026-09-21T22:22:04.788398+00:00.
