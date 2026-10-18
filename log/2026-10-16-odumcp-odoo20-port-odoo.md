# 2026-10-16 — odumcp20-test — OduMCP port to Odoo 20

## Context and Status

- Purpose and scope: make `odumcp` from branch `20.0` install and serve MCP on
  Odoo 20. Oduflow production provisioning (`sync_production_mcp`) reported
  "MCP FAILED" for an `odoo:20.0` production because the addon referenced the
  removed `ir.model.access` model.
- Operation start/end (UTC): 2026-10-16 ~20:35 — 20:49.
- Operator and tool/MCP instance: Claude Opus 5.5 (Claude Code session), plain
  Docker CLI on the maintainer's workstation; no Oduflow MCP tools were used.
- Oduflow instance/team: none — an isolated Docker stack, not an Oduflow
  environment. The local Oduflow instance and its containers were not touched.
- Environment/database and service names/IDs: Docker network `odumcp20-test-net`;
  PostgreSQL container `odumcp20-test-pg`; one-shot Odoo containers
  `odumcp20-test-baseline`, `odumcp20-test-install`, `odumcp20-test-clean`,
  `odumcp20-test-e2e-init`, `odumcp20-test-e2e-shell`, `odumcp20-test-e2e-http`.
  Databases `odumcp_base`, `odumcp_clean`, `odumcp_t1`…`odumcp_t5`, `odumcp_e2e`.
- Initial state and dependencies: empty PostgreSQL 16 cluster; every database
  created fresh with `--without-demo`.
- Status: succeeded.
- Provenance: executed now.

## Source and Images

- Repository URL, branch and deployed commit:
  `https://github.com/oduflow/oduflow-client-addons`, local branch `20.0-ir-access`
  based on `origin/20.0` at `aeafade`. Baseline run used `aeafade` unchanged; the
  final runs used the tree committed as `fb7b50b` + `e330936`.
- Odoo version/image: `odoo:20.0`, server version `20.0-20261015`,
  digest `odoo@sha256:3de556969ca7916fe7d1a7fa3be2a49307a147c5fa1491bc2c57dcb0b950bea5`.
- Service image tags and resolved digests: `postgres:16`,
  `postgres@sha256:1a6ab3f5345eb6dbe04a1349529caabdb0ab09293a09590fad07b2246bfa4b54`.
- Configuration paths and content/diffs or links pinned to the applied revision:
  image default `/etc/odoo/odoo.conf`; addons mounted read-only at
  `/mnt/extra-addons/addons`; `--addons-path /mnt/extra-addons/addons,<odoo>/addons`.

## Network and Persistence

- Public URLs, TLS and published routes/ports: none public. The E2E server was
  published on `127.0.0.1:18069` only.
- Internal container names, networks, API endpoints and ports: Odoo containers
  reached `odumcp20-test-pg:5432` on `odumcp20-test-net` (passed through the image
  entrypoint variables `HOST`, `USER`, `PASSWORD`).
- VPN prefixes, DNS, tags and ACL policy: not applicable.
- Volumes, mount paths, access modes, ownership and backup scope: no named
  volumes; PostgreSQL data lived in the container layer and was discarded.
- Non-secret environment variables and runtime options: `HOST=odumcp20-test-pg`,
  `USER=odoo`.

## Credentials

- Variable names and storage references only (values: `<redacted>`): PostgreSQL
  `PASSWORD` / `POSTGRES_PASSWORD` for the throwaway cluster; the E2E managed MCP
  key was a random 43-character token kept in a temporary file.
- Provisioning, issue/expiry times and rotation/revocation procedure: the key was
  provisioned with `res.users.apikeys._set_oduflow_key` and destroyed with the
  database; the temporary file was deleted.

## Backup and Rollback

- Backup/snapshot reference, timestamp and restore prerequisites: no backup —
  disposable databases only.
- Rollback steps and actual result, or explicitly not performed: not performed;
  the whole stack was removed.

## Operations

### ~20:35 UTC — reproduce the failure on unmodified `20.0`

- Preconditions and intended change: confirm the reported install failure.
- Exact tool/command and sanitized arguments:
  `odoo --addons-path … -d odumcp_base -i odumcp --without-demo --stop-after-init`.
- Executed / planned / unverified: executed (first attempts failed to reach the
  database because the image entrypoint appends `--db_host db`; repeated with
  `HOST=odumcp20-test-pg`).
- Job/output ID, exit status and observed result: exit 255,
  `KeyError: 'ir.model.access'` while loading `security/ir.model.access.csv`.
- Failure and corrective action, if any: access rights rewritten as
  `security/ir.access.csv` (commit `fb7b50b`).

### 20:37–20:38 UTC — install and module tests after the access-rights port

