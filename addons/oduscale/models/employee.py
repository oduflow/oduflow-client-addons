from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    oduscale_connection_ids = fields.One2many("oduscale.connection", "employee_id", groups="oduscale.group_manager")

    def write(self, vals):
        result = super().write(vals)
        if vals.get("active") is False:
            self.env["oduscale.connection"].sudo().search([
                ("employee_id", "in", self.ids), ("state", "=", "active"),
            ]).action_revoke()
        return result


class ResUsers(models.Model):
    _inherit = "res.users"

    def write(self, vals):
        result = super().write(vals)
        if vals.get("active") is False:
            self.env["oduscale.connection"].sudo().search([
                ("employee_id.user_id", "in", self.ids), ("state", "=", "active"),
            ]).action_revoke()
        return result
