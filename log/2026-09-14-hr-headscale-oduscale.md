# 2026-09-14 — hr-headscale Oduscale installation

## Record provenance and status

Imported on 2026-09-15 from the former deployment README. This is a historical
record of the demo installation and its documented reproduction procedure, not
a fresh inspection of the running services. Exact execution times, tool job IDs,
image digests and the deployed Git SHA were not recorded in the source.
The original validation reported a successful installation. No backup/restore
exercise or rollback result was recorded.

The procedure below includes later documentation of the repository's `addons/`
layout; it does not establish which layout was deployed on September 14.
Configuration snapshots below were copied from `deploy/headscale/` and
`deploy/gateway/` at import time. Their equality to the September 14 runtime
was not rechecked during this documentation change.
Secret values are intentionally absent. Key lifetime below is historical and
must not be treated as confirmation that the same key is still active.

## Environment Resources

| Resource | Value |
| --- | --- |
| Environment | `hr-headscale`, Odoo `19.0` |
| Git | `https://github.com/oduflow/oduflow-client-addons`, branch `19.0-headscale` |
| Module | `oduscale` |
| Administrator interface | https://hr-headscale.demo.odusfera.pl |
| Headscale | `oduscale-hs`, `ghcr.io/juanfont/headscale:0.29.3` |
| Client login server | https://oduscale-hs.demo.odusfera.pl |
| API inside Docker | `http://oduflow-1-svc-oduscale-hs:8080` |
| VPN gateway | `oduscale-gateway`, `tailscale/tailscale:v1.98.3` |
| Odoo over VPN | http://odoo.oduscale.internal or http://100.80.0.1 |

This is a demonstration environment: the public Odoo address remains available
for development and validation. Revocation in Oduscale blocks the VPN connection,
but does not by itself prevent login through the public Odoo address. For VPN-only
operation, close the public Odoo route at the ingress proxy after preparing
administrator access through the VPN.

HTTP traffic to the VPN address travels inside an encrypted Tailscale/WireGuard
connection. The gateway forwards TCP to Odoo port 8069, including websocket traffic
with the current `workers=0` setting. Multiple Odoo workers require an internal HTTP
proxy with separate routing of `/websocket` to the gevent port. Odoo login remains
mandatory.

## Recorded Reproduction Procedure

1. Publish the Git branch. Call `create_environment` with `branch=19.0-headscale`,
   `env_name=hr-headscale`, `odoo_image=odoo:19.0`, `template_name=none` and the repository URL.
   Configure the repository addon path as `/mnt/extra-addons/addons` (Oduflow
   detects the top-level `addons/` directory when generating its configuration).
   Install `oduscale` through `pull_and_apply(install="oduscale")`.
2. Create the `oduscale-config`, `oduscale-data`, `oduscale-gateway-state` and
   `oduscale-gateway-config` volumes through `create_volume`.
3. Use `write_file_in_volume` to write `headscale/config.yaml` and `headscale/policy.hujson`
   to `oduscale-config`, and `gateway/serve.json` to `oduscale-gateway-config`.
   For a different environment, replace the domains, Odoo container name and VPN ranges.
4. Create the `oduscale-hs` service using the image from the table, `command="serve"` and volumes
   `oduscale-config:/etc/headscale:ro,oduscale-data:/var/lib/headscale`.
   Supply `routes` for `/health`, `/key`, `/ts2021`, `/register`, `/auth`,
   `/oidc/callback`, `/verify` and `/machine/ping-response`, each on `port=8080`.
   Do not publish a catch-all route or `/api/v1`.
5. Run through `run_service_command(name="oduscale-hs", shell=false)`:

   ```text
   headscale users create oduscale-gateway
   headscale apikeys create --expiration 2160h
   headscale users list -o json
   headscale preauthkeys create --user <gateway-user-id> --expiration 1h --tags tag:odoo -o json
   ```

   Do not recreate the user if it already exists. Pass the API key only through
   the Odoo environment variable `ODUSCALE_API_KEY` using `update_environment`,
   preserving other variables. Its value must not appear in Git, chatter or reports.
   The demo API key is valid for 90 days from September 14, 2026. Before it expires,
   create a new key, update the Odoo variable, verify the connection and expire the
   old key with `headscale apikeys expire`.
6. Create `oduscale-gateway` using the image from the table, `port=65535` (no listener;
   the VPN port is not published) and volumes
   `oduscale-gateway-state:/var/lib/tailscale,oduscale-gateway-config:/config:ro`.
   Environment settings:

   ```text
   TS_AUTHKEY=<single-use gateway key from step 5>
   TS_AUTH_ONCE=true
   TS_STATE_DIR=/var/lib/tailscale
   TS_USERSPACE=true
   TS_HOSTNAME=odoo
   TS_EXTRA_ARGS=--login-server=https://oduscale-hs.demo.odusfera.pl --accept-dns=false
   TS_SERVE_CONFIG=/config/serve.json
   ```

   `privileged`, `NET_ADMIN` and host networking are unnecessary. With a Headscale
   preauth key, tags come from the key: do not add `--advertise-tags` to the client command.
   After registration, remove `TS_AUTHKEY` from the environment through `update_service`,
   preserving the remaining settings. The gateway identity persists in the volume.
