from odoo import api, models, _
from odoo.exceptions import AccessError, ValidationError


class DiscussChannelMember(models.Model):
    _inherit = 'discuss.channel.member'

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            channel = self.env['discuss.channel'].browse(values.get('channel_id'))
            session = channel.sudo()._odupilot_session() if channel else False
            if not session:
                continue
            session.with_user(self.env.user)._check_membership_manager()
            user = self.env['res.users'].sudo().search([
                ('partner_id', '=', values.get('partner_id')),
                ('share', '=', False), ('active', '=', True),
            ], limit=1)
            if values.get('guest_id') or not user:
                raise ValidationError(_('Only active internal Odoo users can be invited to an AI chat.'))
            if session.profile_id.workspace_type == 'worktree' and not user.has_group('base.group_system'):
                raise AccessError(_('Only Odoo administrators can join a developer worktree chat.'))
        return super().create(vals_list)

    def unlink(self):
        bot = self.env.ref('odupilot.partner_ai_bot')
        for member in self:
            session = member.channel_id.sudo()._odupilot_session()
            if not session or session.state == 'closed':
                continue
            if member.partner_id == bot:
                raise ValidationError(_('The AI bot cannot leave an active AI chat.'))
            session = session.with_user(self.env.user)
            if member.partner_id == session.user_id.partner_id:
                if member.partner_id != self.env.user.partner_id:
                    raise ValidationError(_('The session owner cannot be removed from an active AI chat.'))
                session.action_close()
            elif member.partner_id != self.env.user.partner_id:
                session._check_membership_manager()
        return super().unlink()

    def write(self, values):
        if {'partner_id', 'guest_id', 'channel_id'} & values.keys():
            if any(member.channel_id.sudo()._odupilot_session() for member in self):
                raise ValidationError(_('Leave or invite a member instead of changing their identity.'))
        return super().write(values)
