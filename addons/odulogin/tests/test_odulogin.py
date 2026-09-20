from types import SimpleNamespace

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import Session, _request_stack
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user

from ..models.session import ORIGIN_UID_KEY


@tagged("post_install", "-at_install")
class TestOduLogin(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = new_test_user(
            cls.env,
            login="odulogin_admin",
            groups="base.group_system",
            name="OduLogin Administrator",
        )
        cls.target = new_test_user(
            cls.env,
            login="odulogin_target",
            groups="base.group_user",
            name="OduLogin Target",
        )
        cls.regular = new_test_user(
            cls.env,
            login="odulogin_regular",
            groups="base.group_user",
            name="OduLogin Regular",
        )
        cls.portal = new_test_user(
            cls.env,
            login="odulogin_portal",
            groups="base.group_portal",
            name="OduLogin Portal",
        )

    def _push_request(self, user, extra=None):
        user_env = self.env(user=user.id, su=False)
        context = dict(user_env["res.users"].context_get())
        data = {
            "db": self.env.cr.dbname,
            "uid": user.id,
            "login": user.login,
            "context": context,
        }
        data.update(extra or {})
        session = Session(data, sid="odulogin-test-session")
        session.session_token = user._compute_session_token(session.sid)
        fake_request = SimpleNamespace(
            session=session, env=user_env, cookies={},
            db=self.env.cr.dbname, registry=self.env.registry,
            httprequest=SimpleNamespace(cookies={}),
        )

        def update_env(*, user=None, context=None, su=None):
            fake_request.env = fake_request.env(user=user, context=context, su=su)

        fake_request.update_env = update_env
        _request_stack.push(fake_request)
        self.addCleanup(_request_stack.pop)
        return fake_request

    def _wizard(self, actor, target=None):
        return self.env["odulogin.switch.wizard"].with_user(actor).create(
            {"user_id": (target or self.target).id}
        )

    def test_administrator_can_switch_and_return(self):
        fake_request = self._push_request(self.admin)

        action = self._wizard(self.admin).action_switch()

        self.assertEqual(action, {"type": "ir.actions.client", "tag": "reload"})
        self.assertEqual(fake_request.session[ORIGIN_UID_KEY], self.admin.id)
        self.assertEqual(fake_request.session.uid, self.target.id)
        self.assertEqual(fake_request.session.login, self.target.login)
        self.assertEqual(fake_request.env.uid, self.target.id)
        self.assertTrue(fake_request.session.should_rotate)
        self.assertEqual(
            fake_request.session.session_token,
            self.target._compute_session_token(fake_request.session.sid),
        )

        result = self.env["odulogin.session"].with_user(self.target).switch_back()

        self.assertTrue(result)
        self.assertNotIn(ORIGIN_UID_KEY, fake_request.session)
        self.assertEqual(fake_request.session.uid, self.admin.id)
        self.assertEqual(fake_request.session.login, self.admin.login)
        self.assertEqual(fake_request.env.uid, self.admin.id)
        self.assertTrue(fake_request.session.should_rotate)
        self.assertEqual(
            fake_request.session.session_token,
            self.admin._compute_session_token(fake_request.session.sid),
        )

    def test_regular_user_cannot_start_switch(self):
        self._push_request(self.regular)
        wizard = self.env["odulogin.switch.wizard"].sudo().create(
            {"user_id": self.target.id}
        )

        with self.assertRaisesRegex(AccessError, "Only settings administrators"):
            wizard.with_user(self.regular).action_switch()

    def test_nested_switch_is_rejected(self):
        self._push_request(self.admin, {ORIGIN_UID_KEY: self.regular.id})

        with self.assertRaisesRegex(UserError, "before switching again"):
            self._wizard(self.admin).action_switch()

    def test_invalid_targets_are_rejected(self):
        inactive = new_test_user(
            self.env,
            login="odulogin_inactive",
            groups="base.group_user",
        )
        inactive.active = False
        fake_request = self._push_request(self.admin)

        for target, message in (
            (self.admin, "other than yourself"),
            (self.portal, "active internal users"),
            (inactive, "active internal users"),
            (self.env.ref("base.user_root"), "technical superuser"),
        ):
            with self.subTest(target=target.display_name), self.assertRaisesRegex(
                ValidationError, message
            ):
                self._wizard(self.admin, target).action_switch()
            self.assertNotIn(ORIGIN_UID_KEY, fake_request.session)
            self.assertEqual(fake_request.session.uid, self.admin.id)

    def test_switch_back_requires_switched_session(self):
        self._push_request(self.target)

        with self.assertRaisesRegex(UserError, "not switched"):
            self.env["odulogin.session"].with_user(self.target).switch_back()

    def test_session_info_exposes_only_needed_state(self):
        fake_request = self._push_request(self.admin)

        info = self.env["ir.http"].with_user(self.admin).session_info()
        self.assertTrue(info["odulogin_can_switch"])
        self.assertFalse(info["odulogin_is_switched"])
        self.assertNotIn("odulogin_origin_name", info)

        fake_request.session[ORIGIN_UID_KEY] = self.admin.id
        fake_request.session.uid = self.target.id
        fake_request.env = self.env(user=self.target.id, su=False)
        info = self.env["ir.http"].with_user(self.target).session_info()
        self.assertFalse(info["odulogin_can_switch"])
        self.assertTrue(info["odulogin_is_switched"])
        self.assertEqual(info["odulogin_origin_name"], self.admin.name)

    def test_user_domain_contains_only_switchable_accounts(self):
        wizard = self.env["odulogin.switch.wizard"].with_user(self.admin)
        users = self.env["res.users"].with_user(self.admin).search(wizard._user_domain())

        self.assertIn(self.target, users)
        self.assertNotIn(self.admin, users)
        self.assertNotIn(self.portal, users)
        self.assertNotIn(self.env.ref("base.user_root"), users)
