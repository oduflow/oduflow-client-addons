# Oduscale Administrator Guide

Oduscale manages access on an existing Headscale server. Deploy the control server,
VPN policy and Odoo gateway separately before enrolling employees.

## Install and Assign Permissions

Add the repository's `addons/` directory to `addons_path` and install `oduscale`.
Dependencies are `hr`, `mail` and the Python package `requests`. Install `odubook`
to display this documentation in Odoo; it is optional for VPN management.

Grant responsible users **Oduscale / Manage employee VPN access**. This role also
implies HR officer access. Settings administrators inherit the Oduscale role.
Managers can manage employee access and read server configuration; only Settings
administrators can create or edit servers and see the API key variable name.
Company rules restrict servers, connections, devices and key history to the user's
allowed companies. Employees and servers on a connection must belong to compatible
companies.

## Configure a Headscale Server

Open **Oduscale → Headscale Servers**, create a server and configure these fields:

| Field | Purpose |
| --- | --- |
| Name / Company | Identify the server and its owning company. |
| API URL | Headscale address reachable by Odoo, without `/api/v1`. |
| API Key Env | Environment variable containing the API token; default `ODUSCALE_API_KEY`. |
| Login URL | Public HTTPS control server URL reachable by Tailscale clients. |
| Odoo URL | Optional Odoo address reachable through the VPN gateway. |
| Key Lifetime Minutes | Single-use enrollment validity, 5–1440 minutes; default 60. |

URLs must use HTTP(S) and must not contain credentials, a query or a fragment.
The login URL specifically requires HTTPS. Put the API token in the Odoo process
environment, not in the server record, and use separate variable names for different
servers. Click **Test connection** to verify access to the Headscale user API.
This does not test the client VPN route or the Odoo gateway.

## Operate and Recover

- The scheduled action **Oduscale: synchronize employee devices** runs every 5 minutes
  as the system user. Ensure Odoo cron processing is enabled.
- Review **Last Sync** and **Last Error** on the server. A handled synchronization
  failure records an error; a successful server synchronization clears it.
- Use **Synchronize** on the server for all its connections. The scheduled action
  also revokes active access for archived employees or archived linked users.
- Headscale requests are outside the Odoo database transaction. A failed operation
  may have partially changed remote state. Restore service and retry; full revocation
  reads the remote keys and devices again, including resources absent from the local cache.
- Archiving an employee or linked user fails if revocation fails. Resolve the
  Headscale error and repeat the archive operation.
- Rotate the API token in the Odoo environment before expiration and verify it with
  **Test connection**. Keep API tokens and enrollment commands out of Git and reports.

## Secrets and Access Boundaries

Enrollment keys are single-use and create persistent devices. Their expiration is
an enrollment deadline, not a session timeout. Expire a key to stop enrollment;
revoke a device or all access to remove existing VPN connections.

The enrollment dialog holds the command secret in a temporary record configured
for a one-hour lifetime, with deletion performed by Odoo's transient cleanup.
Closing the dialog does not immediately delete that record. Permanent key history
stores identifiers and status, not secrets. HTTP error responses are redacted.

VPN policy and the gateway control reachable services. Odoo authentication remains
required, and revocation cannot close a public Odoo route. For independent cloned
environments, use a separate Headscale server and API configuration to avoid
changing the original network.

## Deploy Services in Oduflow

