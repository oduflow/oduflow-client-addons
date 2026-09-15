import json
from odoo.tests import HttpCase, tagged, new_test_user


@tagged('post_install', '-at_install')
class TestOduPilotHttp(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bridge = new_test_user(cls.env, login='pilot_http_bridge', groups='odupilot.group_bridge')
        cls.reader = new_test_user(cls.env, login='pilot_http_reader', groups='base.group_user')

    def _rpc(self, route, params):
        response = self.url_open(route, data=json.dumps({
            'jsonrpc': '2.0', 'method': 'call', 'params': params, 'id': 1,
        }), headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_bridge_poll_and_cursor_validation(self):
        self.authenticate(self.bridge.login, self.bridge.login)
        result = self._rpc('/odupilot/bridge/poll', {'last': 0})
        self.assertIn('result', result)
        self.assertIsInstance(result['result'], list)
        result = self._rpc('/odupilot/bridge/poll', {'last': -1})
        self.assertEqual(result['error']['data']['name'], 'odoo.exceptions.ValidationError')

    def test_bridge_poll_denies_regular_users(self):
        self.authenticate(self.reader.login, self.reader.login)
        result = self._rpc('/odupilot/bridge/poll', {})
        self.assertEqual(result['error']['data']['name'], 'odoo.exceptions.AccessError')

    def test_stream_snapshot_model_rpc(self):
        self.authenticate(self.reader.login, self.reader.login)
        result = self._rpc('/web/dataset/call_kw/odupilot.session/stream_snapshot', {
            'model': 'odupilot.session', 'method': 'stream_snapshot', 'args': [0], 'kwargs': {},
        })
        self.assertIn('result', result)
        self.assertFalse(result['result'])
