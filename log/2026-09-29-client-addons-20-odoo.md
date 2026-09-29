# 2026-09-29 — client-addons-20 — Odoo 20 branch bring-up

## Context and Status

- Purpose and scope: create branch `20.0` from `19.0` and verify that all five
  repository addons load on Odoo 20.
- Operation start/end (UTC): 2026-09-29 13:42 — 2026-09-29 14:05.
- Operator and tool/MCP instance: Claude Opus 5 via the `megaflow_veleagro` MCP server.
- Oduflow instance/team: megaflow.velesagro.pl, team 1.
- Environment/database and service names/IDs: environment `client-addons-20`,
  database `oduflow_1_client-addons-20`, container `oduflow-1-client-addons-20-odoo`.
- Initial state and dependencies: no pre-existing environment for this repository on
  this Oduflow instance; shared PostgreSQL cluster `oduflow-db:5432`.
- Status: failed — the module load test was not performed.
- Provenance: executed now.

## Source and Images

- Repository URL, branch and deployed commit:
  `https://github.com/oduflow/oduflow-client-addons`, branch `20.0`,
  commit `d0609a2` (branched from `19.0` at `5fe5724`).
- Odoo version/image: `odoo:20.0`, reported by the server as `20.0-20260926`.
- Service image tags and resolved digests: unknown — not reported by the tooling.
- Configuration paths and content/diffs or links pinned to the applied revision:
  no environment configuration was modified; `/etc/odoo/odoo.conf` left at defaults.
  Source change is the manifest version bump in commit `d0609a2`.

## Network and Persistence

- Public URLs, TLS and published routes/ports:
  `http://client-addons-20.megaflow.velesagro.pl/web?debug=1` (plain HTTP via Traefik).
- Internal container names, networks, API endpoints and ports:
  `oduflow-1-client-addons-20-odoo`, Odoo on port 8069; database reached at
  `oduflow-db:5432` as user `u_1_client-addons-20`.
- VPN prefixes, DNS, tags and ACL policy: not applicable — no VPN component.
- Volumes, mount paths, access modes, ownership and backup scope:
  workspace `/srv/oduflow/data/team_1/workspaces/client-addons-20`, addons mounted at
  `/mnt/extra-addons/addons`. No backup scope — disposable environment, never initialized.
- Non-secret environment variables and runtime options: defaults only; template `none`.

## Credentials

- Variable names and storage references only (values: `<redacted>`):
  database user/password provisioned automatically by Oduflow; values never read or recorded.
- Provisioning, issue/expiry times and rotation/revocation procedure:
  provisioned by `create_environment`; revoked with the environment on deletion.

## Backup and Rollback

- Backup/snapshot reference, timestamp and restore prerequisites: no backup taken —
  the database never initialized and held no data.
- Rollback steps and actual result, or explicitly not performed: no rollback performed.
  The environment was deleted by the user at approximately 14:00 UTC.

## Operations

### 13:42 UTC — create environment on odoo:20.0

- Preconditions and intended change: branch `20.0` created locally from `19.0` and pushed
  to origin; provision a fresh environment to test module loading.
- Exact tool/command and sanitized arguments:
  `git checkout -b 20.0 19.0`, `git push -u origin 20.0`, then
  `create_environment(branch="20.0", env_name="client-addons-20",
  repo_url="https://github.com/oduflow/oduflow-client-addons",
  odoo_image="odoo:20.0", template_name="none")`.
- Executed / planned / unverified: executed.
- Job/output ID, exit status and observed result: succeeded. Containers running;
  URL `http://client-addons-20.megaflow.velesagro.pl/web?debug=1`.
  The first client call timed out and returned a `BusyError`; the server-side creation
  completed regardless and `get_environment_info` confirmed the result.
- Failure and corrective action, if any: none at this step.

### 13:55 UTC — install odubook (failed)

- Preconditions and intended change: install the first addon to start the per-module
  load test against an empty database.
- Exact tool/command and sanitized arguments:
  `install_odoo_modules(env_name="client-addons-20", modules="odubook")`.
- Executed / planned / unverified: executed.
- Job/output ID, exit status and observed result: exit code 255, output ID `f003a13f`.
  Two independent defects surfaced:
  1. All five addons were rejected before loading —
     `The module <name> has an incompatible version, setting installable=False`
     for `odubook`, `odulogin`, `odumcp`, `odupilot` and `oduscale`, because their
     manifest versions were still in the `19.0.x` series.
  2. Database initialization of core `base` failed outright:
     `UserWarning: Postgres version is 150019, lower than minimum required 160000`,
     then `psycopg2.errors.UndefinedFunction: function any_value(integer) does not exist`
     while parsing `odoo/addons/base/security/base_groups.xml:37`
     (`res.groups` record `group_erp_manager`), raised from
     `res_users.py:531 _recompute_user_share`. The registry load failed and Odoo
     reported `CRITICAL Failed to initialize database oduflow_1_client-addons-20`.