Use the [service configuration examples](https://github.com/oduflow/oduflow-client-addons/tree/19.0-headscale/addons/oduscale/deploy)
as a starting point. They contain demo-specific values: select your environment,
service names, public control-server domain, VPN prefixes and DNS domain first.
Record actual values, tool arguments, image versions and results in the
[deployment journal](https://github.com/oduflow/oduflow-client-addons/tree/19.0-headscale/log).
The journal contains historical observations, not a live environment inventory.

1. Publish the chosen Git branch and use `create_environment` with your repository,
   branch, environment name, `odoo_image="odoo:18.0"` and `template_name="none"`
   for a fresh database. For an existing environment, preserve its database.
   Ensure `/mnt/extra-addons/addons` is on the addon path. Use `pull_and_apply`
   with `install="oduscale"` for the first installation or `upgrade="oduscale"`
   for module updates. Enable a cron thread in `.oduflow/odoo.conf`.
2. Choose and record explicit Headscale and Tailscale image versions. Create four
   volumes with `create_volume`: Headscale configuration, Headscale data, gateway
   state and gateway configuration. Use distinct names for independent deployments.
3. Adapt `addons/oduscale/deploy/headscale/config.yaml`: set the public HTTPS server URL, VPN
   prefixes and MagicDNS domain. Adapt `addons/oduscale/deploy/headscale/policy.hujson`: its gateway
   user owns `tag:odoo`, and members can reach that tag on port 80. Adapt
   `addons/oduscale/deploy/gateway/serve.json` to forward port 80 to your Odoo container on port 8069.
   Use `write_file_in_volume` to place `config.yaml` and `policy.hujson` at the root
   of the Headscale configuration volume and `serve.json` at the root of the
   gateway configuration volume.
4. Use `create_service` for Headscale with `command="serve"`. Mount configuration
   at `/etc/headscale:ro` and data at `/var/lib/headscale`. Publish only `/health`,
   `/key`, `/ts2021`, `/register`, `/auth`, `/oidc/callback`, `/verify` and
   `/machine/ping-response` on port 8080. Do not publish a catch-all route or
   `/api/v1`. Odoo must reach the API using the internal service hostname.
5. Through `run_service_command` with `shell=false`, create the gateway user if
   absent, issue an API key, list users to obtain the gateway user ID, and issue
   a gateway preauth key tagged `tag:odoo`. Substitute your gateway user and ID:

   ```text
   headscale users create <gateway-user>
   headscale apikeys create --expiration 2160h
   headscale users list -o json
   headscale preauthkeys create --user <gateway-user-id> --expiration 1h --tags tag:odoo -o json
   ```

   Put the API key into the Odoo environment variable `ODUSCALE_API_KEY` using
   `update_environment`, preserving other variables. Record its expiration, never
   its value. Before expiry, issue a replacement, update the variable, verify
   **Test connection**, and expire the old key with `headscale apikeys expire`.
6. Use `create_service` for the Tailscale gateway. Mount state at `/var/lib/tailscale`
   and configuration at `/config:ro`. The demo uses `port=65535` with no listener
   to avoid exposing the VPN forwarder publicly. Configure these variables,
   substituting the single-use key and public control-server URL:

   ```text
   TS_AUTHKEY=<single-use-gateway-key>
   TS_AUTH_ONCE=true
   TS_STATE_DIR=/var/lib/tailscale
   TS_USERSPACE=true
   TS_HOSTNAME=odoo
   TS_EXTRA_ARGS=--login-server=<public-headscale-https-url> --accept-dns=false
   TS_SERVE_CONFIG=/config/serve.json
   ```

   This userspace setup needs no privileged container, `NET_ADMIN` or host networking.
   Tags come from the preauth key; do not add `--advertise-tags`. After registration,
   remove `TS_AUTHKEY` using `update_service`, preserving other settings. The
   gateway identity remains in its state volume.
7. Configure the Odoo Headscale server as described above: internal API URL,
   public Login URL and VPN Odoo URL. Run **Test connection**, then follow the
   [user guide](user_guide.md) to enroll a temporary device, synchronize it, open
   Odoo through the VPN and verify revocation. Check that public `/api/v1/user`
   is inaccessible and `/health` succeeds. Record actual results and remove test
   devices and keys. Start an idle environment with `start_environment` if needed.

## Gateway Routing and Backups

The example gateway forwards TCP port 80 through the encrypted VPN to Odoo port
8069. With `workers=0`, this also carries websocket traffic. Multiple workers
require an internal HTTP proxy routing `/websocket` to the gevent port.
For VPN-only access, prepare and verify administrator access through the VPN
before closing the public Odoo route at the ingress proxy.

The example Headscale service uses SQLite with WAL in its persistent data volume;
it needs no separate PostgreSQL service. Back up SQLite through its backup API or
while Headscale is stopped, and preserve private keys and configuration. Back up
the gateway state and configuration as well as Odoo's database and filestore.
Record backup references and recovery steps before service changes; do not put
private keys or backup credentials in the journal. Use a separate Headscale
instance for independent Odoo clones so their actions cannot alter the original VPN.

## Odoo 18 compatibility

Use branch `18.0` for a fresh installation on Odoo 18. Install the module from `addons` together with its declared dependencies. This branch does not downgrade an existing Odoo database.
