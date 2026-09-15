# 2026-09-15 — hr-headscale — OduMCP

## Context and Status

- Purpose: rename the MCP addon to `odumcp` and install it without migration, after checking/removing its predecessor.
- Operation start (UTC): 2026-09-15 13:25; end: 2026-09-15 13:33.
- Operator/tool: Codex on behalf of Max, Odusfera MCP (`mcp__demo_odusfera__*`).
- Instance/team: demo.odusfera.pl / team 1.
- Environment: `hr-headscale`; database: `oduflow_1_hr-headscale`.
- Initial state: `oduscale` installed at 19.0.1.0.0; neither the predecessor MCP addon, `odumcp`, `odupilot`, nor `odubook` had a module record. No predecessor models or source path existed. No uninstall was necessary.
- Status: succeeded. Provenance: executed now.

## Source and Images

- Repository: https://github.com/oduflow/oduflow-client-addons; branch: `19.0-headscale`.
- Initial local HEAD: `0aec08c`; initial deployed SHA: unknown. Delivery: managed Git clone, commit/push then `pull_and_apply`.
- Odoo: `odoo:19.0`, runtime 19.0-20260908; image digest unknown.
- Configuration: addon directory changes from repository root to `addons/`; Python prerequisites in `.oduflow/requirements.txt`. No separate MCP server image is deployed by this operation.

## Network and Persistence

- Odoo: https://hr-headscale.demo.odusfera.pl/web?debug=1; new API route prefix `/odumcp/v1/`.
- Workspace: `/srv/oduflow-data/team_1/workspaces/hr-headscale`.
- Initial addon mount: `/mnt/extra-addons`; shared PostgreSQL hostname: `oduflow-db`.
- No service volumes, VPN policy, DNS or public port changes requested. Existing network/storage details remain in the [Oduscale journal](2026-09-14-hr-headscale-oduscale.md); not reverified here.

## Credentials

- Existing `ODUSCALE_API_KEY` is stored in environment configuration; value omitted. No credentials issued or rotated. MCP keys are not provisioned by this task.

## Backup and Rollback

- No backup or rollback performed. There was no predecessor module data to preserve.
- To undo the new installation, uninstall `odumcp` through Odoo before reverting source to the preceding revision and applying it. Module uninstall removes its data and dependent modules; inspect dependencies first.

## Operations

### 13:25 UTC — inspect before renaming

- Called `get_environment_info(env_name="hr-headscale")` and `get_odoo_development_guide(version="19")`.
- Called `run_odoo_shell(env_name="hr-headscale", auto_commit=false)` to read module names/states/versions for the predecessor and `odumcp`, `odupilot`, `odubook`, `oduscale`, and the predecessor's downstream dependencies. Exit 0: only `oduscale` was present/installed, no dependencies to remove.
- Second rollback-only shell checked predecessor `get_module_path(..., display_warning=False)` and `ir.model` namespace. Exit 0: path `None`, models `[]`.
- Removal was a verified no-op before changing source. No database records were deleted. Raw responses were not saved because environment information can contain secrets.

### 13:28–13:30 UTC — rename, validation and Git delivery

- Renamed addon, models, XML IDs, routes, config variables, server package/CLI, tests, OduPilot dependency, documentation and translations. No migration scripts or compatibility aliases added. Upstream attribution retained.
- Local Python/XML/manifest validation passed; bridge unittest suite: 24 passed; isolated server pytest suite: 102 passed. Logs: `/tmp/odumcp-bridge-tests.log`, `/tmp/odumcp-server-tests.log` (local temporary evidence).
- Documentation checker passed both default and `--against HEAD`; all prior/new source and mirrors synchronized.
- Git commit `af730e6` includes the previously completed module ports and addon relocation required to deliver the current workspace. Author/committer use configured `Max <litnimax@users.noreply.github.com>`; stale inherited Git identity variables were unset for Git commands.
- Initial `git push -u origin HEAD` failed non-fast-forward. Fetched and merged upstream `5b4ba46` (URL label fix), preserving its author/history and resolving the README conflict. Merge commit `786b50c`; cleanup commit `8328f24` removes duplicate old-layout change notes whose content already exists in the new module documentation. Push succeeded.
- Next planned operation: `pull_and_apply(env_name="hr-headscale", install="odumcp", upgrade="oduscale", summary_only=true)`. Oduscale upgrade applies its merged field labels after relocation.

### 13:31 UTC — first apply did not discover the module

- Executed planned `pull_and_apply(install="odumcp", upgrade="oduscale", summary_only=true)`. Tool reported: module not found after Odoo reported successful installation. No output ID was returned.
- Read-only command `find /mnt/extra-addons -maxdepth 3 -name __manifest__.py; sed -n '/^addons_path/p' /etc/odoo/odoo.conf` confirmed all four addons under `/mnt/extra-addons/addons`, while runtime config still used `/mnt/extra-addons`.
- Read complete `/etc/odoo/odoo.conf` through `read_file_in_odoo`: only `[options]`, `max_cron_threads = 1`, `addons_path = /mnt/extra-addons`.
- Corrective source change: add `addons_path = /mnt/extra-addons/addons` to `.oduflow/odoo.conf`, preserving `max_cron_threads = 1`. Commit/push and repeat apply with `restart=true` to regenerate configuration.

### 13:31 UTC — runtime correction and successful installation

