# OduLogin

OduLogin lets an Odoo 17 settings administrator temporarily use the current
backend browser session as another active internal user. The administrator can
return to the original account from the systray without losing the current URL.

The implementation is an independent Odoo 17 module inspired by the behavior
of VelesAgro's `se_login_as_other_users` module. It uses the current OWL systray
registry and updates the complete authenticated session identity.

Install the module as `odulogin`. Run its tests with:

```sh
/path/to/odoo-bin \
  --addons-path=/path/to/odoo/addons,/path/to/oduflow-client-addons/addons \
  -d odulogin_test -i odulogin \
  --without-demo --test-enable --test-tags /odulogin \
  --stop-after-init
```
