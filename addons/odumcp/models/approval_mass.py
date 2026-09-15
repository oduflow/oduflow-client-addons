from odoo import _, api, fields, models
from odoo.exceptions import AccessError


class OduMcpApprovalMass(models.TransientModel):
    _name = "odumcp.approval.mass"
    _description = "MCP Mass Approve/Reject"

    mode = fields.Selection(
        [("approve", "Approve"), ("reject", "Reject"), ("delete", "Delete Expired")],
        required=True,
        readonly=True,
    )
    approval_ids = fields.Many2many(
        "odumcp.approval",
        string="Change Plans",
        readonly=True,
    )
    eligible_count = fields.Integer(
        string="Plans to Process",
        compute="_compute_eligible_count",
    )
    skipped_count = fields.Integer(string="Skipped Records", readonly=True)

    @api.depends("approval_ids")
    def _compute_eligible_count(self):
        for wizard in self:
            wizard.eligible_count = len(wizard.approval_ids)

    def action_confirm(self):
        self.ensure_one()
        if not self.env.user._has_group("odumcp.group_mcp_manager"):
            raise AccessError(_("Only MCP managers can approve or reject change plans."))
        self.approval_ids._mass_moderate(self.mode)
