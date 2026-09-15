import logging
import os
from urllib.parse import urlsplit

import requests

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)


class OduscaleServer(models.Model):
    _name = "oduscale.server"
    _description = "Headscale Server"
    _check_company_auto = True

    name = fields.Char(required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company)
    api_url = fields.Char(string="API URL", required=True, help="Internal Headscale URL, without /api/v1.")
    login_url = fields.Char(string="Login URL", required=True, help="Public HTTPS control server URL for Tailscale clients.")
    odoo_url = fields.Char(string="Odoo URL", help="Odoo URL reachable through the VPN gateway.")
    api_key_env = fields.Char(default="ODUSCALE_API_KEY", required=True,
                              groups="base.group_system", help="Environment variable containing the Headscale API key.")
    key_lifetime_minutes = fields.Integer(default=60, required=True)
    connection_ids = fields.One2many("oduscale.connection", "server_id")
    last_sync = fields.Datetime(readonly=True)
    last_error = fields.Char(readonly=True)

    @api.constrains("api_url", "login_url", "odoo_url", "key_lifetime_minutes")
    def _check_configuration(self):
        for server in self:
            for value in (server.api_url, server.login_url, server.odoo_url):
                if not value:
                    continue
                url = urlsplit(value)
                if (url.scheme not in ("http", "https") or not url.hostname
                        or url.username or url.password or url.query or url.fragment):
                    raise ValidationError(_("Use an HTTP(S) URL without credentials, query or fragment."))
            if urlsplit(server.login_url).scheme != "https":
                raise ValidationError(_("The public Headscale login URL must use HTTPS."))
            if not 5 <= server.key_lifetime_minutes <= 1440:
                raise ValidationError(_("Enrollment keys must expire in 5 to 1440 minutes."))

    def _request(self, method, path, payload=None, missing_ok=False):
        self.ensure_one()
        token = os.environ.get(self.sudo().api_key_env or "", "")
        if not token:
            raise UserError(_("The Headscale API key environment variable is not configured."))
        try:
            response = requests.request(
                method, self.api_url.rstrip("/") + "/api/v1" + path,
                json=payload, headers={"Authorization": "Bearer " + token},
                timeout=(5, 20), allow_redirects=False,
            )
        except requests.RequestException:
            raise UserError(_("Headscale is unreachable. Check the service and retry.")) from None
        if missing_ok and response.status_code == 404:
            return {}
        if not 200 <= response.status_code < 300:
            # Never expose response bodies: some endpoints include enrollment keys.
            raise UserError(_("Headscale request failed (HTTP %s).", response.status_code))
        try:
            return response.json() if response.content else {}
        except ValueError:
            raise UserError(_("Headscale returned an invalid JSON response.")) from None

    def _check_manager(self):
        if not self.env.su and not self.env.user.has_group("oduscale.group_manager"):
            raise AccessError(_("Only Oduscale managers can manage VPN access."))
        self.check_access("read")

    def action_test_connection(self):
        self._check_manager()
        self.ensure_one()
        self._request("GET", "/user")
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {
            "title": _("Headscale"), "message": _("Connection successful."), "type": "success"}}

    def action_sync(self):
        self._check_manager()
        for server in self:
            server.connection_ids._sync()
            server.sudo().write({"last_sync": fields.Datetime.now(), "last_error": False})
        return True

    @api.model
    def _cron_sync(self):
        for server in self.search([]):
            try:
                with self.env.cr.savepoint():
                    connections = server.connection_ids
                    for connection in connections.filtered(lambda c: c.state == "active"):
                        employee = connection.employee_id
                        if not employee.active or (employee.user_id and not employee.user_id.active):
                            connection.action_revoke()
                    server.action_sync()
            except UserError as error:
                server.write({"last_error": str(error)})
                _logger.warning("Oduscale synchronization failed for server %s", server.id)
