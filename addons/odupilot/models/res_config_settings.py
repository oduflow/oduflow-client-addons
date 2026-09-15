# -*- encoding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

from .config_validation import validate_http_url


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ai_base_url = fields.Char(
        string='AI base URL',
        config_parameter='odupilot.ai_base_url',
    )
    odupilot_developers_profile_id = fields.Many2one(
        'odupilot.profile',
        string='Developers Profile',
        domain="[('active', '=', True), ('workspace_type', '=', 'worktree')]",
        help=(
            'Developer worktree profile used when an administrator starts '
            'AI Developer from the developer menu.'),
        config_parameter='odupilot.developers_profile_id',
    )
    odupilot_responsible_developer_id = fields.Many2one(
        'res.users',
        string='Responsible Developer',
        domain="[('active', '=', True), ('share', '=', False)]",
        help=(
            'Administrator who receives AI Developer requests classified '
            'as code changes and joins their Discuss threads.'),
        config_parameter='odupilot.responsible_developer_id',
    )
    odupilot_busy_timeout_minutes = fields.Integer(
        string='Busy session timeout',
        help='Abort an AI request that remains busy longer than this many minutes.',
        config_parameter='odupilot.busy_timeout_minutes',
        default=30,
    )
    odupilot_event_retention_days = fields.Integer(
        string='Audit event retention',
        help='Delete AI chat audit event payloads after this many days. Set zero to keep them indefinitely.',
        config_parameter='odupilot.event_retention_days',
        default=90,
    )
    odupilot_closed_session_retention_days = fields.Integer(
        string='Closed session retention',
        help=(
            'Delete technical AI session records after this many days. '
            'Discuss channels and messages are kept. Set zero to keep records indefinitely.'),
        config_parameter='odupilot.closed_session_retention_days',
        default=365,
    )

    @api.constrains('ai_base_url')
    def _check_ai_base_url(self):
        for settings in self.filtered('ai_base_url'):
            validate_http_url(settings.ai_base_url, _('AI base URL'), env=self.env)

    @api.constrains('odupilot_developers_profile_id')
    def _check_odupilot_developers_profile(self):
        for settings in self.filtered('odupilot_developers_profile_id'):
            error = (
                settings.odupilot_developers_profile_id
                ._developers_profile_configuration_error()
            )
            if error:
                raise ValidationError(error)

    @api.constrains('odupilot_responsible_developer_id')
    def _check_odupilot_responsible_developer(self):
        for settings in self.filtered('odupilot_responsible_developer_id'):
            developer = settings.odupilot_responsible_developer_id
            if (not developer.active or developer.share
                    or not developer.has_group('base.group_system')):
                raise ValidationError(_(
                    'Responsible Developer must be an active internal Odoo '
                    'administrator.'))

    @api.constrains('odupilot_busy_timeout_minutes')
    def _check_odupilot_busy_timeout_minutes(self):
        for settings in self:
            if settings.odupilot_busy_timeout_minutes < 1:
                raise ValidationError(_(
                    'Busy session timeout must be at least one minute.'))

    @api.constrains(
        'odupilot_event_retention_days',
        'odupilot_closed_session_retention_days',
    )
    def _check_odupilot_retention_days(self):
        for settings in self:
            if (settings.odupilot_event_retention_days < 0
                    or settings.odupilot_closed_session_retention_days < 0):
                raise ValidationError(_(
                    'AI chat retention periods cannot be negative.'))
