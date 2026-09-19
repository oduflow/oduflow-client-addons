# 2026-09-19 — client-addons-18 — installation tests

## Context and Status

- Purpose and scope: Fresh installation of odubook, odumcp, odupilot and oduscale on Odoo 18.
- Operation start/end (UTC): 2026-09-19T21:55:16.481282+00:00; end pending.
- Operator and tool/MCP instance: Codex, mcp__odusfera; explicitly authorized by user.
- Oduflow instance/team:
- Environment/database and service names/IDs:
- Initial state and dependencies:
- Status: succeeded; temporary environment removed.
- Provenance: executed now, or historical source and import date.

## Source and Images

- Repository URL, branch and deployed commit: https://github.com/oduflow/oduflow-client-addons, 18.0, 1987e2a (planned).
- Odoo version/image: odoo:18.0 (planned).
- Service image tags and resolved digests (unknown if unavailable):
- Configuration paths and content/diffs or links pinned to the applied revision:

## Network and Persistence

- Public URLs, TLS and published routes/ports:
- Internal container names, networks, API endpoints and ports:
- VPN prefixes, DNS, tags and ACL policy:
- Volumes, mount paths, access modes, ownership and backup scope:
- Non-secret environment variables and runtime options:

## Credentials

- Variable names and storage references only (values: `<redacted>`):
- Provisioning, issue/expiry times and rotation/revocation procedure:

## Backup and Rollback

- Backup/snapshot reference, timestamp and restore prerequisites:
- Rollback steps and actual result, or explicitly not performed:

## Operations

### HH:MM UTC — operation

- Preconditions and intended change:
- Exact tool/command and sanitized arguments, including configuration changes:
- Executed / planned / unverified:
- Job/output ID, exit status and observed result:
- Failure and corrective action, if any:

## Verification

| Time (UTC) | Check / command | Expected | Observed | Evidence / output ID |
| --- | --- | --- | --- | --- |
| | | | | |

Include service health, internal API access, public route restrictions, module
tests and end-to-end VPN access/revocation where applicable. Mark checks not run.

## Final State and Follow-up

- Running/stopped services and deployed revision:
- Cleanup of temporary devices, keys, files and test resources:
- Remaining limitations and unverified behavior:
- Follow-up owner/action/date:
- Related guide and previous/next journal entries:

## Operation record

### 2026-09-19T21:55:16.481282+00:00 — Provisioning planned

`mcp__odusfera__create_environment(env_name="client-addons-18", branch="18.0", repo_url="https://github.com/oduflow/oduflow-client-addons", odoo_image="odoo:18.0", template_name="none")`. Fresh database; no production copy. No backup or rollback performed. Network, volumes, image digest and team identity unknown until provisioning returns. No credentials recorded.

### 2026-09-19T21:56:54.915946+00:00 — Provisioned

Creation succeeded in 60.8s; base initialized, requirements installed. URL https://client-addons-18.oduflow.odusfera.pl; team_1; container oduflow-1-client-addons-18-odoo; database oduflow_1_client-addons-18; workspace /srv/oduflow-data/team_1/workspaces/client-addons-18. Image digest and volume metadata unknown. Next: `pull_and_apply(env_name="client-addons-18", install="odubook,odumcp,odupilot,oduscale", summary_only=true)`.

### 21:57 UTC — First installation failed

`pull_and_apply` exited 255; output_id `5d75b984`. XML inheritance failed on `page_security` in odumcp/views/res_users_views.xml. Replaced the Odoo 19 XPath with the existing `access_rights` page in odumcp and odupilot. No installed-state claim is made from the misleading tool preamble.

### 21:58 UTC — Second installation failed

Apply output `a215a7a9`, exit 255: ir.ui.view uses `groups_id`, not the Odoo 19 `group_ids`. Corrected restricted agent and wizard views.

### 21:59–22:00 UTC — Installed; initial tests failed

Apply `93db0bef` exited 0, all four modules installed. `run_odoo_tests(env_name="client-addons-18", modules="odubook,odumcp,odupilot,oduscale", summary_only=true)` returned 14 failures and 5 errors / 265, output `a707c755`. Correcting field access API and tests for HTTP helper, view XPath, completed activity deletion, HTML bus encoding, locale formatting, and missing fixture email.

### 22:03–22:07 UTC — Final runtime verification

Second test output `ff878f9e`: 1 failure, 1 error / 265; fixed sender email fixture and the completed-activity deletion assertion. Final deployed code `c91429a`: `run_odoo_tests` output `aad65b13` reports **0 failures, 0 errors / 265 tests**. Rollback-only `run_odoo_shell` verified all four modules are installed at 18.0.1.0.0. Public `http_request_to_odoo(/web/login)` received Cloudflare HTTP 403; direct container `python3 -c "import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8069/web/login'); print(r.status)"` returned 200. Browser UI and external AI/VPN integrations were not tested. Documentation synchronization follows; no application code changes after the passing run.

Cleanup planned: delete_environment(env_name="client-addons-18") to release our temporary slot for Odoo 16. No backups required for this disposable test database; no production data used.

### 22:09 UTC — Cleanup completed

`delete_environment(env_name="client-addons-18")` returned torn down. All application tests passed before teardown. Branch remains on origin; temporary worktree retained for code review.

### 22:24 UTC — Static browser import correction

Official Odoo 18 sources show DiscussAppCategory under @mail/core/public_web/discuss_app_category_model. Corrected the old Odoo 19 import path after teardown; all frontend import paths were checked against upstream 18.0 sources and all 13 JavaScript files parsed with node --input-type=module --check. This final import-only correction was not rerun in a browser. Server test evidence above remains tied to c91429a.
