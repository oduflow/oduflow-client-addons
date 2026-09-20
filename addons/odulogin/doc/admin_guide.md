# OduLogin administrator guide

## Installation and access

Install **OduLogin** from Apps. The module has no configuration menu. The
switching controls are available only to users in `base.group_system`, the
standard Settings administration group.

Targets are limited to active internal users. OduLogin deliberately excludes
portal users and the technical superuser because the return control is a
backend systray component and impersonating the technical account would cross
a privilege boundary.

## Security and operations

The original administrator ID is stored only in the server-side Odoo session.
Starting or ending a switch updates the session user ID, login, context and
session token, rotates the session ID, then reloads the current URL. Nested
switching is blocked.

Actions performed while switched are attributed to the selected user. Use this
feature for support and access diagnosis, return promptly to the administrator
account, and do not use it to conceal the real operator. OduLogin does not add
a separate persistent audit model; retain the usual Odoo and reverse-proxy logs
according to your audit policy.

Removing Settings administration access during an active switch does not stop
the original operator from returning to their own active account. If that
account is deactivated, the return attempt is rejected and the operator must
sign out and authenticate with another account.

## Odoo 17 compatibility

Use branch `17.0` for a fresh installation on Odoo 17. Install the module from `addons` together with its declared dependencies. This branch does not downgrade an existing Odoo database.
