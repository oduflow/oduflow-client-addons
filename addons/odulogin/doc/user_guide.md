# OduLogin user guide

OduLogin helps an administrator reproduce what an internal user sees without
asking for that user's password.

## Switch from the top bar

1. Sign in with an account that has Settings administration access.
2. Select **Switch User** in the top bar.
3. Choose an active internal user and select **Switch User**.
4. Odoo reloads the current URL as the selected user. Normal access rules now
   apply to that user, so the current screen can show an access error.

## Switch from a user record

1. Open **Settings > Users & Companies > Users** and select a user.
2. Open the **Actions** menu and select **Switch User**.
3. Confirm the preselected user in the dialog.

## Return to the administrator account

Select **Return to administrator** in the top bar. Odoo reloads the same URL
with the original administrator account.

Only one switch can be active in a browser session. Return to the administrator
account before choosing another user. Portal users, inactive users, the current
administrator and the technical superuser cannot be selected.

## Odoo 17 compatibility

Use branch `17.0` for a fresh installation on Odoo 17. Install the module from `addons` together with its declared dependencies. This branch does not downgrade an existing Odoo database.
