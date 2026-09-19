# -*- encoding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ResUsers(models.Model):
    _inherit = 'res.users'

    odupilot_profile_id = fields.Many2one(
        'odupilot.profile',
        string='AI chat profile',
        groups='base.group_system',
        ondelete='set null',
    )

    @api.constrains('odupilot_profile_id', 'groups_id')
    def _check_odupilot_worktree_profile(self):
        invalid_users = self.filtered(
            lambda user: user.odupilot_profile_id.workspace_type == 'worktree'
            and not user.has_group('base.group_system'))
        if invalid_users:
            raise ValidationError(_(
                'Developer worktree profiles can only be assigned to Odoo administrators.'))