7. In **Oduscale → Headscale Servers**, create a server with the API/login/VPN URLs
   from the table, key variable `ODUSCALE_API_KEY` and a 60-minute key lifetime.
   Click **Test connection**. Use distinct key variable names for multiple servers.
8. Create employee access and test the connection using the [Oduscale user guide](../addons/oduscale/doc/user_guide.md).

SQLite uses WAL and the persistent `oduscale-data` volume. A PostgreSQL service
database is unnecessary: upstream Headscale recommends SQLite for new installations.
Copy the database through the SQLite backup API or while Headscale is stopped;
back up private keys and configuration as well. When cloning Odoo for an independent
environment, use a separate Headscale instance and new API configuration so test
actions do not affect the original network.

## Operations

- Synchronization runs every 5 minutes; `.oduflow/odoo.conf` enables one cron thread.
- Oduflow may automatically stop an idle development environment. Before testing,
  call `start_environment(env_name="hr-headscale")`; this is not a production deployment.
- Operations return an error when Headscale is unavailable. Employee/user archiving
  is blocked if revocation cannot be confirmed. Restore the service and retry.
- Headscale requests are outside the PostgreSQL transaction. If revocation partially
  succeeds, retrying reads the actual keys and devices and completes the cleanup.
- After revocation, the Headscale user remains for auditing and reconnection;
  its keys are expired and devices deleted. Granting access again requires a new key.
- The single-use key secret is stored only in a temporary Odoo dialog until transient
  records are cleaned up (one hour plus the cleanup interval). Permanent history stores IDs and expiration.
- The Headscale API grants administrative privileges over an entire server. Do not
  connect an arbitrary shared production Headscale instance to the demo database.

## Validation on September 14, 2026

- Installation and upgrade succeeded on `Odoo 19.0-20260908`.
- 16 Odoo tests: 0 errors and 0 failures.
- A separate Tailscale process registered using a single-use key from `action_enroll`.
- Device `employee-test`, IP `100.80.0.2`, appeared online; the key was marked as used.
- `/web/login` at `100.80.0.1` returned HTTP 200 over the VPN.
- After `action_revoke`, the node disappeared from Headscale and a new connection timed out.
- External `/api/v1/user` returns 404; `/health` returns 200.
- The test client was stopped and its key revoked; the employee record remains for UI checks.

## Configuration Snapshots at Import

The following non-secret files preserve the available configuration independently
of later edits to the examples. They were read locally on 2026-09-15, not fetched
from the services. Volume ownership, Docker network name, resolved image digests,
backup locations and numeric gateway user ID were not recorded.

### deploy/headscale/config.yaml

```yaml
server_url: https://oduscale-hs.demo.odusfera.pl
listen_addr: 0.0.0.0:8080
metrics_listen_addr: 127.0.0.1:9090
grpc_listen_addr: 127.0.0.1:50443
grpc_allow_insecure: false
noise:
  private_key_path: /var/lib/headscale/noise_private.key
prefixes:
  v4: 100.80.0.0/16
  v6: fd7a:115c:a1e0:ab00::/64
  allocation: sequential
derp:
  server:
    enabled: false
  urls:
    - https://controlplane.tailscale.com/derpmap/default
  auto_update_enabled: true
  update_frequency: 3h
disable_check_updates: true
database:
  type: sqlite
  sqlite:
    path: /var/lib/headscale/db.sqlite
    write_ahead_log: true
policy:
  mode: file
  path: /etc/headscale/policy.hujson
dns:
  magic_dns: true
  base_domain: oduscale.internal
  override_local_dns: false
  nameservers:
    global: []
unix_socket: /var/lib/headscale/headscale.sock
unix_socket_permission: "0770"
log:
  level: info
```

### deploy/headscale/policy.hujson

```json
{
  "tagOwners": {"tag:odoo": ["oduscale-gateway@"]},
  "acls": [
    {"action": "accept", "src": ["autogroup:member"], "dst": ["tag:odoo:80"]}
  ]
}
```

### deploy/gateway/serve.json

```json
{
  "TCP": {
    "80": {"TCPForward": "oduflow-1-hr-headscale-odoo:8069"}
  }
}
```

## Upstream

- [Headscale 0.29.3 and API schema](https://github.com/juanfont/headscale/tree/v0.29.3)
- [Headscale configuration, including SQLite](https://github.com/juanfont/headscale/blob/v0.29.3/config-example.yaml)
- [Headscale device registration](https://headscale.net/stable/ref/registration/)
- [Tailscale 1.98.3](https://github.com/tailscale/tailscale/releases/tag/v1.98.3)

## Repository Layout Update — 2026-09-15

This record now lives in the repository-root `log/` directory. The configuration
examples moved to [addons/oduscale/deploy](../addons/oduscale/deploy/README.md).
The old paths in the import notes and snapshot headings above are preserved as
historical references; current configuration paths are
`addons/oduscale/deploy/headscale/config.yaml`,
`addons/oduscale/deploy/headscale/policy.hujson` and
`addons/oduscale/deploy/gateway/serve.json`. File contents and services were not
changed by this repository reorganization.
