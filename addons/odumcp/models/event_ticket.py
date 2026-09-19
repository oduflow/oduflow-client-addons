import hashlib
import secrets

from odoo import api, fields, models


class OduMcpEventTicket(models.Model):
    _name = "odumcp.event.ticket"
    _description = "MCP Event Ticket"
    _order = "create_date desc"

    token_hash = fields.Char(required=True, readonly=True, index=True)
    user_id = fields.Many2one(
        "res.users",
        required=True,
        readonly=True,
        ondelete="cascade",
        index=True,
    )
    expires_at = fields.Datetime(required=True, readonly=True, index=True)
    _sql_constraints = [('token_hash_unique', 'UNIQUE(token_hash)', 'The MCP event ticket must be unique.')]

    @api.model
    def _ttl_seconds(self):
        value = self.env["ir.config_parameter"].sudo().get_param(
            "odumcp.event_ticket_ttl_seconds",
            "600",
        )
        return min(max(int(value), 60), 3600)

    @api.model
    def _issue(self, user):
        token = secrets.token_urlsafe(32)
        now = fields.Datetime.now()
        self.sudo().create(
            {
                "token_hash": self._digest(token),
                "user_id": user.id,
                "expires_at": fields.Datetime.add(now, seconds=self._ttl_seconds()),
            }
        )
        return token

    @api.model
    def _check(self, token):
        if not isinstance(token, str) or not token:
            return self.browse()
        now = fields.Datetime.now()
        ticket = self.sudo().search(
            [
                ("token_hash", "=", self._digest(token)),
                ("expires_at", ">=", now),
            ],
            limit=1,
        )
        user = ticket.user_id
        if (
            not ticket
            or not user.active
            or not user.mcp_active
            or not user.mcp_profile_id.active
        ):
            return self.browse()
        return ticket

    @staticmethod
    def _digest(token):
        return hashlib.sha256(token.encode()).hexdigest()

    @api.autovacuum
    def _gc_event_tickets(self):
        self.sudo().search([("expires_at", "<", fields.Datetime.now())], limit=5000).unlink()
