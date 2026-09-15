# -*- encoding: utf-8 -*-
from odoo import fields, models


class AiChatEvent(models.Model):
    _name = 'odupilot.event'
    _description = 'OduPilot Audit Event'
    _order = 'id desc'

    session_id = fields.Many2one(
        'odupilot.session', required=True, ondelete='cascade', index=True)
    event_type = fields.Char(required=True, index=True)
    payload = fields.Text(required=True, default='{}')
    external_id = fields.Char(required=True, index=True)
    actor_user_id = fields.Many2one(
        'res.users', string='Actual actor', ondelete='set null', index=True)
    execution_user_id = fields.Many2one(
        'res.users', string='Execution identity', required=True,
        ondelete='restrict', index=True)
    mail_message_id = fields.Many2one(
        'mail.message', ondelete='set null', index=True)

    _odupilot_event_external_unique = models.Constraint('unique(session_id, external_id)', 'This AI chat event has already been ingested.')
