# -*- encoding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AiChatAskWizard(models.TransientModel):
    _name = 'odupilot.ask.wizard'
    _description = 'Ask AI About a Record'

    res_model = fields.Char(string='Record model', required=True, readonly=True)
    res_id = fields.Integer(string='Record ID', required=True, readonly=True)
    record_name = fields.Char(
        string='Record', compute='_compute_record_name', readonly=True)
    question = fields.Text(string='Question', required=True)

    @api.depends('res_model', 'res_id')
    def _compute_record_name(self):
        for wizard in self:
            record = wizard._record()
            wizard.record_name = record.display_name if record else False

    def _record(self):
        """Запись из чаттера, если о ней вообще можно спросить."""
        self.ensure_one()
        if not self.res_model or not self.res_id:
            return False
        if self.res_model not in self.env:
            return False
        record = self.env[self.res_model].browse(self.res_id).exists()
        # Ответ возвращается заметкой, поэтому запись без чаттера бессмысленна.
        if not record or not hasattr(record, 'message_post'):
            return False
        return record

    def action_ask(self):
        self.ensure_one()
        record = self._record()
        if not record:
            raise UserError(_('This record cannot be discussed with AI.'))
        # Вопрос ложится обычной заметкой, поэтому нужны те же права, что у
        # кнопки «Log note»: проверяем их до создания сессии, чтобы отказ был
        # штатной ошибкой доступа, а не последствием половины работы.
        record.check_access('write')
        record.check_access('write')
        question = (self.question or '').strip()
        if not question:
            raise UserError(_('Write a question first.'))
        session = self.env['odupilot.session']._ask_session()
        # Вопрос ложится заметкой сразу: пользователь видит, что запрос ушёл,
        # а ответ через минуты подшивается в эту же заметку.
        note = record.message_post(
            body=session._ask_question_html(question),
            message_type='comment',
            subtype_xmlid='mail.mt_note',
        )
        session.enqueue_prompt(note, self.env.user, origin=record)
        return {'type': 'ir.actions.act_window_close'}
