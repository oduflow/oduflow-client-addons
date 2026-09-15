# -*- encoding: utf-8 -*-
import json
import re

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


class AiChatAgent(models.Model):
    _name = 'odupilot.agent'
    _description = 'AI Agent'
    _order = 'name, id'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    active = fields.Boolean(default=True)
    agent_type = fields.Selection([
        ('general', 'General Assistant'),
        ('payment_reconciliation', 'Payment Reconciliation'),
    ], required=True, default='general')
    description = fields.Text(translate=True)
    system_prompt = fields.Text(
        help='Instructions that define this agent role and business boundaries.')
    ruleset_json = fields.Text(
        string='Permission rules',
        required=True,
        default='{}',
        help='JSON object used as the OpenCode permission configuration.',
    )
    mcp_only = fields.Boolean(
        string='MCP tools only',
        help='Deny all OpenCode tools except tools from the selected MCP servers.')
    mcp_server_ids = fields.Many2many(
        'odupilot.mcp.server',
        'odupilot_agent_mcp_server_rel',
        'agent_id',
        'server_id',
        string='MCP servers',
        groups='base.group_system',
    )
    profile_ids = fields.Many2many(
        'odupilot.profile',
        'odupilot_agent_profile_rel',
        'agent_id',
        'profile_id',
        string='Available for profiles',
        help='Leave empty to make the agent available for every OduPilot profile.',
        groups='base.group_system',
    )
    session_ids = fields.One2many(
        'odupilot.session', 'agent_id', string='Sessions', readonly=True)

    _odupilot_agent_code_unique = models.Constraint('unique(code)', 'The AI agent code must be unique.')

    @api.constrains('code')
    def _check_code(self):
        for agent in self:
            if not re.fullmatch(r'[A-Za-z0-9_.]+', agent.code or ''):
                raise ValidationError(_(
                    'Agent codes may contain only letters, numbers, dots, and underscores.'))

    @api.constrains('ruleset_json')
    def _check_ruleset_json(self):
        for agent in self:
            try:
                rules = json.loads(agent.ruleset_json or '{}')
            except (TypeError, ValueError) as error:
                raise ValidationError(_(
                    'Permission rules must contain valid JSON: %s', error))
            if not isinstance(rules, dict):
                raise ValidationError(_(
                    'Permission rules must be a JSON object.'))

    def _is_available_for_profile(self, profile):
        self.ensure_one()
        return bool(
            self.active
            and profile
            and (not self.profile_ids or profile in self.profile_ids)
        )

    def _configuration_error(self):
        self.ensure_one()
        if not self.active:
            return _('This AI agent is inactive.')
        if self.agent_type == 'payment_reconciliation':
            if 'payment.batch.auto.reconcile' not in self.env:
                return _(
                    'The Payment Batch reconciliation engine is not installed.')
            available_servers = self.mcp_server_ids.filtered(
                lambda server: server.active and server.enabled)
            if not available_servers:
                return _(
                    'Configure an active Odoo MCP server for the Payment Reconciliation agent.')
        return False

    def action_start_chat(self):
        self.ensure_one()
        return self.env['odupilot.session'].action_new_chat(self.id)

    def action_configure_mcp_methods(self):
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_(
                'Only Odoo administrators can configure agent MCP methods.'))
        profiles = self.env['odumcp.profile'].sudo().search([])
        self.filtered(
            lambda agent: agent.agent_type == 'payment_reconciliation'
        )._configure_payment_reconciliation_policies(profiles=profiles)
        # object-кнопка без action молчит в UI, поэтому всегда отдаём toast
        if profiles:
            message = _(
                'Payment Reconciliation methods configured for %s MCP profile(s).'
            ) % len(profiles)
            notification_type = 'success'
        else:
            message = _(
                'No MCP profile found. Create an MCP profile first, then configure the methods again.')
            notification_type = 'warning'
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('MCP Methods'),
                'message': message,
                'type': notification_type,
                'sticky': False,
            },
        }

    def _configure_payment_reconciliation_policies(self, profiles=None):
        agents = self.filtered(
            lambda agent: agent.agent_type == 'payment_reconciliation')
        if not agents:
            return True
        profiles = profiles or self.env['odumcp.profile'].sudo().search([])
        profiles._odupilot_configure_agent_methods()
        return True

    def _check_session_invocation(self):
        self.ensure_one()
        session_id = self.env.context.get('odupilot_session_id')
        agent_id = self.env.context.get('odupilot_agent_id')
        if not session_id or agent_id != self.id:
            raise AccessError(_(
                'This method can only be called by its active AI agent session.'))
        session = self.env['odupilot.session'].sudo().browse(session_id).exists()
        if (not session or session.state == 'closed'
                or session.agent_id != self
                or session.user_id.id != self.env.uid):
            raise AccessError(_(
                'This method can only be called by its active AI agent session.'))
        return session

    def _payment_statement_lines(self, statement_line_ids):
        if self.agent_type != 'payment_reconciliation':
            raise UserError(_(
                'This method is available only to the Payment Reconciliation agent.'))
        if (not isinstance(statement_line_ids, list)
                or not statement_line_ids
                or len(statement_line_ids) > 100
                or any(not isinstance(line_id, int) or isinstance(line_id, bool)
                       or line_id <= 0 for line_id in statement_line_ids)
                or len(set(statement_line_ids)) != len(statement_line_ids)):
            raise ValidationError(_(
                'Provide between 1 and 100 unique bank statement line IDs.'))
        StatementLine = self.env['account.bank.statement.line']
        StatementLine.check_access('read')
        lines = StatementLine.search([('id', 'in', statement_line_ids)])
        if set(lines.ids) != set(statement_line_ids):
            raise AccessError(_(
                'One or more bank statement lines are unavailable to this user.'))
        lines.check_access('read')
        return lines

    def _payment_reconciliation_plan(self, lines):
        engine = self.env['payment.batch.auto.reconcile']
        proposals = []
        skipped = {}
        eligible = self.env['account.bank.statement.line']
        for line in lines:
            if line.is_reconciled:
                skipped[line.id] = 'already_reconciled'
            elif line.amount >= 0:
                skipped[line.id] = 'not_outgoing'
            elif line.no_auto_reconcile:
                skipped[line.id] = 'no_auto_validate'
            elif not line.statement_id or line.statement_id.state != 'posted':
                skipped[line.id] = 'statement_not_posted'
            else:
                eligible |= line

        matches_by_company = {}
        legs_by_company = {}
        for company in eligible.mapped('company_id'):
            legs = engine._settlement_legs(company)
            legs_by_company[company.id] = legs
            candidates = self.env['account.bank.statement.line']
            for partner in {leg['partner'] for leg in legs}:
                candidates |= engine._candidate_statement_lines(company, partner)
            matches, dummy = engine._pair_lines_with_legs(
                company, candidates, legs)
            matches_by_company[company.id] = engine._drop_conflicting_legs(
                matches, legs)

        selected_matches = []
        for company in eligible.mapped('company_id'):
            legs = legs_by_company[company.id]
            company_matches = matches_by_company[company.id]
            for line, leg_index in company_matches:
                if line not in eligible:
                    continue
                leg = legs[leg_index]
                payable = engine._payable_lines(leg['moves'])
                if not payable:
                    skipped[line.id] = 'nothing_to_reconcile'
                    continue
                selected_matches.append((line, leg_index, legs))
                effective_currency = (
                    line.foreign_currency_id or line.currency_id)
                effective_amount = abs(
                    line.amount_currency
                    if line.foreign_currency_id else line.amount)
                proposals.append({
                    'statement_line_id': line.id,
                    'statement_id': line.statement_id.id,
                    'date': fields.Date.to_string(line.date),
                    'amount': effective_amount,
                    'currency': effective_currency.name,
                    'partner_id': leg['partner'].id,
                    'partner': leg['partner'].display_name,
                    'bill_ids': leg['moves'].ids,
                    'bills': leg['moves'].mapped('display_name'),
                    'leg': leg['kind'],
                })

        proposed_ids = {proposal['statement_line_id'] for proposal in proposals}
        for line in eligible.filtered(
                lambda item: item.id not in proposed_ids
                and item.id not in skipped):
            skipped[line.id] = 'no_unique_exact_match'
        return proposals, skipped, selected_matches

    def payment_reconciliation_preview(self, statement_line_ids=None):
        self.ensure_one()
        self._check_session_invocation()
        lines = self._payment_statement_lines(statement_line_ids)
        proposals, skipped, dummy = self._payment_reconciliation_plan(lines)
        result = {
            'proposals': proposals,
            'skipped': [
                {'statement_line_id': line_id, 'reason': reason}
                for line_id, reason in sorted(skipped.items())
            ],
        }
        self.env['odupilot.agent.log']._record_agent_action(
            self,
            'payment_reconciliation.preview',
            {'statement_line_ids': statement_line_ids},
            result,
            [],
        )
        return result

    def payment_reconciliation_apply(self, statement_line_ids=None):
        self.ensure_one()
        self._check_session_invocation()
        lines = self._payment_statement_lines(statement_line_ids)
        proposals, skipped, selected_matches = (
            self._payment_reconciliation_plan(lines))
        reconciled = {}
        for company in lines.mapped('company_id'):
            company_matches = [
                (line, leg_index)
                for line, leg_index, dummy in selected_matches
                if line.company_id == company
            ]
            company_legs = next(
                (legs for line, dummy, legs in selected_matches
                 if line.company_id == company),
                [],
            )
            if company_matches:
                reconciled.update(
                    self.env['payment.batch.auto.reconcile']._reconcile_matches(
                        company_matches, company_legs))

        proposal_by_line = {
            proposal['statement_line_id']: proposal for proposal in proposals
        }
        changes = []
        for line_id, proposal in proposal_by_line.items():
            if line_id in reconciled:
                changes.append(dict(proposal, status='reconciled'))
            else:
                skipped[line_id] = 'execution_failed'
        result = {
            'reconciled': changes,
            'skipped': [
                {'statement_line_id': line_id, 'reason': reason}
                for line_id, reason in sorted(skipped.items())
            ],
        }
        self.env['odupilot.agent.log']._record_agent_action(
            self,
            'payment_reconciliation.apply',
            {'statement_line_ids': statement_line_ids},
            result,
            changes,
        )
        return result
