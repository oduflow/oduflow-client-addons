from datetime import datetime, timedelta, timezone
import shlex

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


def remote_datetime(value):
    if not value or value.startswith("0001-"):
        return False
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)


class OduscaleConnection(models.Model):
    _name = "oduscale.connection"
    _description = "Employee VPN Access"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "employee_id"
    _check_company_auto = True

    employee_id = fields.Many2one("hr.employee", required=True, ondelete="restrict", check_company=True)
    server_id = fields.Many2one("oduscale.server", required=True, ondelete="restrict", check_company=True)
    company_id = fields.Many2one(related="server_id.company_id", store=True)
    state = fields.Selection([("draft", "Draft"), ("active", "Active"), ("revoked", "Revoked")],
                             default="draft", readonly=True, tracking=True)
    remote_user_id = fields.Char(readonly=True, copy=False)
    remote_user_name = fields.Char(readonly=True, copy=False)
    device_ids = fields.One2many("oduscale.device", "connection_id")
    key_ids = fields.One2many("oduscale.key", "connection_id")
    last_sync = fields.Datetime(readonly=True)
    odoo_url = fields.Char(related="server_id.odoo_url")

    _employee_server_unique = models.Constraint("UNIQUE(employee_id, server_id)",
                                               "This employee already has access configured on this server.")
    _remote_user_unique = models.Constraint("UNIQUE(server_id, remote_user_id)",
                                           "This Headscale user is already linked to another employee.")
    _managed_fields = {"state", "remote_user_id", "remote_user_name", "device_ids", "key_ids", "last_sync"}

    @api.model_create_multi
    def create(self, vals_list):
        if any(self._managed_fields.intersection(vals) for vals in vals_list):
            raise UserError(_("VPN state is managed by Headscale actions."))
        return super().create(vals_list)

    def write(self, vals):
        if self._managed_fields.intersection(vals):
            raise UserError(_("VPN state is managed by Headscale actions."))
        if {"employee_id", "server_id"}.intersection(vals) and any(self.mapped("remote_user_id")):
            raise UserError(_("An enrolled connection cannot be reassigned. Create a new connection instead."))
        return super().write(vals)

    def _set_remote(self, vals):
        return super().write(vals)

    def unlink(self):
        if any(self.mapped("remote_user_id")):
            raise UserError(_("Keep enrolled connections for audit. Revoke their access instead."))
        return super().unlink()

    def _check_action(self):
        self.check_access("write")
        self.server_id._check_manager()

    def _lock(self):
        # Serialize enrollment/revocation so two browser requests cannot race.
        self.env.cr.execute("SELECT id FROM oduscale_connection WHERE id IN %s FOR UPDATE", [tuple(self.ids)])
        self.invalidate_recordset()

    def action_activate(self):
        self._check_action()
        self._lock()
        for connection in self:
            employee = connection.employee_id
            if not employee.active or (employee.user_id and not employee.user_id.active):
                raise UserError(_("Activate the employee and their Odoo user before granting VPN access."))
            if not connection.remote_user_id:
                # Stable, database-specific name permits recovery after a timeout/rollback.
                uuid = self.env["ir.config_parameter"].sudo().get_param("database.uuid", "")
                if not uuid:
                    raise UserError(_("The Odoo database UUID is missing."))
                username = "oduscale-%s-%s" % (uuid.replace("-", ""), connection.id)
                users = connection.server_id._request("GET", "/user").get("users", [])
                user = next((u for u in users if u["name"] == username), None)
                if not user:
                    user = connection.server_id._request("POST", "/user", {
                        "name": username, "displayName": employee.name,
                    })["user"]
                connection._set_remote({"remote_user_id": str(user["id"]), "remote_user_name": username})
            connection._set_remote({"state": "active"})
        return True

    def action_enroll(self):
        self.ensure_one()
        self._check_action()
        self._lock()
        if self.state != "active":
            raise UserError(_("Activate access before issuing an enrollment key."))
        employee = self.employee_id
        if not employee.active or (employee.user_id and not employee.user_id.active):
            raise UserError(_("Inactive employees or Odoo users cannot enroll devices."))
        expiration = fields.Datetime.now() + timedelta(minutes=self.server_id.key_lifetime_minutes)
        key = self.server_id._request("POST", "/preauthkey", {
            "user": self.remote_user_id, "reusable": False, "ephemeral": False,
            "expiration": expiration.replace(tzinfo=timezone.utc).isoformat(), "aclTags": [],
        })["preAuthKey"]
        self.env["oduscale.key"].sudo().create({
            "connection_id": self.id, "remote_id": str(key["id"]), "expiration": expiration,
        })
        command = "tailscale up --login-server=%s --auth-key=%s" % (
            shlex.quote(self.server_id.login_url), shlex.quote(key["key"]))
        wizard = self.env["oduscale.enrollment"].create({
            "connection_id": self.id, "command": command, "expiration": expiration,
        })
        self.message_post(body=_("A single-use enrollment key was issued. Expires at %s UTC.", expiration))
        return {"type": "ir.actions.act_window", "name": _("Connect a device"),
                "res_model": "oduscale.enrollment", "res_id": wizard.id, "view_mode": "form", "target": "new"}

    def action_sync(self):
        self._check_action()
        self._sync()
        return True

    def _sync(self):
        for server in self.server_id:
            connections = self.filtered(lambda c: c.server_id == server and c.remote_user_id)
            if not connections:
                continue
            nodes = server._request("GET", "/node").get("nodes", [])
            keys = server._request("GET", "/preauthkey").get("preAuthKeys", [])
            for connection in connections:
                found = []
                for node in nodes:
                    if str((node.get("user") or {}).get("id")) != connection.remote_user_id:
                        continue
                    remote_id = str(node["id"])
                    found.append(remote_id)
                    vals = {"name": node.get("givenName") or node.get("name") or remote_id,
                            "ip_addresses": ", ".join(node.get("ipAddresses", [])),
                            "online": bool(node.get("online")), "present": True,
                            "last_seen": remote_datetime(node.get("lastSeen")),
                            "expiry": remote_datetime(node.get("expiry"))}
                    device = connection.device_ids.filtered(lambda d: d.remote_id == remote_id)
                    if device:
                        device.sudo().write(vals)
                    else:
                        self.env["oduscale.device"].sudo().create(dict(vals, connection_id=connection.id, remote_id=remote_id))
                connection.device_ids.filtered(lambda d: d.remote_id not in found).sudo().write({"present": False, "online": False})
                for key in keys:
                    if str((key.get("user") or {}).get("id")) != connection.remote_user_id:
                        continue
                    local = connection.key_ids.filtered(lambda k: k.remote_id == str(key["id"]))
                    vals = {"used": bool(key.get("used")), "expiration": remote_datetime(key.get("expiration"))}
                    if local:
                        local.sudo().write(vals)
                    else:
                        self.env["oduscale.key"].sudo().create(dict(vals, connection_id=connection.id, remote_id=str(key["id"])))
                connection._set_remote({"last_sync": fields.Datetime.now()})

    def action_revoke(self):
        self._check_action()
        self._lock()
        for connection in self:
            if connection.remote_user_id:
                # Query remote state, including keys/devices missing from the local cache.
                keys = connection.server_id._request("GET", "/preauthkey").get("preAuthKeys", [])
                for key in keys:
                    if str((key.get("user") or {}).get("id")) == connection.remote_user_id:
                        connection.server_id._request("POST", "/preauthkey/expire", {"id": str(key["id"])}, missing_ok=True)
                nodes = connection.server_id._request("GET", "/node").get("nodes", [])
                for node in nodes:
                    if str((node.get("user") or {}).get("id")) == connection.remote_user_id:
                        connection.server_id._request("DELETE", "/node/%s" % node["id"], missing_ok=True)
            connection.key_ids.sudo().write({"revoked": True})
            connection.device_ids.sudo().write({"present": False, "online": False})
            connection._set_remote({"state": "revoked"})
        return True


