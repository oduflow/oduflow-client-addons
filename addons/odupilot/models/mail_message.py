# -*- encoding: utf-8 -*-
from odoo import models, fields


class MailMessage(models.Model):
    _inherit = 'mail.message'

    odupilot_is_answer = fields.Boolean(
        string='OduPilot Answer',
        help='Set on the AI chat message that carries the answer itself. '
             'Steps with reasoning or tool calls only are not marked.',
        default=False,
    )
    odupilot_is_request = fields.Boolean(
        string='OduPilot Request',
        help='Set on the AI chat message that asks the user for a decision, '
             'such as a permission or a recovery request.',
        default=False,
    )

    def message_format(self, format_reply=True, **kwargs):
        values = super().message_format(format_reply=format_reply, **kwargs)
        permissions = self.env['odupilot.permission'].sudo().search([
            ('mail_message_id', 'in', self.ids),
        ])
        permissions_by_message = {
            permission.mail_message_id.id: permission
            for permission in permissions
            if permission.mail_message_id
        }
        recoveries = self.env['odupilot.recovery'].sudo().search([
            ('mail_message_id', 'in', self.ids),
        ])
        recoveries_by_message = {
            recovery.mail_message_id.id: recovery
            for recovery in recoveries
            if recovery.mail_message_id
        }
        current_partner = self.env.user.partner_id
        is_admin = self.env.user.has_group('base.group_system')
        # Ход агента приезжает несколькими сообщениями: рассуждения и вызовы
        # инструментов идут отдельными шагами, и ответом считается только шаг
        # с текстом. Клиенту признак нужен, чтобы липкое уведомление и
        # докированное окно поднимал ответ или адресованный человеку вопрос, а
        # не каждый служебный шаг.
        attention_ids = set(self.sudo().filtered(
            lambda message: message.odupilot_is_answer
            or message.odupilot_is_request).ids)
        bot = self.env.ref('odupilot.partner_ai_bot', raise_if_not_found=False)
        bot_message_ids = set(self.sudo().filtered(lambda message: message.author_id == bot).ids) if bot else set()
        for item in values:
            if item['id'] in attention_ids:
                item['odupilot_assistant'] = True
            elif item['id'] in bot_message_ids:
                # Служебный шаг агента: клиент по этому признаку не поднимает
                # ни докированное окно, ни уведомление вне фокуса.
                item['odupilot_step'] = True
            permission = permissions_by_message.get(item['id'])
            if permission:
                if (is_admin or current_partner in
                        permission.session_id.channel_id.channel_partner_ids):
                    item['odupilot_permission'] = (
                        permission._format_for_client())
            recovery = recoveries_by_message.get(item['id'])
            if recovery:
                if (is_admin or current_partner in
                        recovery.session_id.channel_id.channel_partner_ids):
                    item['odupilot_recovery'] = recovery._format_for_client()
        return values

