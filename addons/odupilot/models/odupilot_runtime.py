# -*- encoding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import AccessError


class AiChatRuntime(models.Model):
    _name = 'odupilot.runtime'
    _description = 'OduPilot Runtime Status'

    name = fields.Char(required=True, default='OduPilot Runtime')
    last_heartbeat_at = fields.Datetime(
        string='Last heartbeat', readonly=True)
    bridge_started_at = fields.Datetime(
        string='Bridge started', readonly=True)
    bridge_version = fields.Char(string='Bridge version', readonly=True)
    opencode_version = fields.Char(string='OpenCode version', readonly=True)
    opencode_healthy = fields.Boolean(string='OpenCode healthy', readonly=True)
    opencode_latency_ms = fields.Integer(
        string='OpenCode latency (ms)', readonly=True)
    event_queue_size = fields.Integer(string='Buffered events', readonly=True)
    health_error = fields.Text(string='Current health error', readonly=True)
    last_error = fields.Text(string='Last runtime error', readonly=True)
    last_error_at = fields.Datetime(
        string='Last runtime error at', readonly=True)
    last_error_state = fields.Char(
        string='Last runtime error state',
        compute='_compute_last_error_state')
    status = fields.Selection([
        ('healthy', 'Healthy'),
        ('degraded', 'Degraded'),
        ('offline', 'Offline'),
    ], compute='_compute_status')
    heartbeat_age_seconds = fields.Integer(
        compute='_compute_status', string='Heartbeat age (seconds)')
    pending_command_count = fields.Integer(
        compute='_compute_metrics', string='Pending commands')
    processing_command_count = fields.Integer(
        compute='_compute_metrics', string='Processing commands')
    stuck_command_count = fields.Integer(
        compute='_compute_metrics', string='Stuck commands')
    error_command_count = fields.Integer(
        compute='_compute_metrics', string='All command errors')
    error_command_24h_count = fields.Integer(
        compute='_compute_metrics', string='Command errors (24h)')
    completed_command_24h_count = fields.Integer(
        compute='_compute_metrics', string='Completed commands (24h)')
    average_duration_24h = fields.Float(
        compute='_compute_metrics', string='Average duration (24h)')
    maximum_duration_24h = fields.Float(
        compute='_compute_metrics', string='Maximum duration (24h)')
    busy_session_count = fields.Integer(
        compute='_compute_metrics', string='Busy sessions')
    waiting_approval_count = fields.Integer(
        compute='_compute_metrics', string='Waiting approvals')

    @api.depends('last_heartbeat_at', 'opencode_healthy')
    def _compute_status(self):
        now = fields.Datetime.now()
        for runtime in self:
            if not runtime.last_heartbeat_at:
                runtime.heartbeat_age_seconds = 0
                runtime.status = 'offline'
                continue
            age = max(0, int((now - runtime.last_heartbeat_at).total_seconds()))
            runtime.heartbeat_age_seconds = age
            if age > 90:
                runtime.status = 'offline'
            elif runtime.opencode_healthy:
                runtime.status = 'healthy'
            else:
                runtime.status = 'degraded'

    @api.depends('last_error', 'last_error_at', 'health_error')
    def _compute_last_error_state(self):
        now = fields.Datetime.now()
        for runtime in self:
            if not runtime.last_error:
                runtime.last_error_state = False
                continue
            age = self._format_age(now, runtime.last_error_at)
            if runtime.health_error:
                runtime.last_error_state = (
                    _('Active · last seen %s ago') % age if age
                    else _('Active issue'))
            else:
                runtime.last_error_state = (
                    _('Resolved · was %s ago') % age if age
                    else _('Resolved issue'))

    @api.model
    def _format_age(self, now, moment):
        """Человекочитаемый возраст события: 45 s, 13 h, 3 d."""
        if not moment:
            return ''
        seconds = max(0, int((now - moment).total_seconds()))
        if seconds < 60:
            return _('%s s') % seconds
        if seconds < 3600:
            return _('%s min') % (seconds // 60)
        if seconds < 86400:
            return _('%s h') % (seconds // 3600)
        return _('%s d') % (seconds // 86400)

    def _compute_metrics(self):
        command_model = self.env['odupilot.command'].sudo()
        session_model = self.env['odupilot.session'].sudo()
        now = fields.Datetime.now()
        day_ago = now - timedelta(hours=24)
        stuck_before = now - timedelta(minutes=10)
        pending = command_model.search_count([('state', '=', 'pending')])
        processing = command_model.search_count([('state', '=', 'processing')])
        stuck = command_model.search_count([
            '|',
            '&', ('state', '=', 'processing'),
            ('processing_started_at', '<=', stuck_before),
            '&', ('state', '=', 'pending'),
            ('create_date', '<=', stuck_before),
        ])
        errors = command_model.search_count([('state', '=', 'error')])
        errors_24h = command_model.search_count([
            ('state', '=', 'error'),
            ('completed_at', '>=', day_ago),
        ])
        self.env.cr.execute("""
            SELECT COUNT(*),
                   COALESCE(AVG(duration_seconds), 0),
                   COALESCE(MAX(duration_seconds), 0)
              FROM odupilot_command
             WHERE state = 'done'
               AND completed_at >= %s
        """, [day_ago])
        completed_24h, average_duration, maximum_duration = (
            self.env.cr.fetchone())
        busy = session_model.search_count([('state', '=', 'busy')])
        waiting = session_model.search_count([
            ('state', '=', 'waiting_approval')])
        for runtime in self:
            runtime.pending_command_count = pending
            runtime.processing_command_count = processing
            runtime.stuck_command_count = stuck
            runtime.error_command_count = errors
            runtime.error_command_24h_count = errors_24h
            runtime.completed_command_24h_count = completed_24h
            runtime.average_duration_24h = average_duration
            runtime.maximum_duration_24h = maximum_duration
            runtime.busy_session_count = busy
            runtime.waiting_approval_count = waiting

    @api.model
    def _check_bridge_access(self):
        if not self.env.user.has_group('odupilot.group_bridge'):
            raise AccessError(_(
                'Only the AI chat bridge service account may report AI chat runtime status.'))

    @api.model
    def bridge_heartbeat(self, values=None):
        self._check_bridge_access()
        values = values or {}
        runtime = self.sudo().search([], limit=1)
        if not runtime:
            runtime = self.sudo().create({'name': _('OduPilot Runtime')})
        error = (values.get('error') or '')[:4000]
        update = {
            'last_heartbeat_at': fields.Datetime.now(),
            'bridge_version': (values.get('bridge_version') or '')[:128],
            'opencode_version': (values.get('opencode_version') or '')[:128],
            'opencode_healthy': bool(values.get('opencode_healthy')),
            'opencode_latency_ms': max(
                0, int(values.get('opencode_latency_ms') or 0)),
            'event_queue_size': max(
                0, int(values.get('event_queue_size') or 0)),
            'health_error': error or False,
        }
        if values.get('bridge_started_at'):
            update['bridge_started_at'] = values['bridge_started_at']
        if error:
            update.update({
                'last_error': error,
                'last_error_at': fields.Datetime.now(),
            })
        runtime.write(update)
        return {'status': runtime.status, 'heartbeat_at': runtime.last_heartbeat_at}

    def _command_action(self, name, domain):
        self.ensure_one()
        action = self.env.ref('odupilot.action_odupilot_command').read()[0]
        action.update({'name': name, 'domain': domain})
        return action

    def action_open_pending_commands(self):
        return self._command_action(
            _('Pending OduPilot Commands'), [('state', '=', 'pending')])

    def action_open_processing_commands(self):
        return self._command_action(
            _('Processing OduPilot Commands'), [('state', '=', 'processing')])

    def action_open_error_commands(self):
        return self._command_action(
            _('Failed OduPilot Commands'), [('state', '=', 'error')])

    def action_open_sessions(self):
        self.ensure_one()
        return self.env.ref('odupilot.action_odupilot_session').read()[0]