- Preconditions and intended change: verify the `ir.access` port.
- Exact tool/command and sanitized arguments: `-i odumcp --stop-after-init` on
  `odumcp_clean`; the same plus `--test-enable --test-tags /odumcp` on
  `odumcp_t1`/`odumcp_t2`.
- Executed / planned / unverified: executed.
- Job/output ID, exit status and observed result: clean install exit 0 with no
  warnings. Tests: `odumcp_t1` could not import (`_request_stack` removed from
  `odoo.http`); `odumcp_t2` reported 21 failed and 11 errors of 109 —
  `ir.config_parameter.get_param/set_param` and `Registry.clear_cache` removed,
  the API key wizard forcing scope `rpc`, and `toggle_active` removed.
- Failure and corrective action, if any: runtime port (commit `e330936`).

### 20:43–20:44 UTC — module tests and first end-to-end check

- Preconditions and intended change: verify the runtime port.
- Exact tool/command and sanitized arguments: tests on `odumcp_t3`/`odumcp_t4`;
  E2E on `odumcp_e2e`: `-i base --stop-after-init`, then `odoo shell` running
  `ir.module.module.update_list()`, `button_immediate_install()` for `odumcp` and
  `res.users.apikeys._set_oduflow_key(<redacted>)` (the Oduflow provisioning
  path), then an HTTP server on `127.0.0.1:18069`.
- Executed / planned / unverified: executed.
- Job/output ID, exit status and observed result: 0 failed, 0 errors of 109
  tests. Provisioning returned `state=installed`, `scope=mcp`, `changed=true`.
  `GET /odumcp/v1/health` 200, but `/odumcp/v1/identity` returned 403 even with
  the managed key: `TypeError: IrHttp._auth_method_mcp() takes 1 positional
  argument but 2 were given`.
- Failure and corrective action, if any: `_auth_method_mcp`/`_auth_method_mcp_event`
  accept Odoo 20's `routing` argument; an `HttpCase` now covers both routes
  (commit `e330936`).

### 20:46–20:48 UTC — final module tests and end-to-end check

- Preconditions and intended change: verify the final tree.
- Exact tool/command and sanitized arguments: tests on `odumcp_t5`; E2E repeated
  on a recreated `odumcp_e2e`; `curl` against `/odumcp/v1/health`, `/identity`,
  `/capabilities` and `/execute`.
- Executed / planned / unverified: executed.
- Job/output ID, exit status and observed result: see Verification.
- Failure and corrective action, if any: none.

## Verification

| Time (UTC) | Check / command | Expected | Observed | Evidence / output ID |
| --- | --- | --- | --- | --- |
| ~20:35 | Install unmodified `aeafade` | Reproduce failure | Exit 255, `KeyError: 'ir.model.access'` | Odoo log |
| 20:38 | Fresh install `-i odumcp` | Exit 0, no warnings | Exit 0, no warnings | Odoo log |
| 20:46 | `--test-enable --test-tags /odumcp` | All pass | 0 failed, 0 errors of 111 tests; no warnings | `odoo.tests.result` |
| 20:46 | Provisioning as Oduflow does it | Installed, MCP key set | `state=installed`, `scope=mcp`, `mcp_active=true` | shell output |
| 20:46 | `GET /odumcp/v1/health` | 200 | 200 | curl |
| 20:46 | `GET /odumcp/v1/identity` without key / with invalid key | 401 | 401 / 401 | curl |
| 20:46 | `GET /odumcp/v1/identity` with managed key | 200 | 200, user `admin` | curl |
| 20:47 | `POST /odumcp/v1/execute` `records.search` on `res.partner` and `ir.access` | 200 | 200 / 200 | curl |
| 20:47 | `GET /odumcp/v1/capabilities` | 200 | 200 | curl |
| — | Upgrade of an existing 19.0 database to Odoo 20 | — | **Not run** | — |

## Final State and Follow-up

- Running/stopped services and deployed revision: nothing running; branch
  `20.0-ir-access` (`fb7b50b`, `e330936`, plus this documentation commit) is local
  and not pushed.
- Cleanup of temporary devices, keys, files and test resources: all
  `odumcp20-test-*` containers and `odumcp20-test-net` removed; key file deleted.
- Remaining limitations and unverified behavior: only fresh installs on Odoo 20
  were tested; the upgrade of a 19.0 database (Odoo's own `ir.model.access` to
  `ir.access` migration against the renamed CSV with preserved external IDs) was
  not tested. `odulogin` and `odupilot` on `20.0` still ship
  `ir.model.access.csv` and will fail to install on Odoo 20 in the same way.
- Follow-up owner/action/date: maintainer — push the branch, then re-run
  `sync_production_mcp` on the affected Odoo 20 production; port `odulogin` and
  `odupilot`.
- Related guide and previous/next journal entries: previous —
  [2026-09-29 Odoo 20 branch bring-up](2026-09-29-client-addons-20-odoo.md).
