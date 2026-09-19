# 2026-09-19 — client-addons-17 — installation tests

## Context and Status

- Purpose and scope:
- Operation start/end (UTC):
- Operator and tool/MCP instance:
- Oduflow instance/team:
- Environment/database and service names/IDs:
- Initial state and dependencies:
- Status: planned / in progress / succeeded / partial / failed.
- Provenance: executed now, or historical source and import date.

## Source and Images

- Repository URL, branch and deployed commit:
- Odoo version/image:
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

### 2026-09-19T22:00:25.653538+00:00 — Provisioning planned

Scope: install odubook, odumcp, odupilot and oduscale in a fresh Odoo 17 database through mcp__odusfera, authorized by the user. Repository https://github.com/oduflow/oduflow-client-addons; branch 17.0. Team, URLs, containers, network, volumes and image digest unknown until provisioning returns. No backup or rollback performed. No secrets recorded.

Planned: `create_environment(env_name="client-addons-17", branch="17.0", repo_url="https://github.com/oduflow/oduflow-client-addons", odoo_image="odoo:17.0", template_name="none")`.

### 22:00–22:03 UTC — Provisioned; installation failed

Creation succeeded (63.8s), base and requirements installed. Team_1; URL https://client-addons-17.oduflow.odusfera.pl; container oduflow-1-client-addons-17-odoo; database oduflow_1_client-addons-17; workspace /srv/oduflow-data/team_1/workspaces/client-addons-17. Revision 978d997. `pull_and_apply(env_name="client-addons-17", install="odubook,odumcp,odupilot,oduscale", summary_only=true)` exited 255, output `4018fe58`. Oduscale view validation requires company_id for every user to evaluate server_id company domain; added invisible unrestricted company_id.

### 22:04–22:08 UTC — Installation passed; test compatibility fixes

Apply `ffa26edd` exited 0. Test output `66adc438` reported 0/0 of 45 but **was not a complete pass**: asset pregeneration crashed on missing mail.Message.bodyAsNotification. Removed that obsolete inheritance, retaining decision cards in mail.Message. After restart, tests `210fcf2a` reported 0 failures, 13 errors / 163; errors: has_access unavailable, XPath list instead of tree in test, env._ unavailable. Ported these APIs and fixtures.
