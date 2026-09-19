# -*- encoding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

from .config_validation import validate_git_ref, validate_http_url


class AiChatProfile(models.Model):
    _name = 'odupilot.profile'
    _description = 'OduPilot Access Profile'
    _order = 'name, id'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    active = fields.Boolean(default=True)
    workspace_type = fields.Selection([
        ('files', 'Files'),
        ('worktree', 'Developer worktree'),
    ], required=True, default='files')
    model = fields.Char(
        required=True,
        help='Model identifier exposed by the configured AI endpoint.',
    )
    reasoning_effort = fields.Selection([
        ('default', 'Provider default'),
        ('minimal', 'Minimal'),
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ], string='Thinking effort', required=True, default='high',
        help='Reasoning effort requested from the model. Choose Provider '
             'default for models that do not support thinking.')
    litellm_api_key = fields.Char(
        string='LiteLLM API key',
        groups='base.group_system',
        copy=False,
    )
    max_sessions = fields.Integer(required=True, default=3)
    default_agent_id = fields.Many2one(
        'odupilot.agent',
        string='Default agent',
        ondelete='restrict',
        domain="['&', ('active', '=', True), '|', ('profile_ids', '=', False), ('profile_ids', 'in', [id])]",
        help='Agent used by Ask AI and by integrations that do not ask the user to select one.',
        groups='base.group_system',
    )
    agent_ids = fields.Many2many(
        'odupilot.agent',
        'odupilot_agent_profile_rel',
        'profile_id',
        'agent_id',
        string='Available agents',
        groups='base.group_system',
    )
    user_ids = fields.One2many(
        'res.users',
        'odupilot_profile_id',
        string='Users',
        groups='base.group_system',
    )
    developer_repo_url = fields.Char(
        string='Developers repository URL',
        help='HTTPS Git repository cloned for this developer profile.',
        groups='base.group_system',
    )
    developer_base_branch = fields.Char(
        string='Developers base branch',
        default='prod',
        help='Remote branch from which new developer worktrees start.',
        groups='base.group_system',
    )
    developer_github_pat = fields.Char(
        string='Developers GitHub PAT',
        copy=False,
        help='Token used by Odoo only while cloning and fetching this profile repository.',
        groups='base.group_system',
    )
    developer_environment_mcp_server_id = fields.Many2one(
        'odupilot.mcp.server',
        string='Developer environment MCP',
        ondelete='restrict',
        domain="[('active', '=', True), ('enabled', '=', True)]",
        help=(
            'Full MCP server used by the automatic developer environment '
            'bootstrap. Leave empty to create only the Git worktree.'),
        groups='base.group_system',
    )
    developer_environment_template_name = fields.Char(
        string='Developer environment template',
        default='prod',
        help='Environment template passed to the full MCP bootstrap tool.',
        groups='base.group_system',
    )
    developer_environment_odoo_image = fields.Char(
        string='Developer environment Odoo image',
        default='odoo15_veles',
        help='Odoo image passed to the full MCP bootstrap tool.',
        groups='base.group_system',
    )
    developer_bootstrap_prompt = fields.Text(
        string='Additional developer bootstrap instructions',
        help='Optional instructions appended to the automatic environment bootstrap prompt.',
        groups='base.group_system',
    )

    _sql_constraints = [('odupilot_profile_code_unique', 'unique(code)', 'The AI chat profile code must be unique.')]

    def _developers_profile_configuration_error(self):
        """Ошибка, из-за которой профиль нельзя использовать из debug menu."""
        self.ensure_one()
        if not self.active:
            return _('Developers Profile must be active.')
        if self.workspace_type != 'worktree':
            return _('Developers Profile must use Developer worktree.')
        if not self.litellm_api_key:
            return _('Developers Profile must provide a LiteLLM API key.')
        if not self.default_agent_id:
            return _('Developers Profile must provide a default agent.')
        if not self.default_agent_id._is_available_for_profile(self):
            return _('Developers Profile default agent is unavailable.')
        if not self.developer_repo_url:
            return _('Developers Profile must provide a repository URL.')
        if not self.developer_github_pat:
            return _('Developers Profile must provide a GitHub PAT.')
        environment_mcp = self.developer_environment_mcp_server_id
        if not environment_mcp:
            return _(
                'Developers Profile must provide a Developer environment MCP.')
        if not environment_mcp.active or not environment_mcp.enabled:
            return _(
                'Developers Profile must provide an active and enabled '
                'Developer environment MCP.')
        return False

    def unlink(self):
        # Сессия несёт за собой рабочий каталог на volume моста; убирает его
        # только Python-овый AiChatSession.unlink().
        # Поэтому profile_id намеренно остаётся ondelete='restrict': SQL-каскад
        # снёс бы строки в обход ORM и оставил каталоги мусором навсегда.
        sessions = self.env['odupilot.session'].sudo().search([
            ('profile_id', 'in', self.ids),
        ])
        sessions.unlink()
        # Архивированные пользователи тоже держат профиль, поэтому active_test.
        users = self.env['res.users'].sudo().with_context(
            active_test=False).search([
                ('odupilot_profile_id', 'in', self.ids),
            ])
        users.write({'odupilot_profile_id': False})
        exclusive_agents = self.mapped('agent_ids').filtered(
            lambda agent: not (agent.profile_ids - self))
        result = super().unlink()
        if exclusive_agents:
            exclusive_agents.unlink()
        return result

    @api.constrains('default_agent_id', 'agent_ids')
    def _check_default_agent(self):
        for profile in self:
            if (profile.default_agent_id
                    and not profile.default_agent_id._is_available_for_profile(
                        profile)):
                raise ValidationError(_(
                    'The default agent must be active and available for this profile.'))

    @api.constrains('max_sessions')
    def _check_max_sessions(self):
        if any(profile.max_sessions < 1 for profile in self):
            raise ValidationError(_(
                'Maximum sessions must be greater than zero.'))

    @api.constrains(
        'developer_repo_url',
        'developer_base_branch',
        'developer_github_pat',
        'developer_environment_mcp_server_id',
        'developer_environment_template_name',
        'developer_environment_odoo_image',
    )
    def _check_developer_workspace(self):
        for profile in self:
            if profile.developer_repo_url:
                validate_http_url(
                    profile.developer_repo_url,
                    _('Developers repository URL'),
                    https_only=True,
                 env=self.env)
            if profile.developer_base_branch:
                validate_git_ref(profile.developer_base_branch, env=self.env)
            github_pat = profile.developer_github_pat or ''
            if '\r' in github_pat or '\n' in github_pat:
                raise ValidationError(_(
                    'Developers GitHub PAT contains an invalid character.'))
            environment_mcp = profile.developer_environment_mcp_server_id
            if environment_mcp and profile.workspace_type != 'worktree':
                raise ValidationError(_(
                    'Developer environment bootstrap requires a developer worktree profile.'))
            if environment_mcp and (
                    not environment_mcp.active or not environment_mcp.enabled):
                raise ValidationError(_(
                    'Developer environment MCP must be active and enabled.'))
            for value, label in (
                    (profile.developer_environment_template_name,
                     _('Developer environment template')),
                    (profile.developer_environment_odoo_image,
                     _('Developer environment Odoo image'))):
                if environment_mcp and not (value or '').strip():
                    raise ValidationError(_('%s is required.', label))
                if '\r' in (value or '') or '\n' in (value or ''):
                    raise ValidationError(_(
                        '%s contains an invalid character.', label))

    @api.constrains('workspace_type')
    def _check_worktree_assignments(self):
        worktree_profiles = self.filtered(
            lambda profile: profile.workspace_type == 'worktree')
        if not worktree_profiles:
            return
        assigned_users = self.env['res.users'].sudo().search([
            ('odupilot_profile_id', 'in', worktree_profiles.ids),
        ])
        invalid_users = assigned_users.filtered(
            lambda user: not user.has_group('base.group_system'))
        if invalid_users:
            raise ValidationError(_(
                'Developer worktree profiles can only be assigned to Odoo administrators.'))
