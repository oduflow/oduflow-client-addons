from odoo import api, fields, models


class OduLoginSwitchWizard(models.TransientModel):
    _name = "odulogin.switch.wizard"
    _description = "Switch to Another User"

    user_id = fields.Many2one(
        "res.users",
        string="User",
        required=True,
        domain=lambda self: self._user_domain(),
    )

    @api.model
    def _user_domain(self):
        return [
            ("active", "=", True),
            ("share", "=", False),
            ("id", "not in", [self.env.uid, self.env.ref("base.user_root").id]),
        ]

    def action_switch(self):
        self.ensure_one()
        return self.env["odulogin.session"]._start(self.user_id)
