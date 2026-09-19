# -*- encoding: utf-8 -*-
import hashlib
import json

from odoo import fields, models, _
from odoo.exceptions import UserError, ValidationError


class AiChatRecovery(models.Model):
    _name = 'odupilot.recovery'
    _description = 'OduPilot Recovery Decision'
    _order = 'id desc'

    session_id = fields.Many2one(
        'odupilot.session', required=True, ondelete='cascade', index=True)
    failed_command_id = fields.Many2one(
        'odupilot.command', required=True, ondelete='cascade', index=True)
    abort_command_id = fields.Many2one(
        'odupilot.command', ondelete='set null', index=True)
    retry_command_id = fields.Many2one(
        'odupilot.command', ondelete='set null', index=True)
    mail_message_id = fields.Many2one(
        'mail.message', ondelete='set null', index=True)
    status = fields.Selection([
        ('pending', 'Waiting for decision'),
        ('auto_retrying', 'Retrying automatically'),
        ('retrying', 'Retrying'),
        ('dismissed', 'Dismissed'),
        ('completed', 'Completed'),
        ('expired', 'Expired'),
    ], required=True, default='pending', index=True)
    reason = fields.Text(required=True)
    had_tool_activity = fields.Boolean(
        string='Tool activity detected', readonly=True)
    resolved_by_id = fields.Many2one(
        'res.users', string='Answered by', ondelete='set null', index=True)
    resolved_at = fields.Datetime(copy=False)

    _sql_constraints = [('odupilot_recovery_failed_command_unique', 'unique(failed_command_id)', 'A recovery decision already exists for this AI request.')]

    def _format_for_client(self):
        self.ensure_one()
        status_labels = dict(
            self._fields['status']._description_selection(self.env))
        return {
            'id': self.id,
            'status': self.status,
            'status_label': status_labels.get(self.status, self.status),
            'reason': self.reason,
            'had_tool_activity': self.had_tool_activity,
            'resolved_by': self.resolved_by_id.name or '',
            'message_id': self.mail_message_id.id or False,
        }

    def _broadcast_update(self):
        notifications = []
        for recovery in self.sudo():
            if not recovery.mail_message_id:
                continue
            payload = recovery._format_for_client()
            for partner in recovery.session_id.channel_id.channel_partner_ids:
                notifications.append((
                    partner,
                    'odupilot.recovery/updated',
                    payload,
                ))
        if notifications:
            for target, notification_type, payload in notifications:
                self.env['bus.bus']._sendone(target, notification_type, payload)

    def _retry_payload(self):
        self.ensure_one()
        try:
            payload = json.loads(self.failed_command_id.payload or '{}')
        except (TypeError, ValueError):
            payload = {}
        if not isinstance(payload, dict) or not payload.get('text'):
            raise UserError(_(
                'The interrupted AI request no longer has a valid prompt payload.'))
        digest = hashlib.sha256(
            ('odupilot-recovery:%s' % self.id).encode()).hexdigest()[:32]
        payload['message_id'] = 'msg_%s' % digest
        return payload

    def _ensure_abort(self):
        self.ensure_one()
        abort = self.abort_command_id
        if abort and abort.state in ('pending', 'processing', 'done'):
            return abort
        abort = self.env['odupilot.command'].sudo().search([
            ('session_id', '=', self.session_id.id),
            ('state', 'in', ['pending', 'processing']),
            ('command_type', '=', 'abort'),
        ], order='id', limit=1)
        if not abort:
            abort = self.env['odupilot.command'].sudo().create({
                'session_id': self.session_id.id,
                'user_id': self.session_id.user_id.id,
                'command_type': 'abort',
                'payload': json.dumps({'reason': 'interrupted_recovery'}),
                'external_id': 'recovery:%s:abort' % self.id,
            })
        self.abort_command_id = abort.id
        return abort

    def _queue_retry(self, automatic=False, user=False):
        self.ensure_one()
        if self.retry_command_id:
            return self.retry_command_id
        self._ensure_abort()
        command = self.env['odupilot.command'].sudo().create({
            'session_id': self.session_id.id,
            'user_id': self.failed_command_id.user_id.id,
            'command_type': 'prompt',
            'recovery_id': self.id,
            'payload': json.dumps(
                self._retry_payload(), ensure_ascii=False),
            'external_id': 'recovery:%s:prompt' % self.id,
            # Повтор отвечает на тот же вопрос, значит и в ту же запись.
            'origin_model': self.failed_command_id.origin_model,
            'origin_res_id': self.failed_command_id.origin_res_id,
        })
        values = {
            'retry_command_id': command.id,
            'status': 'auto_retrying' if automatic else 'retrying',
        }
        if user:
            values.update({
                'resolved_by_id': user.id,
                'resolved_at': fields.Datetime.now(),
            })
        self.sudo().write(values)
        self.session_id._audit_event(
            'recovery.retry.queued',
            {
                'recovery_id': self.id,
                'failed_command_id': self.failed_command_id.id,
                'retry_command_id': command.id,
                'automatic': automatic,
            },
            user or False,
            'recovery:retry:%s' % self.id,
        )
        self._broadcast_update()
        return command

    def _mark_completed(self):
        recoveries = self.filtered(
            lambda recovery: recovery.status not in ('dismissed', 'completed'))
        if recoveries:
            recoveries.sudo().write({'status': 'completed'})
            recoveries._broadcast_update()

    def _mark_expired(self):
        recoveries = self.filtered(
            lambda recovery: recovery.status in (
                'pending', 'auto_retrying', 'retrying'))
        if recoveries:
            recoveries.sudo().write({'status': 'expired'})
            recoveries._broadcast_update()

    def _cancel_pending_commands(self):
        self.ensure_one()
        commands = self.abort_command_id | self.retry_command_id
        pending = commands.filtered(lambda command: command.state == 'pending')
        if pending:
            pending.sudo().write({
                'state': 'error',
                'next_attempt_at': False,
                'error': _(
                    'Cancelled because the original AI response arrived during recovery.'),
            })

    def action_reply(self, response):
        self.ensure_one()
        if response not in ('retry', 'dismiss'):
            raise ValidationError(_('The recovery response is invalid.'))
        recovery = self.sudo()
        recovery.session_id.with_user(self.env.user)._check_actor(
            self.env.user)
        if recovery.session_id.state == 'closed':
            raise UserError(_('This AI chat is closed.'))
        if recovery.status != 'pending':
            if (response == 'dismiss'
                    and recovery.status == 'dismissed'):
                return recovery._format_for_client()
            if (response == 'retry'
                    and recovery.status in ('retrying', 'completed')):
                return recovery._format_for_client()
            raise UserError(_(
                'This recovery request has already been answered.'))

        if response == 'retry':
            recovery._queue_retry(user=self.env.user)
        else:
            recovery._ensure_abort()
            recovery.write({
                'status': 'dismissed',
                'resolved_by_id': self.env.user.id,
                'resolved_at': fields.Datetime.now(),
            })
            recovery.session_id._audit_event(
                'recovery.dismissed',
                {
                    'recovery_id': recovery.id,
                    'failed_command_id': recovery.failed_command_id.id,
                },
                self.env.user,
                'recovery:dismissed:%s' % recovery.id,
            )
            recovery._broadcast_update()
        if (recovery.abort_command_id.state == 'done'
                and recovery.session_id.state == 'error'):
            recovery.session_id.write({
                'state': 'ready',
                'busy_since': False,
                'error': False,
            })
        return recovery._format_for_client()
