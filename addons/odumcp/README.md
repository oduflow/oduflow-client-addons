# OduMCP

OduMCP connects MCP clients to Odoo 19 while keeping authorization, policy,
approval, and audit decisions inside Odoo.

The project has two deliberately separate components:

- `addons/odumcp` owns Odoo identities, MCP profiles, ACL and record
  rule enforcement, change approvals, execution, audit, and resource events.
- `addons/odumcp/deploy/odumcp_server` is a single-replica FastMCP
  v4 HTTP sidecar. It owns MCP protocol
  handling, connection pooling, per-user serialization, circuit breaking, and
  subscription delivery.

```text
MCP client
  |  Streamable HTTP + user's OduMCP API key
  v
FastMCP sidecar (one replica)
  |  same key, forwarded only for the current request
  v
OduMCP control API
  |  effective Odoo user + MCP profile + ACLs + record rules
  v
Odoo ORM
```

There is no stdio transport, connector identity, shared connector secret,
sidecar-issued client token, or direct database access.

## Documentation

- [User guide](doc/user_guide.md)
- [Administrator guide](doc/admin_guide.md)
- [FastMCP sidecar reference](deploy/odumcp_server/README.md)
- [Control-plane specification](specs/odumcp_spec.md)
- [Sidecar specification](specs/odumcp_server_spec.md)

## Capabilities

- User-created Odoo API keys restricted to the `mcp` scope.
- MCP activation and one security profile configured directly on each Odoo user.
- Explicit model, field, operation, method, company, forced-domain, quota, and
  binary/report policies.
- Schema discovery, search, read, count, aggregation, attachments, reports, and
  bounded domain summaries.
- Preview-only create, update, delete, method, chatter, activity, and attachment
  tools.
- Immutable expiring approvals and exactly-once execution by approval ID.
- Immutable redacted audit records with request correlation IDs.
- HTTP health/readiness endpoints, safe-read retries, response limits, a
  transport-only circuit breaker, and one-operation-at-a-time enforcement per
  Odoo user.
- MCP `subscriptions/listen` updates for approval and MCP-executed record
  resources, backed by Odoo Bus long polling and short-lived event tickets.

## Installation

Install the addon on a fresh Odoo 19 database:

```bash
odoo \
  --addons-path=/path/to/odoo/addons,/absolute/path/to/oduflow-client-addons/addons \
  -d connect_addons_ng \
  -i odumcp \
  --stop-after-init
```

This release intentionally rejects databases that contain the obsolete
`odumcp.credential` schema. No migration or compatibility mode is provided.

Run the sidecar:

```bash
cd addons/odumcp/deploy/odumcp_server
uv sync
export ODUMCP_ODOO_URL=https://odoo.example.com
export ODUMCP_HOST=0.0.0.0
uv run odumcp-server
```

In Odoo, open the user, select **Account Security**, enable **MCP Active**, and
choose an MCP profile. The user then creates an API key in their own profile and
selects **MCP only**. Configure that key as the bearer token in their MCP client.

Odoo subscriptions require the standard Odoo evented worker and reverse-proxy
support for `/odumcp/v1/events`, just as Odoo's normal `/longpolling/poll`
endpoint does.

## Development

```bash
cd addons/odumcp/deploy/odumcp_server
uv sync --extra test
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest --cov=odumcp_server --cov-report=term-missing --cov-fail-under=95
```

Run addon tests only on a fresh database:

```bash
/path/to/odoo-bin \
  --addons-path=/path/to/odoo/addons,/absolute/path/to/oduflow-client-addons/addons \
  -d connect_addons_ng_test \
  -i odumcp \
  --test-enable \
  --test-tags=/odumcp \
  --stop-after-init
```

## Deployment Constraints

- Run exactly one sidecar replica.
- Do not add Redis, sticky sessions, or distributed locks for this deployment.
- Terminate TLS at a trusted reverse proxy and keep Odoo TLS verification on.
- Do not use an administrator account as an MCP user.
- Treat an empty allowlist as no access, never as wildcard access.

The addon is `LGPL-3`; the standalone sidecar is `Apache-2.0`.
