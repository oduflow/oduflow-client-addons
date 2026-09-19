# -*- encoding: utf-8 -*-


from odoo import api, SUPERUSER_ID


def post_init_hook(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    agent = env.ref(
        'odupilot.agent_payment_reconciliation', raise_if_not_found=False)
    if not agent:
        return
    servers = env['odupilot.mcp.server'].sudo().search([
        ('active', '=', True),
        ('enabled', '=', True),
        ('headers_json', 'ilike', 'ODOO_MCP_TOKEN'),
    ])
    if servers:
        agent.write({'mcp_server_ids': [(6, 0, servers.ids)]})
    env['odumcp.profile'].sudo().search(
        [])._odupilot_configure_agent_methods()
