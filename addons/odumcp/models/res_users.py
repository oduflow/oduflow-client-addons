import uuid

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResUsers(models.Model):
    _inherit = "res.users"

    mcp_active = fields.Boolean(string="MCP Active", default=False)
    mcp_profile_id = fields.Many2one(
        "odumcp.profile",
        string="Profile",
        ondelete="restrict",
        domain=[("active", "=", True)],
        index=True,
    )
    mcp_event_channel = fields.Char(
        readonly=True,
        copy=False,
        default=lambda self: "odumcp_%s" % uuid.uuid4().hex,
        groups="odumcp.group_mcp_manager",
    )
    mcp_event_version = fields.Integer(readonly=True, copy=False, default=0)

    def init(self):
        super().init()
        self.env.cr.execute(
            """
            SELECT to_regclass('odumcp_credential') IS NOT NULL
                OR EXISTS (
                    SELECT 1 FROM ir_model WHERE model = 'odumcp.credential'
                )
            """
        )
        if self.env.cr.fetchone()[0]:
            raise ValidationError(
                _(
                    "Unsupported odumcp database detected: the obsolete "
                    "odumcp_credential table exists. Install this version on a fresh database."
                )
            )

    @api.constrains("mcp_active", "mcp_profile_id")
    def _check_mcp_profile(self):
        for user in self:
            if user.mcp_active and not user.mcp_profile_id:
                raise ValidationError(_("Select an MCP profile before enabling MCP access."))

    @api.model
    def _mcp_for_user(self, user):
        mcp_user = self.sudo().with_context(active_test=False).browse(user.id).exists()
        if not mcp_user or not mcp_user.mcp_profile_id:
            return self.browse(), "mcp_access_not_configured"
        if not mcp_user.active or not mcp_user.mcp_active or not mcp_user.mcp_profile_id.active:
            return self.browse(), "inactive_mcp_access"
        if not mcp_user.mcp_event_channel:
            mcp_user.mcp_event_channel = "odumcp_%s" % uuid.uuid4().hex
        return mcp_user, False

    def _check_mcp_quota(self):
        self.ensure_one()
        now = fields.Datetime.now()
        minute_start = fields.Datetime.subtract(now, minutes=1)
        audit_model = self.env["odumcp.audit.log"].sudo()
        minute_count = audit_model.search_count(
            [("user_id", "=", self.id), ("create_date", ">=", minute_start)]
        )
        if minute_count >= self.mcp_profile_id.rate_limit_per_minute:
            return "rate_limit_exceeded"
        if self.mcp_profile_id.daily_quota:
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            daily_count = audit_model.search_count(
                [("user_id", "=", self.id), ("create_date", ">=", day_start)]
            )
            if daily_count >= self.mcp_profile_id.daily_quota:
                return "daily_quota_exceeded"
        return False

    def _publish_mcp_resource_update(self, uri):
        self.ensure_one()
        if not self.mcp_event_channel:
            self.sudo().mcp_event_channel = "odumcp_%s" % uuid.uuid4().hex
        if not isinstance(uri, str) or not uri.startswith("odoo://"):
            raise ValidationError(_("MCP event resources must use an odoo:// URI."))
        self.env.cr.execute(
            """
            UPDATE res_users
               SET mcp_event_version = mcp_event_version + 1
             WHERE id = %s
         RETURNING mcp_event_version
            """,
            (self.id,),
        )
        version = self.env.cr.fetchone()[0]
        self.invalidate_recordset(["mcp_event_version"])
        self.env["bus.bus"]._sendone(
            self.mcp_event_channel,
            "odumcp_resource_updated",
            {
                "type": "resource.updated",
                "uri": uri,
                "version": version,
            },
        )
        return version
