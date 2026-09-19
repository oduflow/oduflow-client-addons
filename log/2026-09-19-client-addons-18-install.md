# 2026-09-19 — client-addons-18 — installation tests

## Context and Status

- Purpose and scope: Fresh installation of odubook, odumcp, odupilot and oduscale on Odoo 18.
- Operation start/end (UTC): 2026-09-19T21:55:16.481282+00:00; end pending.
- Operator and tool/MCP instance: Codex, mcp__odusfera; explicitly authorized by user.
- Oduflow instance/team:
- Environment/database and service names/IDs:
- Initial state and dependencies:
- Status: in progress.
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