- Failure and corrective action, if any: defect 1 was corrected in commit `d0609a2`
  (manifest versions moved to the `20.0.x` series). Defect 2 is an infrastructure
  limit and was not corrected — see Verification and Follow-up.

### 14:00 UTC — apply version bump (failed on the uninitialized database)

- Preconditions and intended change: deliver commit `d0609a2` and upgrade the addons.
- Exact tool/command and sanitized arguments:
  `pull_and_apply(env_name="client-addons-20",
  upgrade="odubook,odulogin,odumcp,odupilot,oduscale", summary_only=True)`.
- Executed / planned / unverified: executed.
- Job/output ID, exit status and observed result: failed —
  `Command 'psql' failed (exit 1): ERROR: relation "ir_module_module" does not exist`.
  Expected consequence of the failed `base` initialization. The git pull itself
  succeeded: `run_odoo_command` confirmed all five manifests in
  `/mnt/extra-addons/addons/*/__manifest__.py` carry `20.0.x` versions.
- Failure and corrective action, if any: no corrective action available at this level.

### ~14:00 UTC — environment deleted by user

- Preconditions and intended change: the user deleted `client-addons-20` to recreate it.
- Exact tool/command and sanitized arguments: performed by the user outside this session.
- Executed / planned / unverified: executed by the user; not observed directly.
- Job/output ID, exit status and observed result: `list_environments` at 14:03 UTC no
  longer lists `client-addons-20`; no replacement environment had appeared yet.
- Failure and corrective action, if any: recreation does not address the PostgreSQL
  version limit, which is a property of the shared cluster rather than the environment.

## Verification

| Time (UTC) | Check / command | Expected | Observed | Evidence / output ID |
| --- | --- | --- | --- | --- |
| 13:49 | `get_environment_info(client-addons-20)` | Containers running on `odoo:20.0` | All containers running; branch `20.0`; image `odoo:20.0` | tool response |
| 13:55 | `install_odoo_modules(odubook)` | Module installs | Exit 255; `base` registry load failed; all five addons marked `installable=False` | output ID `f003a13f` |
| 13:58 | `run_db_query("SHOW server_version")` | PostgreSQL ≥ 16 for Odoo 20 | `15.19 (Debian 15.19-1.pgdg13+2)` | tool response |
| 13:59 | `list_services()` | An alternative PostgreSQL 16 cluster | None — every service uses the same `oduflow-db:5432` | tool response |
| 14:00 | `run_odoo_command` grep of container manifests | `20.0.x` versions present in container | All five manifests report `20.0.x` | exit 0 |
| — | Install of `odubook`, `odulogin`, `odumcp`, `odupilot`, `oduscale` on Odoo 20 | All five install | **Not run** — blocked by the database failure | — |
| — | `run_odoo_tests` for any module | Tests pass | **Not run** — blocked by the database failure | — |

## Final State and Follow-up

- Running/stopped services and deployed revision: environment `client-addons-20` no
  longer exists. Branch `20.0` is published at commit `d0609a2`.
- Cleanup of temporary devices, keys, files and test resources: the environment and its
  database were removed by the user; nothing else was created.
- Remaining limitations and unverified behavior: **the Odoo 20 module load test was not
  performed.** Odoo `20.0-20260926` requires PostgreSQL 16 or newer, and the shared
  team cluster runs 15.19, so core `base` cannot initialize and no addon is reached.
  `update_environment` always preserves the database connection variables, so an
  environment cannot be pointed at a different cluster from the agent tooling; this
  requires an operator-level upgrade of `oduflow-db`. Consequently nothing is known yet
  about the actual Odoo 20 compatibility of the addon code itself — only that the
  manifest versions no longer disqualify them.
- Follow-up owner/action/date: operator to upgrade the shared `oduflow-db` cluster to
  PostgreSQL 16+; afterwards recreate `client-addons-20` on `odoo:20.0` from branch
  `20.0` and run the five module installs plus `run_odoo_tests`. Chosen by the user on
  2026-09-29 in preference to testing on `odoo:19.0`.
- Related guide and previous/next journal entries: previous —
  [2026-09-21 MCP major-version ports](2026-09-21-mcp-ports-odoo.md).
