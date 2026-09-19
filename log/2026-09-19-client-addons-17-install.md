# 2026-09-19 — client-addons-17 — installation tests

## Context and Status

- Purpose and scope: Unknown or not inspected; see the operation record below.
- Operation start/end (UTC): Unknown or not inspected; see the operation record below.
- Operator and tool/MCP instance: Unknown or not inspected; see the operation record below.
- Oduflow instance/team: Unknown or not inspected; see the operation record below.
- Environment/database and service names/IDs: Unknown or not inspected; see the operation record below.
- Initial state and dependencies: Unknown or not inspected; see the operation record below.
- Status: succeeded; temporary environment removed.
- Provenance: executed now, or historical source and import date.

## Source and Images

- Repository URL, branch and deployed commit: Unknown or not inspected; see the operation record below.
- Odoo version/image: Unknown or not inspected; see the operation record below.
- Service image tags and resolved digests (unknown if unavailable): Unknown or not inspected; see the operation record below.
- Configuration paths and content/diffs or links pinned to the applied revision: Unknown or not inspected; see the operation record below.
## Network and Persistence

- Public URLs, TLS and published routes/ports: Unknown or not inspected; see the operation record below.
- Internal container names, networks, API endpoints and ports: Unknown or not inspected; see the operation record below.
- VPN prefixes, DNS, tags and ACL policy: Unknown or not inspected; see the operation record below.
- Volumes, mount paths, access modes, ownership and backup scope: Unknown or not inspected; see the operation record below.
- Non-secret environment variables and runtime options: Unknown or not inspected; see the operation record below.
## Credentials

- Variable names and storage references only (values: `<redacted>`): Unknown or not inspected; see the operation record below.
- Provisioning, issue/expiry times and rotation/revocation procedure: Unknown or not inspected; see the operation record below.
## Backup and Rollback

- Backup/snapshot reference, timestamp and restore prerequisites: Unknown or not inspected; see the operation record below.
- Rollback steps and actual result, or explicitly not performed: Unknown or not inspected; see the operation record below.
## Operations

### HH:MM UTC — operation

- Preconditions and intended change: Unknown or not inspected; see the operation record below.
- Exact tool/command and sanitized arguments, including configuration changes: Unknown or not inspected; see the operation record below.
- Executed / planned / unverified: Unknown or not inspected; see the operation record below.
- Job/output ID, exit status and observed result: Unknown or not inspected; see the operation record below.
- Failure and corrective action, if any: Unknown or not inspected; see the operation record below.
## Verification

| Time (UTC) | Check / command | Expected | Observed | Evidence / output ID |
| --- | --- | --- | --- | --- |
| | | | | |

Include service health, internal API access, public route restrictions, module
tests and end-to-end VPN access/revocation where applicable. Mark checks not run.

## Final State and Follow-up

- Running/stopped services and deployed revision: Unknown or not inspected; see the operation record below.
- Cleanup of temporary devices, keys, files and test resources: Unknown or not inspected; see the operation record below.
- Remaining limitations and unverified behavior: Unknown or not inspected; see the operation record below.
- Follow-up owner/action/date: Unknown or not inspected; see the operation record below.
- Related guide and previous/next journal entries: Unknown or not inspected; see the operation record below.
## Operation record

### 2026-09-19T22:00:25.653538+00:00 — Provisioning planned

Scope: install odubook, odumcp, odupilot and oduscale in a fresh Odoo 17 database through mcp__odusfera, authorized by the user. Repository https://github.com/oduflow/oduflow-client-addons; branch 17.0. Team, URLs, containers, network, volumes and image digest unknown until provisioning returns. No backup or rollback performed. No secrets recorded.

Planned: `create_environment(env_name="client-addons-17", branch="17.0", repo_url="https://github.com/oduflow/oduflow-client-addons", odoo_image="odoo:17.0", template_name="none")`.

### 22:00–22:03 UTC — Provisioned; installation failed

Creation succeeded (63.8s), base and requirements installed. Team_1; URL https://client-addons-17.oduflow.odusfera.pl; container oduflow-1-client-addons-17-odoo; database oduflow_1_client-addons-17; workspace /srv/oduflow-data/team_1/workspaces/client-addons-17. Revision 978d997. `pull_and_apply(env_name="client-addons-17", install="odubook,odumcp,odupilot,oduscale", summary_only=true)` exited 255, output `4018fe58`. Oduscale view validation requires company_id for every user to evaluate server_id company domain; added invisible unrestricted company_id.

### 22:04–22:08 UTC — Installation passed; test compatibility fixes

Apply `ffa26edd` exited 0. Test output `66adc438` reported 0/0 of 45 but **was not a complete pass**: asset pregeneration crashed on missing mail.Message.bodyAsNotification. Removed that obsolete inheritance, retaining decision cards in mail.Message. After restart, tests `210fcf2a` reported 0 failures, 13 errors / 163; errors: has_access unavailable, XPath list instead of tree in test, env._ unavailable. Ported these APIs and fixtures.

### 22:12 UTC — Full test pass still pending

Output `f7659070`: 2 failures and 1 error / 265. Correcting bot-message classification against the native author format; adapting event and channel serialization assertions to legacy mail.message/updated and channel_info.

### 22:14–22:16 UTC — Verification succeeded

Final code a410bdc: run_odoo_tests output `16c88667`: **0 failures, 0 errors / 265 tests**. Rollback-only ORM inspection confirmed all four modules installed at 17.0.1.0.0. Internal HTTP check via urllib at http://127.0.0.1:8069/web/login returned 200. No browser UI or live AI/VPN integration tests. Documentation-only synchronization follows. Cleanup planned: delete_environment(env_name="client-addons-17"). No backup or rollback performed; disposable database contains no production data.

### 22:27 UTC — Final verification

Final application revision `c7710e6`: `run_odoo_tests(env_name="client-addons-17", modules="odubook,odumcp,odupilot,oduscale", summary_only=true)` returned **0 failures, 0 errors / 265 tests**, output `c9fc0323`. All four module states are installed at 17.0.1.0.0; internal /web/login HTTP 200. All 12 frontend JavaScript files passed Node syntax checks. Documentation and translated mirrors are being synchronized after the passing tests. Browser UI and external AI/VPN integrations were not tested. Cleanup: planned deletion of our temporary environment; no backup or rollback performed.

### 2026-09-19T22:28:46.008654+00:00 — Cleanup completed

`delete_environment(env_name="client-addons-17")` returned torn down. All four modules had passed installation and all 265 tests before removal. No environment retained; branch and local worktree retained for review. Documentation checks passed for English sources and Polish/Russian mirrors, including comparison with base 7f78bdf.

## Final inventory

- Instance/team: odusfera, team_1. Environment/database: client-addons-17 / oduflow_1_client-addons-17, now removed.
- Container: oduflow-1-client-addons-17-odoo, removed; workspace was /srv/oduflow-data/team_1/workspaces/client-addons-17.
- Route: HTTPS client-addons-17.oduflow.odusfera.pl to Odoo; internal HTTP 8069. Shared DB host observed as oduflow-db. Network names, image digests and volume mappings were not inspected.
- Credentials: no application secrets issued by this task; platform-managed database credentials were not read or recorded. No custom environment variables supplied.
- Source: https://github.com/oduflow/oduflow-client-addons, branch 17.0, based on 7f78bdf. Code and configuration are pinned by the revisions in the operation timeline; .oduflow/requirements.txt supplied Python dependencies.
- No production data, VPN routes, DNS or shared services changed. No backups or rollback performed.
- Limitations: browser interaction and external AI/VPN services untested. Owner for subsequent acceptance: repository maintainer.
