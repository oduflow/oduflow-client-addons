# 2026-09-15 — hr-headscale — environment removal

## Context and Status

- Purpose/scope: execute the user's instruction, “Drop env. PR & Merge”, by removing the development Odoo environment and preparing the repository for a release PR.
- Operation start/end (UTC): 2026-09-15 14:15–14:15:50.
- Operator/tool: Codex on behalf of Max, demo Odusfera MCP (`mcp__demo_odusfera__*`).
- Instance/team: demo.odusfera.pl / team 1.
- Environment/database: `hr-headscale` / `oduflow_1_hr-headscale`.
- Initial state: environment running, not protected; created 2026-09-14 23:16:43 UTC; last activity reported 2026-09-15 13:32:27 UTC.
- Scope excludes the separately managed `oduscale-hs`, `oduscale-gateway` services and their persistent volumes. They are not environment-owned resources.
- Status: succeeded. Provenance: operations executed now; prior module-test results are referenced as historical evidence only.

## Source and Images

- Repository: https://github.com/oduflow/oduflow-client-addons; branch `19.0-headscale`; local/remote HEAD at start `2e2b154`.
- Deployed code: last recorded `92c335c` in the [earlier installation journal](2026-09-15-hr-headscale-odumcp.md); actual container SHA not re-read before removal.
- Odoo image `odoo:19.0`; resolved digest unknown.
- Current configuration resources: [Oduscale deployment overview](../addons/oduscale/deploy/README.md). No configuration changes applied to running services in this operation.

## Network and Persistence

- Odoo URL: `https://hr-headscale.demo.odusfera.pl`; container `oduflow-1-hr-headscale-odoo`.
- Workspace: `/srv/oduflow-data/team_1/workspaces/hr-headscale`; shared PostgreSQL container/host `oduflow-db`.
- Managed teardown covers the Odoo environment and its owned resources. The deletion tool reports teardown success; physical database/filesystem removal was not independently inspected. Separately managed resources are retained.
- Historical service routes, VPN ranges, DNS, policy and volume mounts: [installation journal](2026-09-14-hr-headscale-oduscale.md). Not independently reverified during removal.
- Gateway configuration still targets `oduflow-1-hr-headscale-odoo:8069`; it cannot serve Odoo once that container is removed.
- No service environment variables, volume ownership or network settings modified.

## Credentials

- Odoo environment variable: `ODUSCALE_API_KEY=<redacted>`. No value saved in this journal.
- Deletion removes the environment configuration; it does not revoke the corresponding Headscale API key. Historical issue/expiry and rotation instructions remain in the installation journal/admin guide.
- No credentials issued or rotated in this operation.

## Backup and Rollback

- No new backup/snapshot or rollback performed; the user explicitly requested deletion of this development environment.
- Recreate with `create_environment` and install the modules using the repository and administrator guides. This recreates an empty Odoo database; deleted employee/audit data cannot be restored without an independent existing backup (availability unknown).

## Operations

### 14:15 UTC — inspect and prepare removal

- Executed `mcp__demo_odusfera__get_environment_info({"env_name":"hr-headscale"})`: Odoo and shared DB running; correct branch and environment confirmed. Raw output not saved because it includes environment secrets.
- Reviewed local Git status and prior deployment journal. Pending changes relocate deployment resources and documentation only; preserve them for the PR.
- Planned next: `mcp__demo_odusfera__delete_environment({"env_name":"hr-headscale"})`, followed by `mcp__demo_odusfera__list_environments({})` to verify absence.
- Job/output IDs: none returned by inspection.

### 14:15:50 UTC — execute and verify removal

- Executed `mcp__demo_odusfera__delete_environment({"env_name":"hr-headscale"})`: success, `Environment 'hr-headscale' has been torn down.` No job/output ID or numeric exit code returned.
- Executed `mcp__demo_odusfera__list_environments({})`: only the separate `control` stack remains; `hr-headscale` is absent. No other environment was modified.
- No failure, retry or corrective mutation was required. Did not call service or volume deletion tools.

## Verification

| Time (UTC) | Check | Expected | Observed | Evidence |
| --- | --- | --- | --- | --- |
| 14:15 | Environment inspection | Identify requested environment | Running, branch `19.0-headscale`, not protected | MCP environment info |
| 14:15:50 | Managed environment deletion | Successful teardown | Success reported | MCP delete result |
| 14:15:50 | Managed environment inventory | `hr-headscale` absent | Only `control` remains | MCP list result |

Application tests are not rerun for this documentation/removal operation. The earlier [OduMCP journal](2026-09-15-hr-headscale-odumcp.md) records 327 successful tests; those are historical results, not checks performed now.

## Final State and Follow-up

- `hr-headscale` is removed from the managed inventory. There is no deployed Odoo revision for that environment anymore.
- Headscale and the VPN gateway were not deleted or reconfigured; their health was not rechecked in this operation. No temporary resources were created.
- Owner: repository/environment maintainer. Retained gateway requires an Odoo backend again before VPN access can work; service/key cleanup is a separate follow-up if the retained stack is no longer needed.
- Related instructions: [Oduscale administration](../addons/oduscale/doc/admin_guide.md), [OduMCP administration](../addons/odumcp/doc/admin_guide.md).
