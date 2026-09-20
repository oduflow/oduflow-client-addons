import json
from urllib.parse import urlparse

from odoo.tests import HttpCase, tagged
from odoo.tests.common import new_test_user


@tagged("post_install", "-at_install")
class TestOduLoginHttp(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = new_test_user(
            cls.env,
            login="odulogin_http_admin",
            groups="base.group_system",
            name="HTTP Administrator",
        )
        cls.target = new_test_user(
            cls.env,
            login="odulogin_http_target",
            groups="base.group_user",
            name="HTTP Target",
        )

    def _rpc(self, route, params=None):
        response = self.url_open(
            route,
            data=json.dumps({
                "jsonrpc": "2.0",
                "method": "call",
                "id": 1,
                "params": params or {},
            }),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertNotIn("error", payload, payload.get("error"))
        return payload["result"]

    def test_jsonrpc_switch_persists_across_requests(self):
        self.authenticate(self.admin.login, self.admin.login)
        # Scope the test cookie like a browser so session rotation replaces it.
        self.opener.cookies.clear(domain="", path="/", name="session_id")
        self.opener.cookies.set(
            "session_id", self.session.sid,
            domain=urlparse(self.base_url()).hostname, path="/",
        )
        wizard_id = self._rpc(
            "/web/dataset/call_kw/odulogin.switch.wizard/create",
            {
                "model": "odulogin.switch.wizard",
                "method": "create",
                "args": [{"user_id": self.target.id}],
                "kwargs": {},
            },
        )

        action = self._rpc(
            "/web/dataset/call_button",
            {
                "model": "odulogin.switch.wizard",
                "method": "action_switch",
                "args": [[wizard_id]],
                "kwargs": {},
            },
        )
        self.assertEqual(action["tag"], "reload")
        switched = self._rpc("/web/session/get_session_info")
        self.assertEqual(switched["uid"], self.target.id)
        self.assertTrue(switched["odulogin_is_switched"])
        self.assertEqual(switched["odulogin_origin_name"], self.admin.name)

        self.assertTrue(
            self._rpc(
                "/web/dataset/call_kw/odulogin.session/switch_back",
                {
                    "model": "odulogin.session",
                    "method": "switch_back",
                    "args": [],
                    "kwargs": {},
                },
            )
        )
        restored = self._rpc("/web/session/get_session_info")
        self.assertEqual(restored["uid"], self.admin.id)
        self.assertFalse(restored["odulogin_is_switched"])
