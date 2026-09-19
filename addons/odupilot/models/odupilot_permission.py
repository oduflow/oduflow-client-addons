# -*- encoding: utf-8 -*-
import json

from odoo import fields, models, _
from odoo.exceptions import UserError, ValidationError


class AiChatPermission(models.Model):
    _name = 'odupilot.permission'
    _description = 'OduPilot Permission Request'
    _order = 'id desc'

    session_id = fields.Many2one(
        'odupilot.session', required=True, ondelete='cascade', index=True)
    request_id = fields.Char(required=True, index=True)
    permission = fields.Char(required=True)
    patterns_json = fields.Text(required=True, default='[]')
    metadata_json = fields.Text(required=True, default='{}')
    status = fields.Selection([
        ('pending', 'Waiting for approval'),
        ('submitting', 'Sending response'),
        ('once', 'Allowed once'),
        ('always', 'Always allowed'),
        ('reject', 'Rejected'),
        ('expired', 'Expired'),
    ], required=True, default='pending', index=True)
    event_id = fields.Many2one(
        'odupilot.event', ondelete='set null', index=True)
    mail_message_id = fields.Many2one(
        'mail.message', ondelete='set null', index=True)
    resolved_by_id = fields.Many2one(
        'res.users', string='Answered by', ondelete='set null', index=True)
    resolved_at = fields.Datetime(copy=False)

    _sql_constraints = [('odupilot_permission_request_unique', 'unique(session_id, request_id)', 'This AI permission request already exists.')]

    def _json_value(self, field_name, fallback):
        self.ensure_one()
        try:
            value = json.loads(self[field_name] or '')
        except (TypeError, ValueError):
            return fallback
        if not isinstance(value, type(fallback)):
            return fallback
        return value

    def _format_for_client(self):
        self.ensure_one()
        status_labels = dict(
            self._fields['status']._description_selection(self.env))
        patterns = self._json_value('patterns_json', [])
        metadata = self._json_value('metadata_json', {})
        details = json.dumps(
            metadata, ensure_ascii=False, indent=2, sort_keys=True)
        if details == '{}':
            details = ''
        return {
            'id': self.id,
            'request_id': self.request_id,
            'permission': self.permission,
            'patterns': patterns,
            'details': details,
            'status': self.status,
            'status_label': status_labels.get(self.status, self.status),
            'resolved_by': self.resolved_by_id.name or '',
            'message_id': self.mail_message_id.id or False,
        }

    def _broadcast_update(self):
        notifications = []
        for permission in self.sudo():
            if not permission.mail_message_id:
                continue
            payload = permission._format_for_client()
            for partner in permission.session_id.channel_id.channel_partner_ids:
                notifications.append((
                    partner,
                    'odupilot.permission/updated',
                    payload,
                ))
        if notifications:
            for target, notification_type, payload in notifications:
                self.env['bus.bus']._sendone(target, notification_type, payload)

    def _mark_replied(self, response, user=False):
        if response not in ('once', 'always', 'reject'):
            raise ValidationError(_('The permission response is invalid.'))
        values = {'status': response}
        if user:
            values.update({
                'resolved_by_id': user.id,
                'resolved_at': fields.Datetime.now(),
            })
        self.sudo().write(values)
        self._broadcast_update()

    def _mark_expired(self):
        permissions = self.filtered(
            lambda permission: permission.status in ('pending', 'submitting'))
        if permissions:
            permissions.sudo().write({'status': 'expired'})
            permissions._broadcast_update()

    def action_reply(self, response):
        self.ensure_one()
        if response not in ('once', 'always', 'reject'):
            raise ValidationError(_('The permission response is invalid.'))
        permission = self.sudo()
        permission.session_id.with_user(self.env.user)._check_actor(
            self.env.user)
        if permission.session_id.state == 'closed':
            raise UserError(_('This AI chat is closed.'))
        if permission.status == response:
            return permission._format_for_client()
        if permission.status != 'pending':
            raise UserError(_(
                'This permission request has already been answered.'))

        command = self.env['odupilot.command'].sudo().create({
            'session_id': permission.session_id.id,
            'user_id': self.env.user.id,
            'command_type': 'permission',
            'payload': json.dumps({
                'permission_id': permission.request_id,
                'response': response,
            }),
            'external_id': 'permission:%s:%s' % (
                permission.session_id.id,
                permission.request_id,
            ),
        })
        permission.write({
            'status': 'submitting',
            'resolved_by_id': self.env.user.id,
            'resolved_at': fields.Datetime.now(),
        })
        permission.session_id._audit_event(
            'permission.response.queued',
            {
                'command_id': command.id,
                'permission_id': permission.request_id,
                'response': response,
            },
            self.env.user,
            'permission-response:%s:%s' % (
                permission.session_id.id,
                permission.request_id,
            ),
        )
        permission._broadcast_update()
        return permission._format_for_client()
