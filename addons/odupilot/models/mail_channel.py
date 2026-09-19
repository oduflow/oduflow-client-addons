# -*- encoding: utf-8 -*-
import base64
import json
import re
import uuid

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import file_open, html2plaintext


class MailChannel(models.Model):
    _inherit = 'mail.channel'

    # Отдельная категория sidebar в Discuss опирается на признак канала, а не
    # на наличие odupilot.session: сессию можно закрыть или удалить, а канал с
    # перепиской остаётся и должен оставаться в группе AI.
    is_odupilot = fields.Boolean(
        string='Is OduPilot',
        default=False,
        help='Channel of an AI chat session, shown in the AI sidebar category.')

    @api.model
    def _odupilot_default_avatar(self):
        """Вернуть портрет для AI-каналов в боковой панели Discuss."""
        with file_open(
                'odupilot/static/src/img/ai_channel_avatar.png', 'rb') as source:
            return base64.b64encode(source.read())

    def _odupilot_session(self):
        self.ensure_one()
        return self.env['odupilot.session'].search([
            ('channel_id', '=', self.id),
        ], limit=1)

    def channel_rename(self, name):
        self.ensure_one()
        session = self._odupilot_session()
        result = super().channel_rename(name)
        if session and not session.is_ask_session:
            # Ручное имя имеет приоритет над отложенным заголовком из первого
            # ответа модели: ответ мог прийти уже после RPC переименования.
            session.sudo().write({'title_auto_set': True})
            session._audit_event(
                'session.title.renamed',
                {'title': name},
                self.env.user,
            )
        return result

    def channel_info(self):
        self.check_access_rights("read")
        self.check_access_rule("read")
        return self._odupilot_channel_info()

    def _odupilot_channel_info(self):
        infos = super().channel_info()
        sessions = self.env['odupilot.session'].sudo().search([
            ('channel_id', 'in', self.ids),
        ])
        sessions_by_channel = {
            session.channel_id.id: session
            for session in sessions
        }
        channels = {channel.id: channel for channel in self}
        for info in infos:
            channel = channels.get(info['id'])
            info['is_odupilot'] = bool(channel and channel.is_odupilot)
            session = sessions_by_channel.get(info['id'])
            if session:
                status = session._format_status_for_client()
                info['odupilot_session'] = status
                if status['discuss_only']:
                    # Разработческая сессия живёт только в Discuss. Старое
                    # fold-state не должно превращать её в docked-окно после
                    # возврата пользователя в главное меню.
                    info['is_minimized'] = False
                    info['state'] = 'closed'
        return infos

    def _get_message_create_valid_field_names(self):
        return super()._get_message_create_valid_field_names() | {'odupilot_is_answer', 'odupilot_is_request'}

    def message_post(self, *, message_type='notification', **kwargs):
        message = super().message_post(
            message_type=message_type, **kwargs)
        if self.env.context.get('odupilot_skip_enqueue'):
            return message
        session = self._odupilot_session()
        if not session or message.message_type != 'comment':
            return message
        if session.state == 'closed':
            return message
        bot = self.env.ref('odupilot.partner_ai_bot')
        if message.author_id == bot:
            return message
        actor = self.env['res.users'].sudo().search([
            ('partner_id', '=', message.author_id.id),
            ('share', '=', False),
            ('active', '=', True),
        ], limit=1)
        if not actor:
            return message
        human_users = self.env['res.users'].sudo().search([
            ('partner_id', 'in', self.channel_partner_ids.ids),
            ('share', '=', False),
            ('active', '=', True),
        ])
        routed = len(human_users) == 1 or bot in message.partner_ids
        if not routed:
            return message
        session._check_actor(actor)
        text = html2plaintext(message.body or '').strip()
        bot_name = re.escape(bot.name)
        command_text = re.sub(
            r'^\s*@%s[\s,:-]*' % bot_name,
            '', text, count=1, flags=re.IGNORECASE).strip()
        if command_text.lower() == '/abort':
            session.enqueue_abort(message, actor)
        else:
            session.enqueue_prompt(message, actor)
        return message

    def add_members(self, partner_ids=None, guest_ids=None, **kwargs):
        partners = self.env['res.partner'].browse(partner_ids or [])
        guests = self.env['mail.guest'].browse(guest_ids or [])
        users = self.env['res.users']
        partners = (partners or self.env['res.partner']) | (users or self.env['res.users']).partner_id
        partner_ids = partners.ids
        guest_ids = guests.ids if guests else []
        sessions = {
            channel.id: channel._odupilot_session()
            for channel in self
        }
        previous = {
            channel.id: set(channel.channel_partner_ids.ids)
            for channel in self if sessions[channel.id]
        }
        partners = self.env['res.partner'].sudo().browse(
            partner_ids or []).exists()
        for channel in self:
            session = sessions[channel.id]
            if not session:
                continue
            session._check_membership_manager()
            if guest_ids:
                raise UserError(_(
                    'Guests cannot be invited to an AI chat.'))
            users = self.env['res.users'].sudo().search([
                ('partner_id', 'in', partners.ids),
                ('share', '=', False),
                ('active', '=', True),
            ])
            if set(users.partner_id.ids) != set(partners.ids):
                raise UserError(_(
                    'Only active internal Odoo users can be invited to an AI chat.'))
            if session.profile_id.workspace_type == 'worktree':
                invalid_users = users.filtered(
                    lambda user: not user.has_group('base.group_system'))
                if invalid_users:
                    raise AccessError(_(
                        'Only Odoo administrators can join a developer worktree chat.'))
        result = super().add_members(partner_ids=partners.ids, guest_ids=guests.ids, **kwargs)
        for channel in self:
            session = sessions[channel.id]
            if not session:
                continue
            added = set(channel.channel_partner_ids.ids) - previous[channel.id]
            for partner in self.env['res.partner'].sudo().browse(list(added)):
                session._audit_event(
                    'member.invited',
                    {'partner_id': partner.id, 'partner_name': partner.name},
                    self.env.user,
                    'membership:add:%s' % uuid.uuid4().hex,
                )
        return result

    def _action_remove_members(self, partners):
        sessions = {
            channel.id: channel._odupilot_session()
            for channel in self
        }
        bot = self.env.ref('odupilot.partner_ai_bot')
        for channel in self:
            session = sessions[channel.id]
            if not session:
                continue
            session._check_membership_manager()
            protected = bot | session.user_id.partner_id
            if partners & protected:
                raise ValidationError(_(
                    'The AI bot and session owner cannot be removed from an active AI chat.'))
        result = self.channel_member_ids.filtered(lambda member: member.partner_id in partners).unlink()
        for channel in self:
            session = sessions[channel.id]
            if not session:
                continue
            for partner in partners:
                session._audit_event(
                    'member.removed',
                    {'partner_id': partner.id, 'partner_name': partner.name},
                    self.env.user,
                    'membership:remove:%s' % uuid.uuid4().hex,
                )
        return result

    def _action_unfollow(self, partner=None, guest=None, **kwargs):
        partner = partner or self.env.user.partner_id
        for channel in self:
            session = channel._odupilot_session()
            if not session:
                continue
            bot = self.env.ref('odupilot.partner_ai_bot')
            if partner == bot and session.state != 'closed':
                raise ValidationError(_(
                    'The AI bot cannot leave an active AI chat.'))
            if partner == session.user_id.partner_id:
                session.action_close()
            elif partner != self.env.user.partner_id:
                session._check_membership_manager()
        return super(MailChannel, self.with_context(
            odupilot_membership_allowed=True))._action_unfollow(partner)

    def write(self, values):
        if ('channel_partner_ids' not in values
                or self.env.context.get('odupilot_membership_allowed')):
            return super().write(values)
        sessions = {
            channel.id: channel._odupilot_session()
            for channel in self
        }
        previous = {
            channel.id: set(channel.channel_partner_ids.ids)
            for channel in self if sessions[channel.id]
        }
        for channel in self:
            session = sessions[channel.id]
            if session:
                session._check_membership_manager()
        result = super().write(values)
        bot = self.env.ref('odupilot.partner_ai_bot')
        for channel in self:
            session = sessions[channel.id]
            if not session:
                continue
            current = set(channel.channel_partner_ids.ids)
            if bot.id not in current or session.user_id.partner_id.id not in current:
                raise ValidationError(_(
                    'The AI bot and session owner must remain members of an active AI chat.'))
            for partner_id in current - previous[channel.id]:
                session._audit_event(
                    'member.invited', {'partner_id': partner_id}, self.env.user,
                    'membership:add:%s' % uuid.uuid4().hex)
            for partner_id in previous[channel.id] - current:
                session._audit_event(
                    'member.removed', {'partner_id': partner_id}, self.env.user,
                    'membership:remove:%s' % uuid.uuid4().hex)
        return result
