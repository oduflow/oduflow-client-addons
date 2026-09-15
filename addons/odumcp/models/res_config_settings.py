from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    odumcp_enabled = fields.Boolean(
        string="Enable MCP Connector API",
        config_parameter="odumcp.enabled",
        default=True,
    )
    odumcp_max_payload_bytes = fields.Integer(
        string="Maximum JSON Payload Bytes",
        config_parameter="odumcp.max_payload_bytes",
        default=2 * 1024 * 1024,
    )
    odumcp_max_binary_bytes = fields.Integer(
        string="Maximum Binary/Report Bytes",
        config_parameter="odumcp.max_binary_bytes",
        default=5 * 1024 * 1024,
    )
    odumcp_audit_retention_days = fields.Integer(
        string="Audit Retention (days)",
        config_parameter="odumcp.audit_retention_days",
        default=90,
    )
    odumcp_approval_retention_days = fields.Integer(
        string="Approval Retention (days)",
        config_parameter="odumcp.approval_retention_days",
        default=30,
    )
    odumcp_request_window_minutes = fields.Integer(
        string="Request Grouping Window (minutes)",
        config_parameter="odumcp.request_window_minutes",
        default=10,
        help="Plans of the same connector user and profile that arrive without an "
             "explicit batch key are grouped into one request while less than this "
             "many minutes pass between them. Zero puts every plan in its own request.",
    )
