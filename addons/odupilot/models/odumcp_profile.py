# -*- encoding: utf-8 -*-
from odoo import api, models


class OduMcpProfile(models.Model):
    _inherit = 'odumcp.profile'

    @api.model_create_multi
    def create(self, vals_list):
        profiles = super().create(vals_list)
        profiles._odupilot_configure_agent_methods()
        return profiles

    def _odupilot_configure_agent_methods(self):
        agent_model = self.env['ir.model'].sudo()._get('odupilot.agent')
        if not agent_model:
            return True
        model_policy_model = self.env['odumcp.model.policy'].sudo()
        method_policy_model = self.env['odumcp.method.policy'].sudo()
        read_fields = self.env['ir.model.fields'].sudo().search([
            ('model_id', '=', agent_model.id),
            ('name', 'in', ['name', 'code', 'agent_type', 'description']),
        ])
        for profile in self.sudo():
            model_policy = model_policy_model.search([
                ('profile_id', '=', profile.id),
                ('model_id', '=', agent_model.id),
            ], limit=1)
            if not model_policy:
                model_policy_model.create({
                    'profile_id': profile.id,
                    'model_id': agent_model.id,
                    'allow_read': True,
                    'read_field_ids': [(6, 0, read_fields.ids)],
                })
            elif not model_policy.allow_read:
                model_policy.write({
                    'allow_read': True,
                    'read_field_ids': [(6, 0, read_fields.ids)],
                })
            for method_name, risk_level in (
                    ('payment_reconciliation_preview', 'low'),
                    ('payment_reconciliation_apply', 'high')):
                policy = method_policy_model.search([
                    ('profile_id', '=', profile.id),
                    ('model_id', '=', agent_model.id),
                    ('method_name', '=', method_name),
                ], limit=1)
                values = {
                    'risk_level': risk_level,
                    'max_record_count': 1,
                    'allow_model_method': False,
                    'allow_positional_arguments': False,
                    'allowed_keyword_arguments': 'statement_line_ids',
                    'max_argument_bytes': 8192,
                    'requires_approval': False,
                }
                if policy:
                    policy.write(values)
                else:
                    values.update({
                        'profile_id': profile.id,
                        'model_id': agent_model.id,
                        'method_name': method_name,
                    })
                    method_policy_model.create(values)
        return True
