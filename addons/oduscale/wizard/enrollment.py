from odoo import fields, models


class OduscaleEnrollment(models.TransientModel):
    _name = "oduscale.enrollment"
    _description = "Connect an Employee Device"
    _transient_max_hours = 1

    connection_id = fields.Many2one("oduscale.connection", required=True, readonly=True)
    command = fields.Text(readonly=True, groups="oduscale.group_manager")
    expiration = fields.Datetime(readonly=True)
