from unittest.mock import patch, Mock

import requests

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestOduscale(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env["res.users"].create({
            "name": "VPN Manager", "login": "oduscale-test-manager", "email": "manager@example.test",
            "groups_id": [Command.set([cls.env.ref("oduscale.group_manager").id])],
        })
        cls.employee_user = cls.env["res.users"].create({
            "name": "VPN Employee", "login": "oduscale-test-employee",
            "groups_id": [Command.set([cls.env.ref("base.group_user").id])],
        })
        cls.server = cls.env["oduscale.server"].create({
            "name": "Test Headscale", "api_url": "http://headscale:8080",
            "login_url": "https://headscale.example.com",
        })
        cls.employee = cls.env["hr.employee"].create({"name": "Test Employee", "user_id": cls.employee_user.id})
        cls.connection = cls.env["oduscale.connection"].create({
            "employee_id": cls.employee.id, "server_id": cls.server.id,
        }).with_user(cls.manager)

    def setUp(self):
        super().setUp()
        self.calls = []
        self.users = []
        self.nodes = []
        self.keys = []
        self.api_patch = patch.object(type(self.server), "_request", autospec=True, side_effect=self._api)
        self.api_patch.start()
        self.addCleanup(self.api_patch.stop)

    def _api(self, server, method, path, payload=None, missing_ok=False):
        self.calls.append((method, path, payload))
        if (method, path) == ("GET", "/user"):
            return {"users": self.users}
        if (method, path) == ("POST", "/user"):
            user = {"id": "7", "name": payload["name"]}
            self.users.append(user)
            return {"user": user}
        if (method, path) == ("GET", "/node"):
            return {"nodes": self.nodes}
        if method == "GET" and path.startswith("/node/"):
            return {"node": next((n for n in self.nodes if n["id"] == path.split("/")[-1]), None)}
        if (method, path) == ("GET", "/preauthkey"):
            return {"preAuthKeys": self.keys}
        if (method, path) == ("POST", "/preauthkey"):
            key = {"id": str(len(self.keys) + 1), "key": "test-secret-enrollment",
                   "user": {"id": payload["user"]}, "expiration": payload["expiration"], "used": False}
            self.keys.append(key)
            return {"preAuthKey": key}
        if method == "DELETE" and path.startswith("/node/"):
            self.nodes[:] = [n for n in self.nodes if n["id"] != path.split("/")[-1]]
            return {}
        if (method, path) == ("POST", "/preauthkey/expire"):
            return {}
        raise AssertionError((method, path, payload))

    def test_enrollment_single_use_and_no_key_in_audit(self):
        self.connection.action_activate()
        action = self.connection.action_enroll()
        wizard = self.env["oduscale.enrollment"].browse(action["res_id"])
        self.assertIn("test-secret-enrollment", wizard.command)
        self.assertNotIn("key", self.env["oduscale.key"]._fields)
        body = next(payload for method, path, payload in self.calls if path == "/preauthkey" and method == "POST")
        self.assertFalse(body["reusable"])
        self.assertFalse(body["ephemeral"])
        self.assertEqual(body["aclTags"], [])
        self.assertLessEqual((wizard.expiration - fields.Datetime.now()).total_seconds(), 3600)
        self.assertFalse(any("test-secret" in str(m.body) for m in self.connection.message_ids))

    def test_activate_is_idempotent_and_recovers_remote_user(self):
        self.connection.action_activate()
        self.connection.action_activate()
        self.assertEqual(len(self.users), 1)
        self.connection.sudo()._set_remote({"remote_user_id": False})
        self.connection.action_activate()
        self.assertEqual(len(self.users), 1)
        self.assertEqual(self.connection.remote_user_id, "7")

    def test_inactive_employee_cannot_enroll(self):
        self.employee.active = False
        with self.assertRaises(UserError):
            self.connection.action_activate()
        self.assertFalse(self.calls)

    def test_sync_filters_owner_and_retains_missing_devices(self):
        self.connection.action_activate()
        self.nodes = [
            {"id": "10", "user": {"id": "7"}, "name": "laptop", "online": True,
             "ipAddresses": ["100.80.0.2"], "lastSeen": "2026-09-14T20:00:00Z"},
            {"id": "11", "user": {"id": "8"}, "name": "unrelated"},
        ]
        self.connection.action_sync()
        self.assertEqual(self.connection.device_ids.mapped("name"), ["laptop"])
        self.assertTrue(self.connection.device_ids.online)
        self.nodes = []
        self.connection.action_sync()
        self.assertEqual(len(self.connection.device_ids), 1)
        self.assertFalse(self.connection.device_ids.present)
        self.assertFalse(self.connection.device_ids.online)

    def test_revoke_fetches_uncached_remote_resources(self):
        self.connection.action_activate()
        self.keys = [{"id": "20", "user": {"id": "7"}}, {"id": "21", "user": {"id": "8"}}]
        self.nodes = [{"id": "30", "user": {"id": "7"}}, {"id": "31", "user": {"id": "8"}}]
        self.connection.action_revoke()
        self.assertEqual(self.connection.state, "revoked")
        self.assertIn(("POST", "/preauthkey/expire", {"id": "20"}), self.calls)
        self.assertNotIn(("POST", "/preauthkey/expire", {"id": "21"}), self.calls)
        self.assertEqual([n["id"] for n in self.nodes], ["31"])

    def test_revoke_failure_does_not_report_success(self):
        self.connection.action_activate()
        with patch.object(type(self.server), "_request", side_effect=UserError("Unavailable")):
            with self.assertRaises(UserError):
                self.connection.action_revoke()
        self.assertEqual(self.connection.state, "active")

    def test_archiving_employee_revokes_access(self):
        self.connection.action_activate()
        self.employee.write({"active": False})
        self.assertEqual(self.connection.state, "revoked")

    def test_archiving_odoo_user_revokes_access(self):
        self.connection.action_activate()
        self.employee_user.write({"active": False})
        self.assertEqual(self.connection.state, "revoked")

    def test_archiving_without_connections(self):
        employee = self.env["hr.employee"].create({"name": "No VPN"})
        employee.write({"active": False})
        self.assertFalse(employee.active)

    def test_archive_rolls_back_when_headscale_unavailable(self):
        self.connection.action_activate()
        with patch.object(type(self.server), "_request", side_effect=UserError("Unavailable")):
            with self.assertRaises(UserError), self.env.cr.savepoint():
                self.employee.write({"active": False})
        self.assertTrue(self.employee.active)
        self.assertEqual(self.connection.state, "active")

    def test_ordinary_employee_cannot_manage_or_read_credentials(self):
        connection = self.connection.with_user(self.employee_user)
        for method in (connection.action_activate, connection.action_enroll, connection.action_revoke, connection.action_sync):
            with self.assertRaises(AccessError):
                method()
        with self.assertRaises(AccessError):
            self.server.with_user(self.employee_user).action_test_connection()
        self.assertFalse(self.calls)

    def test_remote_identifiers_and_state_cannot_be_forged(self):
        for vals in ({"state": "active"}, {"remote_user_id": "999"}, {"device_ids": []}):
            with self.assertRaises(UserError):
                self.connection.write(vals)
        with self.assertRaises(UserError):
            self.env["oduscale.connection"].with_user(self.manager).with_context(default_remote_user_id="999").create({
                "employee_id": self.employee.id, "server_id": self.server.id,
            })
        self.connection.action_activate()
        with self.assertRaises(UserError):
            self.connection.write({"employee_id": self.employee.id})
        with self.assertRaises(UserError):
            self.connection.unlink()
        with self.assertRaises(AccessError):
            self.env["oduscale.device"].with_user(self.manager).create({
                "connection_id": self.connection.id, "remote_id": "999", "name": "fake",
            })

    def test_cross_company_access_denied(self):
        other = self.env["res.company"].create({"name": "Other VPN Company"})
        server = self.server.copy({"company_id": other.id})
        with self.assertRaises(AccessError):
            server.with_user(self.manager).action_test_connection()
        with self.assertRaises(AccessError):
            self.server.with_user(self.manager).write({"api_url": "https://attacker.example"})

    def test_device_reassigned_remotely_is_not_deleted(self):
        self.connection.action_activate()
        device = self.env["oduscale.device"].create({
            "connection_id": self.connection.id, "remote_id": "30", "name": "laptop",
        }).with_user(self.manager)
        self.nodes = [{"id": "30", "user": {"id": "8"}}]
        with self.assertRaises(UserError):
            device.action_revoke()
        self.assertTrue(device.present)
        self.assertFalse(any(method == "DELETE" for method, path, payload in self.calls))

    def test_http_errors_are_redacted_and_redirects_disabled(self):
        self.api_patch.stop()
        with patch.dict("os.environ", {"ODUSCALE_API_KEY": "secret-api-token"}):
            with patch("odoo.addons.oduscale.models.server.requests.request") as request:
                request.return_value = Mock(status_code=401, content=b"secret-response-body")
                with self.assertRaises(UserError) as error:
                    self.server._request("GET", "/user")
                self.assertNotIn("secret", str(error.exception))
                self.assertFalse(request.call_args.kwargs["allow_redirects"])
                self.assertEqual(request.call_args.kwargs["timeout"], (5, 20))
                request.side_effect = requests.Timeout("secret-transport-details")
                with self.assertRaises(UserError) as error:
                    self.server._request("GET", "/user")
                self.assertNotIn("secret", str(error.exception))

    def test_configuration_rejects_insecure_login_and_long_key_ttl(self):
        for vals in ({"login_url": "http://headscale.example.com"}, {"key_lifetime_minutes": 10080}):
            with self.assertRaises(ValidationError), self.env.cr.savepoint():
                self.server.write(vals)
