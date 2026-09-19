# Oduscale User Guide

Oduscale lets access managers connect employee devices to the company VPN through
Headscale and Tailscale. VPN connectivity and Odoo permissions are independent:
employees still need their own Odoo account and must sign in.

## Before You Start

An administrator must configure a Headscale server and grant you **Oduscale / Manage
employee VPN access**. The employee and their linked Odoo user, if any, must be active.
The employee installs Tailscale on each device. The VPN policy and gateway determine
which services that device can reach.

## Grant Access and Connect a Device

1. Open **Oduscale → Employee Access** and create a record for the employee and server.
   Access records are also available on the employee form's **Oduscale** tab.
2. Save the record and click **Grant access**. Its state becomes **Active**.
3. Click **Connect a device** to issue a single-use key and display the connection command.
   The default key lifetime is 60 minutes; the dialog shows its expiration.
4. Share the command securely with that employee only. It contains a secret.
   The employee runs it in a terminal with administrator privileges on their device.
5. After connecting, open the VPN Odoo URL shown on the access record and sign in
   with the employee's Odoo account.
6. Click **Synchronize** to refresh the device list immediately. Repeat **Connect a
   device** for each additional device; each needs a new key.

**Active** means access has been granted; it does not mean a device is connected.
There can be only one access record for an employee on a given server. Once linked
to Headscale, a record cannot be reassigned or deleted; keep it for audit and revoke
access when it is no longer needed.

## Inspect Devices and Enrollment History

- Open **Devices** on the access record, or **Oduscale → Devices** for the inventory.
  Review the VPN addresses, online status, presence and last seen time. The access
  record also offers an optional device expiry column.
- A device marked absent remains in the history but is no longer found on Headscale.
  Online status is the result of the last synchronization, not a live connection test.
- **Enrollment history** shows key IDs, creation and expiration times, and used/revoked
  flags. It does not store the connection command or key secret.
- Synchronization is scheduled every 5 minutes. **Synchronize** refreshes one access
  record; the same button on a server refreshes its connections.

## Revoke Access

- In **Enrollment history**, click **Expire** to invalidate an enrollment key.
  Expiring a key does not disconnect a device that already enrolled with it.
- In **Devices**, click **Revoke** and confirm to remove one device from Headscale.
  Other devices and enrollment keys are unaffected.
- Click **Revoke all access** on the access record and confirm to expire all keys
  and remove all devices belonging to that employee's linked Headscale user.
  The record becomes **Revoked**; the remote user and local audit records remain.
- To restore access, click **Grant access**, then **Connect a device** and use a new key.

Archiving an employee or their linked Odoo user automatically revokes active VPN
access. If Headscale cannot confirm revocation, archiving fails; contact an
administrator and retry after service is restored.

## Resolve Connection Problems

- If the key expired or was already used, request a new key with **Connect a device**.
- If the device is missing from the inventory, click **Synchronize** and check whether
  the employee completed the connection command successfully.
- If the VPN connects but Odoo does not open, ask an administrator to check the VPN
  policy, gateway and configured Odoo URL. Check Odoo credentials separately.
- If an action reports a Headscale error, do not assume it completed. Ask an
  administrator to restore connectivity, then retry and synchronize.

Revoking VPN access does not block a separately exposed public Odoo address.

## Odoo 17 compatibility

Use branch `17.0` for a fresh installation on Odoo 17. Install the module from `addons` together with its declared dependencies. This branch does not downgrade an existing Odoo database.
