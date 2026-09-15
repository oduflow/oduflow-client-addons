# -*- encoding: utf-8 -*-
import json

from odoo import api, fields, models, _
from odoo.exceptions import AccessError


class AiChatAgentLog(models.Model):
    _name = 'odupilot.agent.log'
    _description = 'AI Agent Action Log'
    _order = 'create_date desc, id desc'
    _rec_name = 'operation'

    session_id = fields.Many2one(
        'odupilot.session', ondelete='set null', readonly=True, index=True)
    agent_id = fields.Many2one(
        'odupilot.agent', ondelete='set null', readonly=True, index=True)
    user_id = fields.Many2one(
        'res.users', ondelete='set null', readonly=True, index=True)
    request_id = fields.Char(readonly=True, index=True)
    mcp_approval_id = fields.Many2one(
        'odumcp.approval', string='MCP Approval', ondelete='set null',
        readonly=True, index=True)
    mcp_audit_id = fields.Many2one(
        'odumcp.audit.log', string='MCP Audit',
        compute='_compute_mcp_audit_id', readonly=True)
    operation = fields.Char(required=True, readonly=True, index=True)
    status = fields.Selection([
        ('success', 'Success'),
        ('error', 'Error'),
    ], required=True, readonly=True, default='success', index=True)
    input_text = fields.Text(string='Input', readonly=True)
    result_text = fields.Text(string='Result', readonly=True)
    changes_text = fields.Text(string='Changes', readonly=True)
    error_text = fields.Text(string='Error', readonly=True)

    @api.depends('request_id')
    def _compute_mcp_audit_id(self):
        Audit = self.env['odumcp.audit.log'].sudo()
        for log in self:
            log.mcp_audit_id = Audit.search([
                ('request_id', '=', log.request_id),
            ], limit=1) if log.request_id else False

    @api.model
    def _json_text(self, value):
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, indent=2, default=str)

    @api.model
    def _record_agent_action(self, agent, operation, input_data,
                             result_data, changes_data, status='success',
                             error_text=''):
        agent.ensure_one()
        session_id = self.env.context.get('odupilot_session_id')
        session = self.env['odupilot.session'].sudo().browse(
            session_id).exists()
        if (not session or session.agent_id != agent
                or session.user_id.id != self.env.uid):
            raise AccessError(_(
                'An agent log can only be written by its active AI session.'))
        values = {
            'session_id': session.id,
            'agent_id': agent.id,
            'user_id': self.env.uid,
            'request_id': self.env.context.get('odumcp_request_id'),
            'mcp_approval_id': self.env.context.get(
                'odumcp_approval_id'),
            'operation': operation,
            'status': status,
            'input_text': self._json_text(input_data),
            'result_text': self._json_text(result_data),
            'changes_text': self._json_text(changes_data),
            'error_text': error_text or False,
        }
        return self.sudo().with_context(
            odupilot_agent_log_system_create=True).create(values)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('odupilot_agent_log_system_create'):
            raise AccessError(_(
                'AI agent log rows may only be created by agent methods.'))
        return super().create(vals_list)

    def write(self, values):
        raise AccessError(_('AI agent log rows are immutable.'))

    def unlink(self):
        raise AccessError(_('AI agent log rows are immutable.'))
