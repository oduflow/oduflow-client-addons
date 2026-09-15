# Oduscale Technical Specification

## Scope and Dependencies

Odoo 19 application, version `19.0.1.0.0`, depending on `hr`, `mail` and Python
`requests`. The module uses standard Odoo list/form views and object actions;
it has no custom HTTP controllers or frontend assets. Headscale, the Tailscale
client, VPN ACL policy and gateway are external infrastructure.

## Data Model

| Model | Contract |
| --- | --- |
| `oduscale.server` | Company-owned API/login/Odoo URLs, token environment variable name, key lifetime and sync status. |
| `oduscale.connection` | Employee/server association, state, remote user identity, inventory and mail thread/activity support. |
| `oduscale.device` | Cached remote node identity, addresses, presence, online state, last seen and expiry. Missing nodes remain locally with presence/online cleared. |
| `oduscale.key` | Remote key ID, expiration, used/revoked flags; never the key secret. |
| `oduscale.enrollment` | Transient command dialog; `_transient_max_hours = 1`. |
| `hr.employee` | Adds `oduscale_connection_ids` and revokes active access when archived. |
| `res.users` | Revokes active access of linked employees when archived. |

Connections are unique by `(employee_id, server_id)` and by
`(server_id, remote_user_id)`. Keys and devices are unique by
`(connection_id, remote_id)`. Connection state and remote fields reject ordinary
create/write and context-default injection. Once a remote user is linked, the
employee/server cannot be reassigned and the connection cannot be deleted.

Server URL fields explicitly use the labels **API URL**, **Login URL** and
**Odoo URL**; the related connection field inherits **Odoo URL**.

## Actions and Remote State

- `action_activate()` locks connections with `SELECT ... FOR UPDATE`, checks employee
  and linked-user activity, and finds or creates a remote user named
  `oduscale-<database UUID without hyphens>-<connection ID>`. The stable name permits
  recovery after a remote success followed by a local rollback. State becomes `active`.
- `action_enroll()` requires active access and active identities, locks the row and
  creates a preauth key with `reusable=False`, `ephemeral=False`, empty ACL tags and
  a UTC expiration. Only the transient dialog receives the shell-quoted command;
  the permanent audit and chatter contain no key secret.
- `_sync()` fetches nodes and keys once per server for its selected linked connections,
  filters by remote user ID and upserts the local cache. Remote timestamps become
  naive UTC values; missing/year-one values become false. Missing devices are retained.
- `action_revoke()` locks the connection, expires every current remote user key and
  deletes every current user node, including uncached resources. It then marks local
  keys revoked, devices absent/offline and state `revoked`; the remote user remains.
- Device `action_revoke()` checks the current remote owner before deletion and refuses
  to delete a node reassigned to another user. Key `action_revoke()` expires that key
  without removing already enrolled nodes.
- Employee/user archive hooks run after the superclass write in the same transaction.
  Revocation errors propagate and roll back the archive. Remote requests themselves
  cannot be rolled back by PostgreSQL.

## Headscale API Contract

`_request()` appends `/api/v1` to `api_url`, reads a Bearer token from the configured
environment variable, disables redirects and uses connection/read timeouts of
5/20 seconds. HTTP failures expose only the status, network errors use a generic
message and invalid JSON raises a user error. A caller may tolerate 404 for deletion,
expiration or node lookup. No response body containing credentials is exposed.

| Operation | Endpoint |
| --- | --- |
| Test/find/create user | `GET /user`, `POST /user` |
| List/create keys | `GET /preauthkey`, `POST /preauthkey` |
| Expire key | `POST /preauthkey/expire` |
| List/read/delete nodes | `GET /node`, `GET /node/<id>`, `DELETE /node/<id>` |

## Access and Automation

`oduscale.group_manager` implies `hr.group_hr_user`; `base.group_system` implies
the manager group. Managers can CRUD unenrolled connections and use guarded access
actions, but have read-only ACLs on servers/devices/keys. Settings administrators
can create/write servers, but there is no server unlink ACL. Company rules cover
all four persistent models. Managed cache changes use internal methods and sudo.
The token variable field is restricted to Settings administrators; the transient
command field is restricted to managers.

`oduscale.cron_sync_headscale` runs `_cron_sync()` every five minutes as
`base.user_root`, with a savepoint per server. It revokes active connections for
inactive identities, then synchronizes. Handled `UserError` failures populate
`last_error`; successful server synchronization records `last_sync` and clears
that error. The cron is declared under `noupdate="1"`.

## Development and Validation

After publishing code for the selected environment, apply and test the module
with that environment name:

```text
pull_and_apply(env_name="<environment>", upgrade="oduscale", summary_only=true)
run_odoo_tests(env_name="<environment>", modules="oduscale", summary_only=true)
```

For an isolated Odoo test database with this repository's `addons/` on the addon path:

```sh
odoo -d TEST_DATABASE -i oduscale --without-demo \
  --test-enable --test-tags /oduscale --stop-after-init
```

The 16 tests in `tests/test_oduscale.py` cover enrollment and secret handling,
activation recovery, inactive identities, owner-filtered synchronization, uncached
revocation, partial failures, archive hooks and rollback, permissions, protected
remote identifiers, company isolation, reassigned nodes, HTTP redaction and URL/TTL
validation. The [historical installation entry](../../../log/2026-09-14-hr-headscale-oduscale.md) records the September
14, 2026 installation, test and VPN checks; those are historical results, not a test
run performed for this documentation change.

## Service Deployment Contract

Reusable service provisioning, credentials, gateway routing and backup instructions
live in `admin_guide.md`. Configuration examples live under `addons/oduscale/deploy/headscale/`
and `addons/oduscale/deploy/gateway/`; they contain deployment-specific values and must be adapted.
Concrete hosts, image versions, applied revisions and verification evidence belong
in `log/`, following the repository agent rules. Historical journal entries
do not define the current runtime state or supported image-version range.
