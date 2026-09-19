from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request


class OduPilotBridgeController(http.Controller):
    @http.route('/odupilot/bridge/poll', type='json', auth='user', methods=['POST'])
    def poll(self, last=0):
        commands = request.env['odupilot.command']
        commands._check_bridge_access()
        if not isinstance(last, int) or isinstance(last, bool) or last < 0:
            raise ValidationError('Invalid event cursor.')
        # The service account may only observe queue wake-ups, never arbitrary bus channels.
        return request.env['bus.bus']._poll([commands.BRIDGE_CHANNEL], last)
