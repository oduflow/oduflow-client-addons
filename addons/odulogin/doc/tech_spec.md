# OduLogin technical specification

## Scope

`odulogin` is an independent Odoo 16 implementation of the temporary user
switching workflow found in VelesAgro's `se_login_as_other_users` module. It
does not reuse the vendor module's JavaScript, XML, media or model names.

## Models and actions

- `odulogin.switch.wizard` is a `TransientModel` available to
  `base.group_system`. Its required `user_id` domain lists active, non-share
  users other than the current user and `base.user_root`.
- `odulogin.session` is an `AbstractModel` service. `_start(target_user)` checks
  administrator authority and the target independently of the client domain.
  `switch_back()` restores the saved identity.
- `odulogin.action_odulogin_switch_wizard` opens an empty dialog from the
  systray. `odulogin.action_odulogin_switch_from_user` is bound to `res.users`
  and supplies `active_id` as the default target.

## Session contract

The server-side session key `odulogin_origin_uid` is absent in a normal session
and contains the original administrator's user ID during a switch. A second
switch is rejected while this key exists.

Both directions replace `uid`, `login`, `context` and `session_token`. The token
is recomputed for the selected identity and the current request environment is
updated with superuser mode disabled. The session is marked for a hard ID
rotation at the end of the request. The client receives or invokes a full page
reload, preserving the current router URL.

`ir.http.session_info()` adds:

- `odulogin_can_switch`: true only for an authenticated Settings administrator;
- `odulogin_is_switched`: true when `odulogin_origin_uid` exists;
- `odulogin_origin_name`: the display name used by the return control, present
  only during a switch and read with `sudo()`.

## Client contract

The OWL component `odulogin.OduLoginSystray` is registered in the Odoo 16
`systray` registry. It opens the wizard for an administrator and calls
`odulogin.session.switch_back()` for a switched user. The component is not
loaded in portal pages because it belongs only to `web.assets_backend`.

## Security invariants

- Only a user satisfying `_is_system()` can start a switch.
- The target must exist, be active, be internal, differ from the current user
  and not be `base.user_root`.
- Returning requires `odulogin_origin_uid` in the same authenticated web
  session; the original account must still exist and be active.
- Public HTTP routes and password bypass endpoints are not provided.
- The target user's normal record rules and permissions apply after reload.

## Tests

`tests/test_odulogin.py` covers the switch and return lifecycle, session token
replacement, authorization, invalid targets, nested switching, return
preconditions, session information and the selectable-user domain.
`tests/test_http.py` verifies that the changed identity persists between real
JSON-RPC requests and that the original administrator can be restored.