- Commit `92c335c` delivered the durable addon path. Repeated `pull_and_apply(env_name="hr-headscale", install="odumcp", upgrade="oduscale", restart=true, summary_only=true)` still reported module not found; no output ID. Reread runtime and source configs: the managed clone had the new setting, but `/etc/odoo/odoo.conf` retained the old path. This demonstrates the apply did not update the runtime config; the platform cause was not diagnosed.
- Applied the same scoped setting through `write_file_in_odoo(env_name="hr-headscale", path="/etc/odoo/odoo.conf", user="odoo", content="[options]\nmax_cron_threads = 1\naddons_path = /mnt/extra-addons/addons\n\n")`, preserving all other lines.
- `restart_environment(env_name="hr-headscale", wait=true)`: success; Odoo ready, container `oduflow-1-hr-headscale-odoo`.
- `install_odoo_modules(env_name="hr-headscale", modules="odumcp")`: exit 0; module installed and container restarted. Runtime install log 13:31:07–13:31:10 shows correct addon path, model tables, all security/data/view files loaded, and registry success.
- Next: `run_odoo_tests(env_name="hr-headscale", modules="odumcp,oduscale", summary_only=true)`; this also upgrades the already-installed Oduscale field labels.

### 13:31–13:33 UTC — verification and cleanup

- `run_odoo_tests(env_name="hr-headscale", modules="odumcp,oduscale", summary_only=true)`: **0 failed, 0 errors of 96 tests**, output ID `7f372e8f`. This run upgraded both modules successfully.
- Rollback-only `run_odoo_shell` read module state, module source path, model namespaces, profile count and OduPilot dependencies. OduMCP ID 716 and Oduscale ID 714 are installed at `19.0.1.0.0`; OduPilot ID 717 is uninstalled and depends on `auth_totp`, `mail`, `odumcp`. Eight new MCP models exist; no predecessor models exist. Zero MCP profiles (clean installation).
- `translation_status(env_name="hr-headscale", module="odumcp", langs="pl_PL,ru_RU")`: both languages NOT ACTIVATED in this database. Existing language activation was preserved; UI translation loading for those locales was not exercised here. Markdown mirrors passed repository validation.
- `http_request_to_odoo(env_name="hr-headscale", path="/web/health")`: HTTP 200, `{"status":"pass"}`.
- Same HTTP tool for `/odumcp/v1/health`: HTTP 200, `{"status":"ok","service":"odumcp","api_version":"v1"}`; `/odumcp/v1/identity` without credentials: HTTP 401 with Bearer challenge. Predecessor health URL: HTTP 404.
- Isolated local Odoo 19 + PostgreSQL 15 containers tested the renamed dependency integration with OduPilot: **0 failed, 0 errors of 105 tests**. Command: `odoo -d odumcp_rename -i odupilot --db_host=odumcp-rename-db --db_user=odoo --db_password=<redacted> --without-demo --test-enable --test-tags /odupilot --stop-after-init --http-interface=127.0.0.1`. Log: `/tmp/odumcp-odupilot-tests.log`.
- Local containers used `odoo:19.0` and `postgres:15` on `odumcp-rename-test`, with `/srv/paseo/workspace/oduflow-client-addons/addons:/mnt/extra-addons:ro`. Installed only test prerequisites `markdown-it-py` and `linkify-it-py` in the disposable Odoo container. Test password was disposable; no environment credentials reused.
- Removed both local test containers and anonymous database volume with `docker rm -f -v odumcp-rename-odoo odumcp-rename-db`, then `docker network rm odumcp-rename-test`. All exited 0.
- Final source/path search found no predecessor technical identifiers. Upstream contributor names remain unchanged. Documentation checks passed default and `--against 0aec08c`; `git diff --check` passed.

## Verification

| Time (UTC) | Check | Expected | Observed | Evidence |
| --- | --- | --- | --- | --- |
| 13:25 | Predecessor module, source and model inspection | Establish uninstall requirements | All absent; no uninstall required | Two MCP shell calls, exit 0 |
| 13:31 | Odoo module tests | No failures | 96 passed | `7f372e8f` |
| 13:32 | Fresh OduPilot install and integration tests | Renamed dependency works | 105 passed | Local `/tmp/odumcp-odupilot-tests.log` |
| 13:28 | Server / bridge suites | Imports, URLs and integration behavior work | 102 / 24 passed | Local pytest / unittest logs |
| 13:32 | Health and anonymous authentication | Healthy, protected API | 200 / 401; predecessor route 404 | MCP HTTP requests |
| 13:33 | Documentation and predecessor identifier search | Synchronized, no stale technical names | Passed | Local checker and rg |

## Final State and Follow-up

- OduMCP `19.0.1.0.0` installed and Odoo running; Oduscale remains installed. Source revision `92c335c` deployed; later journal-only commits do not change module code.
- All **327 tests** passed: 96 environment tests, 105 isolated OduPilot tests, 102 standalone server tests and 24 bridge tests. UI browser testing and a live external MCP client/provider session were not run for this rename.
- No predecessor installation/data was found, so no uninstall or migration ran. No MCP profile, API key, sidecar service or AI provider was provisioned. OduPilot remains uninstalled in `hr-headscale`.
- Local test resources removed. Environment retained for the user's existing Oduscale deployment and OduMCP use.
- Platform follow-up: after any environment recreation/configuration reapplication, verify `/etc/odoo/odoo.conf` still contains `/mnt/extra-addons/addons`; two applies failed to propagate the repository setting and required the scoped correction documented above. Owner: environment maintainer, at next recreation.
- UI translations: activate Polish/Russian and upgrade the module when those interface languages are needed; activation was outside this installation's scope.
- Related guide: [OduMCP administration](../addons/odumcp/doc/admin_guide.md).