class OduscaleDevice(models.Model):
    _name = "oduscale.device"
    _description = "Employee VPN Device"
    _order = "online desc, name"

    connection_id = fields.Many2one("oduscale.connection", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="connection_id.company_id", store=True)
    employee_id = fields.Many2one(related="connection_id.employee_id")
    remote_id = fields.Char(required=True)
    name = fields.Char(required=True)
    ip_addresses = fields.Char()
    online = fields.Boolean()
    present = fields.Boolean(default=True)
    last_seen = fields.Datetime()
    expiry = fields.Datetime()

    _remote_unique = models.Constraint("UNIQUE(connection_id, remote_id)", "This device is already registered.")

    def action_revoke(self):
        self.check_access("read")
        for device in self:
            connection = device.connection_id
            connection._check_action()
            connection._lock()
            node = connection.server_id._request("GET", "/node/%s" % device.remote_id, missing_ok=True).get("node")
            if node:
                if str((node.get("user") or {}).get("id")) != connection.remote_user_id:
                    raise UserError(_("The device owner changed in Headscale. Synchronize before retrying."))
                connection.server_id._request("DELETE", "/node/%s" % device.remote_id, missing_ok=True)
            device.sudo().write({"present": False, "online": False})
            connection.message_post(body=_("Device access revoked: %s", device.name))
        return True


class OduscaleKey(models.Model):
    _name = "oduscale.key"
    _description = "VPN Enrollment Key Audit"
    _rec_name = "remote_id"
    _order = "id desc"

    connection_id = fields.Many2one("oduscale.connection", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="connection_id.company_id", store=True)
    remote_id = fields.Char(required=True)
    expiration = fields.Datetime()
    used = fields.Boolean()
    revoked = fields.Boolean()
    _remote_unique = models.Constraint("UNIQUE(connection_id, remote_id)", "This key is already registered.")

    def action_revoke(self):
        self.check_access("read")
        for key in self:
            key.connection_id._check_action()
            key.connection_id._lock()
            key.connection_id.server_id._request("POST", "/preauthkey/expire", {"id": key.remote_id}, missing_ok=True)
            key.sudo().write({"revoked": True})
        return True
