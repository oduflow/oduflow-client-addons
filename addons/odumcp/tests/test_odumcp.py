import html
import json
import re
import time
import uuid
from datetime import timedelta
from lxml import etree
from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import _request_stack
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import DotDict


@tagged("post_install", "-at_install")
class TestOduMcp(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.country = cls.env.ref("base.us")
        cls.category = cls.env["res.partner.category"].create(
            {"name": "MCP Test"}
        )
        cls.allowed_partner = cls.env["res.partner"].create(
            {
                "name": "Allowed Partner",
                "email": "allowed@example.com",
                "country_id": cls.country.id,
                "category_id": [Command.set(cls.category.ids)],
            }
        )
        cls.denied_partner = cls.env["res.partner"].create(
            {
                "name": "Denied Partner",
                "email": "denied@example.com",
                "country_id": cls.country.id,
                "category_id": [Command.set(cls.category.ids)],
            }
        )
        partner_model = cls.env["ir.model"]._get("res.partner")
        partner_fields = cls.env["ir.model.fields"].search(
            [
                ("model_id", "=", partner_model.id),
                ("name", "in", ["name", "email", "country_id", "category_id"]),
            ]
        )
        cls.name_field = partner_fields.filtered(lambda field: field.name == "name")
        cls.mcp_user = cls.env["res.users"].create(
            {
                "name": "MCP Test User",
                "login": "mcp-test-user@example.com",
                "group_ids": [
                    Command.set(
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref("base.group_partner_manager").id,
                        ]
                    )
                ],
            }
        )
        cls.profile = cls.env["odumcp.profile"].create(
            {
                "name": "Test MCP Profile",
                "code": "test_profile",
                "max_records_per_call": 10,
                "max_batch_size": 5,
            }
        )
        cls.mcp_user.write(
            {
                "mcp_active": True,
                "mcp_profile_id": cls.profile.id,
            }
        )
        cls.policy = cls.env["odumcp.model.policy"].create(
            {
                "profile_id": cls.profile.id,
                "model_id": partner_model.id,
                "allow_read": True,
                "allow_create": True,
                "allow_write": True,
                "allow_unlink": False,
                "forced_domain_json": json.dumps(
                    [["id", "=", cls.allowed_partner.id]]
                ),
                "read_field_ids": [Command.set(cls.name_field.ids)],
                "write_field_ids": [
                    Command.set(
                        partner_fields.filtered(
                            lambda field: field.name
                            in {"name", "country_id", "category_id"}
                        ).ids
                    )
                ],
            }
        )
        cls.access = cls.mcp_user.sudo()
        cls.token = cls.env["res.users.apikeys"].with_user(cls.mcp_user)._generate(
            "mcp",
            "MCP test key",
        expiration_date=fields.Datetime.now() + timedelta(hours=1),)
        cls.service = cls.env["odumcp.service"]

    def _request(self, operation, params=None, request_id="00000000-0000-4000-8000-000000000001"):
        return self.service.execute_request(
            self.access,
            operation,
            params or {},
            request_id,
            remote_ip="127.0.0.1",
            user_agent="odoo-test",
        )

    def _approve(self, approval_id):
        approval = self.env["odumcp.approval"].search(
            [("request_uid", "=", approval_id)]
        )
        approval.action_approve()
        return approval

    def test_profile_policy_lists_open_detailed_forms(self):
        view = self.env.ref("odumcp.view_odumcp_profile_form")
        arch = etree.fromstring(view.arch_db.encode())

        expected_form_fields = {
            "policy_ids": {"read_field_ids", "write_field_ids"},
            "method_policy_ids": {
                "allow_model_method",
                "allow_positional_arguments",
                "allowed_keyword_arguments",
                "requires_approval",
            },
        }
        for relation_name, expected_fields in expected_form_fields.items():
            relation = arch.xpath("//field[@name='%s']" % relation_name)[0]
            tree = relation.xpath("./list")[0]
            form = relation.xpath("./form")[0]
            form_fields = set(form.xpath(".//field/@name"))

            self.assertFalse(tree.get("editable"))
            self.assertTrue(expected_fields <= form_fields)

    def test_field_policy_lists_are_limited_to_the_policy_model(self):
        """Домен обязан жить на самом поле: диалог "Search More" читает его
        оттуда, а не из tree-вьюхи политик."""
        descriptions = self.env["odumcp.model.policy"].fields_get(
            ["read_field_ids", "write_field_ids"],
            attributes=["domain"],
        )

        for name in ("read_field_ids", "write_field_ids"):
            self.assertEqual(
                descriptions[name]["domain"],
                "[('model_id', '=', model_id)]",
                "%s must be filtered by the policy model" % name,
            )

    def test_mcp_fields_extend_existing_account_security_tab(self):
        view = self.env.ref("odumcp.view_users_form_odumcp")
        arch = etree.fromstring(view.arch_db.encode())

        self.assertEqual(view.inherit_id, self.env.ref("base.view_users_form"))
        self.assertEqual(
            arch.xpath("//xpath[@expr=\"//page[@name='page_security']\"]/@position"),
            ["inside"],
        )
        self.assertEqual(
            set(arch.xpath("//field/@name")),
            {"mcp_active", "mcp_profile_id"},
        )

    def test_mcp_api_key_and_access_resolution(self):
        global_token = self.env["res.users.apikeys"].with_user(self.mcp_user)._generate(
            None,
            "Global test key",
        expiration_date=fields.Datetime.now() + timedelta(hours=1),)
        user_id = self.env["res.users.apikeys"]._check_mcp_credentials(self.token)
        global_user_id = self.env["res.users.apikeys"]._check_mcp_credentials(global_token)
        rpc_user_id = self.env["res.users.apikeys"]._check_credentials(
            scope="rpc",
            key=self.token,
        )
        access, error = self.env["res.users"]._mcp_for_user(self.mcp_user)

        self.assertEqual(user_id, self.mcp_user.id)
        self.assertFalse(global_user_id)
        self.assertFalse(rpc_user_id)
        self.assertFalse(error)
        self.assertEqual(access, self.access)

    def test_key_wizard_can_create_mcp_key(self):
        fake_request = DotDict({
            "httprequest": DotDict({
                "environ": {"REMOTE_ADDR": "localhost"},
                "cookies": {},
            }),
            "session": {"identity-check-last": time.time()},
        })
        _request_stack.push(fake_request)
        self.addCleanup(_request_stack.pop)
        action = self.env["res.users.apikeys.description"].with_user(
            self.mcp_user
        ).create({
            "name": "External MCP client",
            "scope_mode": "mcp",
        }).make_key()
        token = action["context"]["default_key"]
        key = self.env["res.users.apikeys"]._find_for_token(
            self.mcp_user, token
        )

        self.assertEqual(key.scope, "mcp")

    def _new_user(self, login):
        return self.env["res.users"].create({
            "name": "MCP Key User",
            "login": login,
            "group_ids": [Command.set([self.env.ref("base.group_user").id])],
        })

    def test_enabling_mcp_access_does_not_issue_a_permanent_key(self):
        user = self._new_user("mcp-key-enable@example.com")
        api_keys = self.env["res.users.apikeys"].sudo()

        user.write({"mcp_active": True, "mcp_profile_id": self.profile.id})

        self.assertFalse(api_keys.search([("user_id", "=", user.id)]))

    def test_created_user_with_mcp_access_gets_no_permanent_key(self):
        user = self.env["res.users"].create({
            "name": "MCP Created User",
            "login": "mcp-key-create@example.com",
            "group_ids": [Command.set([self.env.ref("base.group_user").id])],
            "mcp_active": True,
            "mcp_profile_id": self.profile.id,
        })

        self.assertFalse(self.env["res.users.apikeys"].sudo().search([
            ("user_id", "=", user.id),
        ]))

    def test_disabling_mcp_access_keeps_personal_key(self):
        user = self._new_user("mcp-key-manual@example.com")
        token = self.env["res.users.apikeys"].with_user(user)._generate(
            "mcp", "External MCP client", expiration_date=fields.Datetime.now() + timedelta(hours=1),)
        manual = self.env["res.users.apikeys"]._find_for_token(user, token)

        user.write({"mcp_active": True, "mcp_profile_id": self.profile.id})
        user.write({"mcp_active": False})

        self.assertTrue(manual.exists())

    def test_unassigning_user_from_profile_revokes_access(self):
        user = self._new_user("mcp-key-unassign@example.com")
        user.write({"mcp_active": True, "mcp_profile_id": self.profile.id})

        self.profile.assigned_user_ids = self.profile.user_ids - user

        self.assertFalse(user.mcp_profile_id)
        self.assertFalse(user.mcp_active)

    def test_obsolete_ai_chat_key_markers_are_removed(self):
        api_key_fields = self.env["res.users.apikeys"]._fields
        wizard_fields = self.env["res.users.apikeys.description"]._fields

        self.assertNotIn("ai_chat_default", api_key_fields)
        self.assertNotIn("mcp_managed", api_key_fields)
        self.assertNotIn("ai_chat_default", wizard_fields)

    def test_event_ticket_is_hashed_and_bound_to_user(self):
        Ticket = self.env["odumcp.event.ticket"]
        token = Ticket._issue(self.access)
        ticket = Ticket.sudo().search(
            [("token_hash", "=", Ticket._digest(token))],
            limit=1,
        )
        expires_at = ticket.expires_at

        self.assertTrue(ticket)
        self.assertNotEqual(ticket.token_hash, token)
        self.assertEqual(Ticket._check(token).user_id, self.access)
        ticket.invalidate_recordset(["expires_at"])
        self.assertEqual(ticket.expires_at, expires_at)
        self.assertFalse(Ticket._check("invalid-ticket"))

    def test_resource_update_uses_private_channel_and_version(self):
        previous_version = self.access.mcp_event_version
        version = self.access._publish_mcp_resource_update(
            "odoo://approval/00000000-0000-4000-8000-000000000001"
        )
        self.env.cr.precommit.run()
        message = self.env["bus.bus"].sudo().search([], order="id desc", limit=1)
        wire_message = json.loads(message.message)

        self.assertEqual(version, previous_version + 1)
        self.assertEqual(
            json.loads(message.channel),
            [self.env.cr.dbname, self.access.mcp_event_channel],
        )
        self.assertEqual(wire_message["type"], "odumcp_resource_updated")
        self.assertEqual(wire_message["payload"]["version"], version)
        self.assertEqual(
            wire_message["payload"]["uri"],
            "odoo://approval/00000000-0000-4000-8000-000000000001",
        )

    def test_mcp_access_is_configured_on_user(self):
        self.assertNotIn("odumcp.access", self.env)
        self.assertTrue(self.mcp_user.mcp_active)
        self.assertEqual(self.mcp_user.mcp_profile_id, self.profile)
        self.assertNotIn("request_count", self.mcp_user._fields)
        self.assertNotIn("failure_count", self.mcp_user._fields)
        self.assertNotIn("last_used_at", self.mcp_user._fields)

    def test_profile_can_assign_existing_users(self):
        other_profile = self.env["odumcp.profile"].create(
            {
                "name": "Other MCP Profile",
                "code": "other_profile",
            }
        )
        existing_user = self.env["res.users"].create(
            {
                "name": "Existing MCP User",
                "login": "existing-mcp-user@example.com",
                "mcp_profile_id": other_profile.id,
            }
        )

        self.profile.assigned_user_ids = existing_user

        self.assertEqual(existing_user.mcp_profile_id, self.profile)
        self.assertFalse(self.mcp_user.mcp_profile_id)

        view = self.env.ref("odumcp.view_odumcp_profile_form")
        arch = etree.fromstring(view.arch_db.encode())
        field = arch.xpath("//page[@name='users']/field")[0]
        self.assertEqual(field.get("name"), "assigned_user_ids")
        self.assertIn("'no_create': True", field.get("options"))

    def test_forced_domain_and_field_policy(self):
        body, status = self._request(
            "records.search",
            {
                "model": "res.partner",
                "domain": [],
                "fields": ["name"],
                "limit": 10,
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(
            [record["id"] for record in body["data"]["records"]],
            [self.allowed_partner.id],
        )

        body, status = self._request(
            "records.search",
            {
                "model": "res.partner",
                "domain": [["id", "=", self.denied_partner.id]],
                "fields": ["name"],
                "limit": 10,
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["data"]["records"], [])

        body, status = self._request(
            "records.read",
            {
                "model": "res.partner",
                "ids": [self.allowed_partner.id],
                "fields": ["email"],
            },
        )
        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["code"], "field_denied")

    def test_domain_cannot_filter_on_fields_outside_the_read_allowlist(self):
        body, status = self._request(
            "records.count",
            {
                "model": "res.partner",
                "domain": [["email", "=", "denied@example.com"]],
            },
        )

        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["code"], "field_denied")

    def test_domain_cannot_traverse_relations_to_denied_fields(self):
        partner_model = self.env["ir.model"]._get("res.partner")
        country_field = self.env["ir.model.fields"].search(
            [("model_id", "=", partner_model.id), ("name", "=", "country_id")],
            limit=1,
        )
        self.policy.read_field_ids = [Command.link(country_field.id)]

        denied, denied_status = self._request(
            "records.count",
            {"model": "res.partner", "domain": [["country_id.code", "=", "US"]]},
        )

        self.assertEqual(denied_status, 403)
        self.assertEqual(denied["error"]["code"], "field_denied")

        country_model = self.env["ir.model"]._get("res.country")
        country_name_field = self.env["ir.model.fields"].search(
            [("model_id", "=", country_model.id), ("name", "=", "name")],
            limit=1,
        )
        self.env["odumcp.model.policy"].create(
            {
                "profile_id": self.profile.id,
                "model_id": country_model.id,
                "allow_read": True,
                "read_field_ids": [Command.set(country_name_field.ids)],
            }
        )

        still_denied, still_denied_status = self._request(
            "records.count",
            {"model": "res.partner", "domain": [["country_id.code", "=", "US"]]},
        )
        allowed, allowed_status = self._request(
            "records.count",
            {
                "model": "res.partner",
                "domain": [["country_id.name", "=", self.country.name]],
            },
        )

        self.assertEqual(still_denied_status, 403)
        self.assertEqual(still_denied["error"]["code"], "field_denied")
        self.assertEqual(allowed_status, 200)
        self.assertEqual(allowed["data"]["count"], 1)

    def test_unknown_field_name_is_not_reported_as_a_policy_denial(self):
        body, status = self._request(
            "records.read",
            {
                "model": "res.partner",
                "ids": [self.allowed_partner.id],
                "fields": ["name", "use_partner_credit_limit"],
            },
        )

        self.assertEqual(status, 422)
        self.assertEqual(body["error"]["code"], "unknown_field")
        self.assertEqual(
            body["error"]["data"]["unknown_fields"],
            ["use_partner_credit_limit"],
        )
        self.assertEqual(body["error"]["data"]["denied_fields"], [])
        self.assertIn("use_partner_credit_limit", body["error"]["message"])

    def test_field_denial_names_the_fields_it_refused(self):
        body, status = self._request(
            "records.read",
            {
                "model": "res.partner",
                "ids": [self.allowed_partner.id],
                "fields": ["name", "email"],
            },
        )

        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["code"], "field_denied")
        self.assertEqual(body["error"]["data"]["model"], "res.partner")
        self.assertEqual(body["error"]["data"]["denied_fields"], ["email"])

    def test_unknown_field_wins_over_denied_field_in_the_same_call(self):
        body, status = self._request(
            "records.read",
            {
                "model": "res.partner",
                "ids": [self.allowed_partner.id],
                "fields": ["email", "use_partner_credit_limit"],
            },
        )

        self.assertEqual(status, 422)
        self.assertEqual(body["error"]["code"], "unknown_field")
        self.assertEqual(body["error"]["data"]["denied_fields"], ["email"])

    def test_unavailable_record_ids_are_listed_in_the_error(self):
        body, status = self._request(
            "records.read",
            {
                "model": "res.partner",
                "ids": [self.allowed_partner.id, self.denied_partner.id],
                "fields": ["name"],
            },
        )

        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["code"], "access_denied")
        self.assertEqual(
            body["error"]["data"]["denied_ids"],
            [self.denied_partner.id],
        )

    def test_write_values_separate_unknown_from_denied_fields(self):
        denied, denied_status = self._request(
            "changes.preview",
            {
                "action": "record.update",
                "payload": {
                    "model": "res.partner",
                    "ids": [self.allowed_partner.id],
                    "values": {"email": "new@example.com"},
                },
                "idempotency_key": "write-denied-field-0001",
            },
        )
        unknown, unknown_status = self._request(
            "changes.preview",
            {
                "action": "record.update",
                "payload": {
                    "model": "res.partner",
                    "ids": [self.allowed_partner.id],
                    "values": {"use_partner_credit_limit": True},
                },
                "idempotency_key": "write-unknown-field-0001",
            },
        )

        self.assertEqual(denied_status, 403)
        self.assertEqual(denied["error"]["code"], "field_denied")
        self.assertEqual(denied["error"]["data"]["denied_fields"], ["email"])
        self.assertEqual(unknown_status, 422)
        self.assertEqual(unknown["error"]["code"], "unknown_field")
        self.assertEqual(
            unknown["error"]["data"]["unknown_fields"],
            ["use_partner_credit_limit"],
        )

    def test_domain_and_order_report_unknown_fields_as_such(self):
        domain_body, domain_status = self._request(
            "records.count",
            {
                "model": "res.partner",
                "domain": [["use_partner_credit_limit", "=", True]],
            },
        )
        order_body, order_status = self._request(
            "records.search",
            {
                "model": "res.partner",
                "domain": [],
                "fields": ["name"],
                "order": "use_partner_credit_limit desc",
            },
        )

        self.assertEqual(domain_status, 422)
        self.assertEqual(domain_body["error"]["code"], "unknown_field")
        self.assertEqual(order_status, 422)
        self.assertEqual(order_body["error"]["code"], "unknown_field")

    def test_missing_record_is_not_reported_as_access_denied(self):
        missing_partner = self.env["res.partner"].create(
            {
                "name": "Gone",
                "country_id": self.country.id,
                "category_id": [Command.set(self.category.ids)],
            }
        )
        missing_id = missing_partner.id
        missing_partner.unlink()

        body, status = self._request(
            "records.read",
            {
                "model": "res.partner",
                "ids": [missing_id],
                "fields": ["name"],
            },
        )

        self.assertEqual(status, 404)
        self.assertEqual(body["error"]["code"], "record_not_found")
        self.assertEqual(body["error"]["data"]["missing_ids"], [missing_id])
        self.assertEqual(body["error"]["data"]["denied_ids"], [])
        audit = self.env["odumcp.audit.log"].search(
            [("error_code", "=", "record_not_found")],
            limit=1,
        )
        self.assertEqual(audit.error_class, "McpServiceError")

    def test_missing_and_denied_record_ids_are_classified_in_one_error(self):
        missing_partner = self.env["res.partner"].create(
            {
                "name": "Gone",
                "country_id": self.country.id,
                "category_id": [Command.set(self.category.ids)],
            }
        )
        missing_id = missing_partner.id
        missing_partner.unlink()

        body, status = self._request(
            "records.read",
            {
                "model": "res.partner",
                "ids": [
                    self.allowed_partner.id,
                    self.denied_partner.id,
                    missing_id,
                ],
                "fields": ["name"],
            },
        )

        self.assertEqual(status, 404)
        self.assertEqual(body["error"]["code"], "record_not_found")
        self.assertEqual(body["error"]["data"]["missing_ids"], [missing_id])
        self.assertEqual(
            body["error"]["data"]["denied_ids"],
            [self.denied_partner.id],
        )

    def test_partial_reads_are_off_until_the_profile_enables_them(self):
        body, status = self._request(
            "records.read",
            {
                "model": "res.partner",
                "ids": [self.allowed_partner.id],
                "fields": ["name", "email"],
            },
        )

        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["code"], "field_denied")

    def test_partial_read_returns_the_readable_part_and_names_the_rest(self):
        self.profile.allow_partial_field_reads = True

        body, status = self._request(
            "records.read",
            {
                "model": "res.partner",
                "ids": [self.allowed_partner.id],
                "fields": ["name", "email", "use_partner_credit_limit"],
            },
        )

        self.assertEqual(status, 200)
        self.assertEqual(
            body["data"]["records"],
            [{"id": self.allowed_partner.id, "name": self.allowed_partner.name}],
        )
        omitted = body["data"]["omitted_fields"]
        self.assertEqual(omitted["denied"], ["email"])
        self.assertEqual(omitted["unknown"], ["use_partner_credit_limit"])
        self.assertIn("email", omitted["note"])
        audit = self.env["odumcp.audit.log"].search(
            [("request_id", "=", "00000000-0000-4000-8000-000000000001")],
            limit=1,
            order="id desc",
        )
        self.assertEqual(audit.outcome, "success")
        self.assertEqual(
            audit.omitted_fields,
            "denied=email; unknown=use_partner_credit_limit",
        )

    def test_partial_read_still_fails_when_nothing_readable_is_left(self):
        self.profile.allow_partial_field_reads = True

        body, status = self._request(
            "records.read",
            {
                "model": "res.partner",
                "ids": [self.allowed_partner.id],
                "fields": ["email"],
            },
        )

        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["code"], "field_denied")
        self.assertEqual(body["error"]["data"]["denied_fields"], ["email"])

    def test_partial_reads_never_trim_a_domain_an_order_or_a_write(self):
        self.profile.allow_partial_field_reads = True

        domain_body, domain_status = self._request(
            "records.search",
            {
                "model": "res.partner",
                "domain": [["email", "=", "denied@example.com"]],
                "fields": ["name"],
            },
        )
        order_body, order_status = self._request(
            "records.search",
            {"model": "res.partner", "domain": [], "fields": ["name"], "order": "email desc"},
        )
        write_body, write_status = self._request(
            "changes.preview",
            {
                "action": "record.update",
                "payload": {
                    "model": "res.partner",
                    "ids": [self.allowed_partner.id],
                    "values": {"name": "Kept", "email": "new@example.com"},
                },
                "idempotency_key": "partial-write-not-trimmed-0001",
            },
        )

        self.assertEqual(domain_status, 403)
        self.assertEqual(domain_body["error"]["code"], "field_denied")
        self.assertEqual(order_status, 403)
        self.assertEqual(order_body["error"]["code"], "field_denied")
        self.assertEqual(write_status, 403)
        self.assertEqual(write_body["error"]["code"], "field_denied")
        self.assertNotEqual(self.allowed_partner.name, "Kept")

    def test_partial_read_without_a_field_list_is_unchanged(self):
        self.profile.allow_partial_field_reads = True

        body, status = self._request(
            "records.read",
            {"model": "res.partner", "ids": [self.allowed_partner.id]},
        )

        self.assertEqual(status, 200)
        self.assertNotIn("omitted_fields", body["data"])
        self.assertEqual(
            sorted(body["data"]["records"][0]),
            ["display_name", "id", "name"],
        )

    def test_global_read_uses_odoo_access_and_safe_fields(self):
        self.profile.default_model_access = "read"

        body, status = self._request(
            "records.search",
            {
                "model": "res.company",
                "domain": [],
                "fields": ["name"],
                "limit": 10,
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(body["data"]["records"])

        body, status = self._request(
            "records.search",
            {
                "model": "res.users",
                "domain": [["id", "=", self.mcp_user.id]],
                "fields": ["password"],
                "limit": 1,
            },
        )
        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["code"], "field_denied")

    def test_global_access_lists_user_accessible_models(self):
        self.profile.default_model_access = "read"

        body, status = self._request("models.list")

        self.assertEqual(status, 200)
        companies = [
            item for item in body["data"]["models"] if item["model"] == "res.company"
        ]
        self.assertEqual(len(companies), 1)
        self.assertIn("read", companies[0]["operations"])

    def test_explicit_policy_overrides_global_access(self):
        self.profile.default_model_access = "write"
        company_model = self.env["ir.model"]._get("res.company")
        self.env["odumcp.model.policy"].create(
            {
                "profile_id": self.profile.id,
                "model_id": company_model.id,
                "allow_read": False,
                "allow_aggregate": False,
            }
        )

        body, status = self._request(
            "records.search",
            {"model": "res.company", "domain": [], "fields": ["name"]},
        )

        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["code"], "policy_denied")

    def test_global_update_allows_preview_without_model_policy(self):
        self.policy.active = False
        self.profile.default_model_access = "write"

        body, status = self._request(
            "changes.preview",
            {
                "action": "record.update",
                "payload": {
                    "model": "res.partner",
                    "ids": [self.allowed_partner.id],
                    "values": {"name": "Globally writable"},
                },
                "idempotency_key": "global-update-partner",
            },
        )

        self.assertEqual(status, 200)
        self.assertEqual(body["data"]["action"], "record.update")

    def test_global_create_allows_preview_without_model_policy(self):
        self.policy.active = False
        self.profile.allow_global_create = True

        body, status = self._request(
            "changes.preview",
            {
                "action": "record.create",
                "payload": {
                    "model": "res.partner",
                    "values": {"name": "Globally creatable"},
                },
                "idempotency_key": "global-create-partner",
            },
        )

        self.assertEqual(status, 200)
        self.assertEqual(body["data"]["action"], "record.create")

    def test_global_delete_allows_preview_without_model_policy(self):
        self.policy.active = False
        self.profile.allow_global_unlink = True

        body, status = self._request(
            "changes.preview",
            {
                "action": "record.delete",
                "payload": {
                    "model": "res.partner",
                    "ids": [self.allowed_partner.id],
                },
                "idempotency_key": "global-delete-partner",
            },
        )

        self.assertEqual(status, 200)
        self.assertEqual(body["data"]["action"], "record.delete")

    def test_global_access_keeps_security_models_blocked(self):
        self.profile.default_model_access = "read"

        body, status = self._request(
            "records.search",
            {
                "model": "ir.config_parameter",
                "domain": [],
                "fields": ["key"],
                "limit": 1,
            },
        )

        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["code"], "policy_denied")

    def test_global_access_reads_security_models(self):
        self.profile.default_model_access = "write"

        body, status = self._request(
            "records.search",
            {
                "model": "res.groups",
                "domain": [["id", "=", self.env.ref("base.group_user").id]],
                "fields": ["name"],
                "limit": 1,
            },
        )

        self.assertEqual(status, 200)
        self.assertEqual(len(body["data"]["records"]), 1)

    def test_global_access_reads_access_rules_for_an_erp_manager(self):
        self.profile.default_model_access = "read"
        self.mcp_user.sudo().write(
            {"group_ids": [Command.link(self.env.ref("base.group_erp_manager").id)]}
        )

        body, status = self._request(
            "records.search",
            {
                "model": "ir.model.access",
                "domain": [],
                "fields": ["name", "perm_read"],
                "limit": 1,
            },
        )

        self.assertEqual(status, 200)
        self.assertEqual(len(body["data"]["records"]), 1)

    def test_global_access_keeps_security_models_read_only(self):
        self.profile.default_model_access = "write"
        self.profile.allow_global_create = True
        self.profile.allow_global_unlink = True
        group = self.env.ref("base.group_user")

        for action, payload in (
            (
                "record.update",
                {
                    "model": "res.groups",
                    "ids": [group.id],
                    "values": {"name": "Escalated"},
                },
            ),
            (
                "record.create",
                {"model": "ir.model.access", "values": {"name": "Escalated"}},
            ),
            ("record.delete", {"model": "ir.rule", "ids": [1]}),
        ):
            with self.subTest(action=action):
                body, status = self._request(
                    "changes.preview",
                    {
                        "action": action,
                        "payload": payload,
                        "idempotency_key": "security-model-%s" % action,
                    },
                )

                self.assertEqual(status, 403)
                self.assertEqual(body["error"]["code"], "policy_denied")

    def test_global_access_hides_password_like_fields(self):
        self.profile.default_model_access = "read"

        policy = self.profile._get_policy("ir.mail_server", "read", user=self.access)
        allowed = policy._allowed_field_names("read", self.env["ir.mail_server"])

        self.assertIn("smtp_host", allowed)
        self.assertNotIn("smtp_pass", allowed)

    def test_global_write_keeps_users_read_only(self):
        self.profile.default_model_access = "write"

        body, status = self._request(
            "changes.preview",
            {
                "action": "record.update",
                "payload": {
                    "model": "res.users",
                    "ids": [self.mcp_user.id],
                    "values": {"name": "Escalated"},
                },
                "idempotency_key": "global-user-write-denied",
            },
        )

        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["code"], "policy_denied")

    def _preview_update(self, key, batch_key=None):
        params = {
            "action": "record.update",
            "payload": {
                "model": "res.partner",
                "ids": [self.allowed_partner.id],
                "values": {"name": "Changed by MCP"},
            },
            "idempotency_key": key,
        }
        if batch_key is not None:
            params["batch_key"] = batch_key
        body, status = self._request("changes.preview", params)
        self.assertEqual(status, 200, body)
        return body["data"]

    def test_batch_key_groups_plans_into_one_request(self):
        first = self._preview_update("batch-plan-0001", "import-vat")
        second = self._preview_update("batch-plan-0002", "import-vat")
        other = self._preview_update("batch-plan-0003", "import-iban")

        self.assertTrue(first["request"])
        self.assertEqual(first["request"], second["request"])
        self.assertNotEqual(first["request"], other["request"])

    def test_plans_without_batch_key_group_by_arrival_window(self):
        first = self._preview_update("window-plan-0001")
        second = self._preview_update("window-plan-0002")
        self.assertEqual(first["request"], second["request"])

        # Отодвигаем уже созданные планы за пределы окна склейки.
        self.env.cr.execute(
            "UPDATE odumcp_approval SET create_date = create_date - interval '1 day'"
        )
        self.env["odumcp.approval"].invalidate_recordset()

        third = self._preview_update("window-plan-0003")
        self.assertNotEqual(first["request"], third["request"])

    def test_zero_window_puts_every_plan_in_its_own_request(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "odumcp.request_window_minutes", "0"
        )
        first = self._preview_update("solo-plan-0001")
        second = self._preview_update("solo-plan-0002")

        self.assertNotEqual(first["request"], second["request"])

    def test_invalid_batch_key_is_refused(self):
        body, status = self._request(
            "changes.preview",
            {
                "action": "record.update",
                "payload": {
                    "model": "res.partner",
                    "ids": [self.allowed_partner.id],
                    "values": {"name": "Changed by MCP"},
                },
                "idempotency_key": "bad-batch-key-0001",
                "batch_key": 42,
            },
        )

        self.assertEqual(status, 400)
        self.assertEqual(body["error"]["code"], "invalid_batch_key")

    def test_preview_approval_and_exactly_once_execution(self):
        body, status = self._request(
            "changes.preview",
            {
                "action": "record.update",
                "payload": {
                    "model": "res.partner",
                    "ids": [self.allowed_partner.id],
                    "values": {"name": "Changed by MCP"},
                },
                "idempotency_key": "update-partner-0001",
            },
        )
        self.assertEqual(status, 200)
        approval_id = body["data"]["approval_id"]
        self.assertEqual(body["data"]["state"], "pending")

        body, status = self._request(
            "changes.execute",
            {"approval_id": approval_id},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["data"]["state"], "pending")
        self.assertEqual(self.allowed_partner.name, "Allowed Partner")

        approval = self.env["odumcp.approval"].search(
            [("request_uid", "=", approval_id)]
        )
        approval.action_approve()
        body, status = self._request(
            "changes.execute",
            {"approval_id": approval_id},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["data"]["state"], "executed")
        self.assertEqual(self.allowed_partner.name, "Changed by MCP")

        first_result = body["data"]["result"]
        body, status = self._request(
            "changes.execute",
            {"approval_id": approval_id},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["data"]["result"], first_result)
        self.assertEqual(approval.state, "executed")

    def test_idempotency_conflict(self):
        common = {
            "action": "record.update",
            "idempotency_key": "update-partner-conflict",
        }
        body, status = self._request(
            "changes.preview",
            {
                **common,
                "payload": {
                    "model": "res.partner",
                    "ids": [self.allowed_partner.id],
                    "values": {"name": "First"},
                },
            },
        )
        self.assertEqual(status, 200)
        first_id = body["data"]["approval_id"]

        body, status = self._request(
            "changes.preview",
            {
                **common,
                "payload": {
                    "model": "res.partner",
                    "ids": [self.allowed_partner.id],
                    "values": {"name": "Second"},
                },
            },
        )
        self.assertEqual(status, 409)
        self.assertEqual(body["error"]["code"], "idempotency_conflict")

        body, status = self._request(
            "changes.preview",
            {
                **common,
                "payload": {
                    "model": "res.partner",
                    "ids": [self.allowed_partner.id],
                    "values": {"name": "First"},
                },
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["data"]["approval_id"], first_id)

    def test_audit_is_redacted_and_immutable(self):
        self._request(
            "records.count",
            {"model": "res.partner", "domain": []},
            request_id="00000000-0000-4000-8000-000000000099",
        )
        audit = self.env["odumcp.audit.log"].search(
            [("request_id", "=", "00000000-0000-4000-8000-000000000099")]
        )
        self.assertTrue(audit)
        self.assertNotIn(self.token, audit.input_summary or "")
        with self.assertRaises(AccessError):
            audit.write({"duration_ms": 0})
        with self.assertRaises(AccessError):
            audit.unlink()

    def test_inactive_access_is_rejected(self):
        self.mcp_user.mcp_active = False
        access, error = self.env["res.users"]._mcp_for_user(self.mcp_user)
        self.assertFalse(access)
        self.assertEqual(error, "inactive_mcp_access")
        self.mcp_user.mcp_active = True

    def test_mcp_api_key_is_rejected_for_inactive_user(self):
        token = self.env["res.users.apikeys"].with_user(self.mcp_user)._generate(
            "mcp",
            "Inactive user MCP test key",
        expiration_date=fields.Datetime.now() + timedelta(hours=1),)
        self.mcp_user.active = False
        try:
            user_id = self.env["res.users.apikeys"]._check_mcp_credentials(token)
            self.assertFalse(user_id)
        finally:
            self.mcp_user.active = True

    def test_rate_limit_is_enforced_per_access(self):
        self.profile.rate_limit_per_minute = 1
        first, first_status = self._request("system.info")
        second, second_status = self._request("system.info")

        self.assertEqual(first_status, 200)
        self.assertTrue(first["ok"])
        self.assertEqual(second_status, 429)
        self.assertEqual(second["error"]["code"], "rate_limit_exceeded")

    def test_create_cannot_escape_forced_domain(self):
        body, status = self._request(
            "changes.preview",
            {
                "action": "record.create",
                "payload": {
                    "model": "res.partner",
                    "values": {
                        "name": "Outside MCP scope",
                        "country_id": self.country.id,
                        "category_id": [Command.set(self.category.ids)],
                    },
                },
                "idempotency_key": "create-outside-scope",
            },
        )
        self.assertEqual(status, 200)
        approval = self._approve(body["data"]["approval_id"])

        body, status = self._request(
            "changes.execute",
            {"approval_id": approval.request_uid},
        )

        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["code"], "policy_postcondition_failed")
        self.assertFalse(
            self.env["res.partner"].search([("name", "=", "Outside MCP scope")])
        )
        self.assertEqual(approval.state, "failed")
        self.assertTrue(approval.error_message)

    def test_update_cannot_move_record_outside_forced_domain(self):
        self.policy.forced_domain_json = json.dumps([["name", "ilike", "Allowed"]])
        body, status = self._request(
            "changes.preview",
            {
                "action": "record.update",
                "payload": {
                    "model": "res.partner",
                    "ids": [self.allowed_partner.id],
                    "values": {"name": "Escaped scope"},
                },
                "idempotency_key": "update-outside-scope",
            },
        )
        self.assertEqual(status, 200)
        approval = self._approve(body["data"]["approval_id"])

        body, status = self._request(
            "changes.execute",
            {"approval_id": approval.request_uid},
        )

        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["code"], "policy_postcondition_failed")
        self.assertEqual(self.allowed_partner.name, "Allowed Partner")
        self.assertEqual(approval.state, "failed")
        self.assertTrue(approval.error_message)

        body, status = self._request(
            "changes.status",
            {"approval_id": approval.request_uid},
        )

        self.assertEqual(status, 200)
        self.assertEqual(body["data"]["state"], "failed")

    def test_method_policy_rejects_unapproved_argument_shapes(self):
        self.env["odumcp.method.policy"].create(
            {
                "profile_id": self.profile.id,
                "model_id": self.policy.model_id.id,
                "method_name": "toggle_active",
                "max_record_count": 1,
            }
        )
        denied, denied_status = self._request(
            "changes.preview",
            {
                "action": "method.call",
                "payload": {
                    "model": "res.partner",
                    "ids": [self.allowed_partner.id],
                    "method": "toggle_active",
                    "args": ["unexpected"],
                },
                "idempotency_key": "method-denied-args",
            },
        )
        allowed, allowed_status = self._request(
            "changes.preview",
            {
                "action": "method.call",
                "payload": {
                    "model": "res.partner",
                    "ids": [self.allowed_partner.id],
                    "method": "toggle_active",
                },
                "idempotency_key": "method-allowed-noargs",
            },
        )

        self.assertEqual(denied_status, 403)
        self.assertEqual(denied["error"]["code"], "policy_denied")
        self.assertEqual(allowed_status, 200)
        self.assertEqual(allowed["data"]["state"], "pending")

    def test_method_policy_can_auto_approve_without_skipping_audit_plan(self):
        self.env["odumcp.method.policy"].create(
            {
                "profile_id": self.profile.id,
                "model_id": self.policy.model_id.id,
                "method_name": "toggle_active",
                "max_record_count": 1,
                "requires_approval": False,
            }
        )

        body, status = self._request(
            "changes.preview",
            {
                "action": "method.call",
                "payload": {
                    "model": "res.partner",
                    "ids": [self.allowed_partner.id],
                    "method": "toggle_active",
                },
                "idempotency_key": "method-direct-audited",
            },
        )

        self.assertEqual(status, 200)
        self.assertEqual(body["data"]["state"], "approved")
        approval = self.env["odumcp.approval"].search(
            [("request_uid", "=", body["data"]["approval_id"])]
        )
        self.assertTrue(approval)
        self.assertFalse(approval.approved_by)

    def test_expired_key_is_rejected_by_both_mcp_lookups(self):
        keys = self.env['res.users.apikeys']
        key = keys._find_for_token(self.mcp_user, self.token)
        self.assertTrue(key)
        self.assertEqual(keys._check_mcp_credentials(self.token), self.mcp_user.id)
        self.env.cr.execute(
            "UPDATE res_users_apikeys SET expiration_date = %s WHERE id = %s",
            [fields.Datetime.now() - timedelta(seconds=1), key.id],
        )
        key.invalidate_recordset(['expiration_date'])
        self.assertFalse(keys._check_mcp_credentials(self.token))
        self.assertFalse(keys._find_for_token(self.mcp_user, self.token))




def _yaml_text(rendered):
    """Убрать разметку подсветки и вернуть чистый YAML."""
    return html.unescape(re.sub(r"<[^>]+>", "", rendered or ""))


@tagged("post_install", "-at_install")
class TestOduMcpYamlPreview(TransactionCase):
    def _approval(self, values):
        base = {
            "user_id": self.env.user.id,
            "profile_id": self.env["odumcp.profile"]
            .create({"name": "YAML Preview Profile", "code": "yaml_preview"})
            .id,
            "action": "record.update",
            "model_name": "res.partner",
            "payload_json": json.dumps({"values": {"vat": "[REDACTED]"}}),
            "payload_hash": "0" * 64,
            "idempotency_key": "yaml-preview",
            "risk_level": "medium",
            "summary": "YAML preview",
            "target_count": 1,
            "expires_at": fields.Datetime.now(),
        }
        base.update(values)
        return self.env["odumcp.approval"].create(base)

    def test_diff_is_rendered_as_yaml_with_highlighting(self):
        diff = [
            {
                "id": 2,
                "display_name": "Task <one>",
                "changes": {
                    "kanban_state": {"old": "normal", "new": "done"},
                    "stage_id": {"old": [1, "New"], "new": 3},
                    "user_id": {"old": None, "new": False},
                },
            }
        ]
        approval = self._approval({"diff_json": json.dumps(diff)})
        rendered = approval.diff_yaml

        self.assertIn('class="o_mcp_yaml_key"', rendered)
        self.assertIn('class="o_mcp_yaml_num"', rendered)
        self.assertIn('class="o_mcp_yaml_const"', rendered)
        # Значения из базы не должны попадать в форму как живая разметка.
        self.assertNotIn("<one>", rendered)

        text = _yaml_text(rendered)
        self.assertIn("- id: 2", text)
        self.assertIn("  changes:", text)
        self.assertIn("      old: normal", text)
        self.assertIn("        - New", text)

        try:
            import yaml
        except ImportError:
            return
        self.assertEqual(yaml.safe_load(text), diff)

    def test_result_and_payload_are_rendered(self):
        approval = self._approval(
            {"result_json": json.dumps({"written": 3, "ids": [2, 158, 5877]})}
        )

        self.assertIn("written", _yaml_text(approval.result_yaml))
        self.assertIn('class="o_mcp_yaml_redacted"', approval.payload_yaml)

    def test_empty_snapshot_stays_empty(self):
        approval = self._approval({})

        self.assertFalse(approval.diff_yaml)
        self.assertFalse(approval.result_yaml)

    def test_invalid_json_is_shown_as_escaped_text(self):
        approval = self._approval({"diff_json": "not json <b>at all</b>"})

        self.assertNotIn("<b>", approval.diff_yaml)
        self.assertIn("not json", approval.diff_yaml)


@tagged("post_install", "-at_install")
class TestOduMcpActivities(TransactionCase):
    """Флаг Allow Activities: свои активности — CRU, удаления нет."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.country = cls.env.ref("base.us")
        cls.category = cls.env["res.partner.category"].create(
            {"name": "MCP Activity Test"}
        )
        partner_model = cls.env["ir.model"]._get("res.partner")
        partner_fields = cls.env["ir.model.fields"].search(
            [("model_id", "=", partner_model.id), ("name", "in", ["name"])]
        )
        cls.mcp_user = cls.env["res.users"].create(
            {
                "name": "Activity MCP User",
                "login": "mcp-activity-user@example.com",
                "group_ids": [
                    Command.set(
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref("base.group_partner_manager").id,
                        ]
                    )
                ],
            }
        )
        cls.other_user = cls.env["res.users"].create(
            {
                "name": "Activity Other User",
                "login": "mcp-activity-other@example.com",
                "group_ids": [Command.set([cls.env.ref("base.group_user").id])],
            }
        )
        cls.partner = (
            cls.env["res.partner"]
            .with_user(cls.mcp_user)
            .sudo()
            .create(
                {
                    "name": "Activity Partner",
                    "country_id": cls.country.id,
                    "category_id": [Command.set(cls.category.ids)],
                }
            )
        )
        cls.profile = cls.env["odumcp.profile"].create(
            {
                "name": "Activity Profile",
                "code": "activity_profile",
                "allow_activities": True,
            }
        )
        cls.env["odumcp.model.policy"].create(
            {
                "profile_id": cls.profile.id,
                "model_id": partner_model.id,
                "allow_read": True,
                "allow_write": True,
                "read_field_ids": [Command.set(partner_fields.ids)],
                "write_field_ids": [Command.set(partner_fields.ids)],
            }
        )
        cls.mcp_user.write(
            {"mcp_active": True, "mcp_profile_id": cls.profile.id}
        )
        cls.access = cls.mcp_user.sudo()
        cls.service = cls.env["odumcp.service"]
        cls.todo_type = cls.env.ref("mail.mail_activity_data_todo")

    def _request(self, operation, params=None, request_id="00000000-0000-4000-8000-0000000000a1"):
        return self.service.execute_request(
            self.access, operation, params or {}, request_id
        )

    def _change(self, action, payload, key):
        body, status = self._request(
            "changes.preview",
            {"action": action, "payload": payload, "idempotency_key": key},
        )
        self.assertEqual(status, 200, body)
        approval_id = body["data"]["approval_id"]
        if body["data"]["state"] == "pending":
            self.env["odumcp.approval"].search(
                [("request_uid", "=", approval_id)]
            ).action_approve()
        return self._request("changes.execute", {"approval_id": approval_id})

    def _own_activity(self, user=None):
        return (
            self.env["mail.activity"]
            .with_user(self.mcp_user)
            .sudo()
            .create(
                {
                    "res_model_id": self.env["ir.model"]._get("res.partner").id,
                    "res_id": self.partner.id,
                    "activity_type_id": self.todo_type.id,
                    "summary": "Own activity",
                    "user_id": (user or self.mcp_user).id,
                }
            )
        )

    def test_own_activities_are_readable_without_a_model_policy(self):
        mine = self._own_activity()
        assigned = (
            self.env["mail.activity"]
            .with_user(self.other_user)
            .sudo()
            .create(
                {
                    "res_model_id": self.env["ir.model"]._get("res.partner").id,
                    "res_id": self.partner.id,
                    "activity_type_id": self.todo_type.id,
                    "summary": "Assigned to me",
                    "user_id": self.mcp_user.id,
                }
            )
        )
        foreign = (
            self.env["mail.activity"]
            .with_user(self.other_user)
            .sudo()
            .create(
                {
                    "res_model_id": self.env["ir.model"]._get("res.partner").id,
                    "res_id": self.partner.id,
                    "activity_type_id": self.todo_type.id,
                    "summary": "Someone else",
                    "user_id": self.other_user.id,
                }
            )
        )

        body, status = self._request("records.search", {"model": "mail.activity"})

        self.assertEqual(status, 200, body)
        found = {row["id"] for row in body["data"]["records"]}
        self.assertIn(mine.id, found)
        self.assertIn(assigned.id, found)
        self.assertNotIn(foreign.id, found)

    def test_activities_are_denied_without_the_flag(self):
        self.profile.allow_activities = False

        body, status = self._request("records.search", {"model": "mail.activity"})

        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["code"], "policy_denied")

    def test_activity_can_be_reassigned(self):
        activity = self._own_activity()

        body, status = self._change(
            "activity.update",
            {"id": activity.id, "values": {"user_id": self.other_user.id}},
            "activity-reassign-0001",
        )

        self.assertEqual(status, 200, body)
        self.assertEqual(body["data"]["state"], "executed")
        self.assertEqual(activity.user_id, self.other_user)

    def test_activity_update_rejects_moving_it_to_another_record(self):
        activity = self._own_activity()
        other_partner = self.env["res.partner"].create(
            {
                "name": "Other Partner",
                "country_id": self.country.id,
                "category_id": [Command.set(self.category.ids)],
            }
        )

        body, status = self._request(
            "changes.preview",
            {
                "action": "activity.update",
                "payload": {"id": activity.id, "values": {"res_id": other_partner.id}},
                "idempotency_key": "activity-move-0001",
            },
        )

        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["code"], "field_denied")
        self.assertEqual(activity.res_id, self.partner.id)

    def test_foreign_activity_cannot_be_touched(self):
        foreign = (
            self.env["mail.activity"]
            .with_user(self.other_user)
            .sudo()
            .create(
                {
                    "res_model_id": self.env["ir.model"]._get("res.partner").id,
                    "res_id": self.partner.id,
                    "activity_type_id": self.todo_type.id,
                    "summary": "Someone else",
                    "user_id": self.other_user.id,
                }
            )
        )

        body, status = self._request(
            "changes.preview",
            {
                "action": "activity.update",
                "payload": {"id": foreign.id, "values": {"summary": "Hijacked"}},
                "idempotency_key": "activity-foreign-0001",
            },
        )

        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["code"], "access_denied")
        self.assertEqual(foreign.summary, "Someone else")

    def test_closing_an_activity_leaves_the_feedback_in_the_chatter(self):
        activity = self._own_activity()
        before = self.partner.message_ids

        body, status = self._change(
            "activity.done",
            {"id": activity.id, "feedback": "Called the customer"},
            "activity-done-0001",
        )

        self.assertEqual(status, 200, body)
        self.assertEqual(body["data"]["state"], "executed")
        self.assertFalse(activity.active)
        self.assertEqual(activity.state, "done")
        posted = self.partner.message_ids - before
        self.assertTrue(posted)
        self.assertIn("Called the customer", posted[0].body)

    def test_activities_cannot_be_deleted_outright(self):
        activity = self._own_activity()

        body, status = self._request(
            "changes.preview",
            {
                "action": "record.delete",
                "payload": {"model": "mail.activity", "ids": [activity.id]},
                "idempotency_key": "activity-delete-0001",
            },
        )

        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["code"], "policy_denied")
        self.assertTrue(activity.exists())

    def test_activities_cannot_be_created_directly(self):
        body, status = self._request(
            "changes.preview",
            {
                "action": "record.create",
                "payload": {
                    "model": "mail.activity",
                    "values": {
                        "res_id": self.partner.id,
                        "activity_type_id": self.todo_type.id,
                    },
                },
                "idempotency_key": "activity-create-0001",
            },
        )

        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["code"], "policy_denied")

    def test_activity_actions_are_auto_approved_when_enabled(self):
        self.profile.auto_approve_low_risk = True
        activity = self._own_activity()

        body, status = self._request(
            "changes.preview",
            {
                "action": "activity.update",
                "payload": {"id": activity.id, "values": {"summary": "Reworded"}},
                "idempotency_key": "activity-auto-0001",
            },
        )

        self.assertEqual(status, 200, body)
        self.assertEqual(body["data"]["state"], "approved")

    def test_activity_model_is_listed_when_the_flag_is_on(self):
        body, status = self._request("models.list")

        self.assertEqual(status, 200, body)
        listed = {row["model"]: row["operations"] for row in body["data"]["models"]}
        self.assertIn("mail.activity", listed)
        self.assertIn("write", listed["mail.activity"])
        self.assertNotIn("unlink", listed["mail.activity"])
        self.assertNotIn("create", listed["mail.activity"])


@tagged("post_install", "-at_install")
class TestOduMcpMassApproval(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.profile = cls.env["odumcp.profile"].create(
            {
                "name": "Mass Test Profile",
                "code": "mass_test_profile",
            }
        )
        cls.mcp_user = cls.env["res.users"].create(
            {
                "name": "Mass MCP User",
                "login": "mass-mcp-user@example.com",
                "group_ids": [Command.set([cls.env.ref("base.group_user").id])],
            }
        )
        cls.manager = cls.env["res.users"].create(
            {
                "name": "Mass MCP Manager",
                "login": "mass-mcp-manager@example.com",
                "group_ids": [
                    Command.set(
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref("odumcp.group_mcp_manager").id,
                        ]
                    )
                ],
            }
        )

    def _make_approval(self, state="pending", expired=False):
        approval = self.env["odumcp.approval"].create(
            {
                "user_id": self.mcp_user.id,
                "profile_id": self.profile.id,
                "action": "record.update",
                "model_name": "res.partner",
                "payload_json": "{}",
                "payload_hash": "hash",
                "idempotency_key": str(uuid.uuid4()),
                "risk_level": "low",
                "summary": "Mass test plan",
                "expires_at": fields.Datetime.now()
                + timedelta(hours=-1 if expired else 1),
            }
        )
        if state != "pending":
            approval._system_write({"state": state})
        return approval

    def _run_wizard(self, action):
        context = action["context"]
        wizard = (
            self.env["odumcp.approval.mass"]
            .with_user(self.manager)
            .with_context(context)
            .create({})
        )
        wizard.action_confirm()
        return wizard

    def test_mass_approve_processes_only_pending_plans(self):
        pending_one = self._make_approval()
        pending_two = self._make_approval()
        approved = self._make_approval(state="approved")
        executed = self._make_approval(state="executed")
        selection = pending_one | pending_two | approved | executed

        action = selection.with_user(self.manager).action_mass_approve()
        context = action["context"]
        self.assertEqual(
            set(context["default_approval_ids"][0][2]),
            set((pending_one | pending_two).ids),
        )
        self.assertEqual(context["default_skipped_count"], 2)

        self._run_wizard(action)
        self.assertEqual(pending_one.state, "approved")
        self.assertEqual(pending_two.state, "approved")
        self.assertEqual(pending_one.approved_by, self.manager)
        self.assertEqual(approved.state, "approved")
        self.assertEqual(executed.state, "executed")

    def test_mass_reject_processes_pending_and_approved_plans(self):
        pending = self._make_approval()
        approved = self._make_approval(state="approved")
        rejected = self._make_approval(state="rejected")
        selection = pending | approved | rejected

        action = selection.with_user(self.manager).action_mass_reject()
        context = action["context"]
        self.assertEqual(
            set(context["default_approval_ids"][0][2]),
            set((pending | approved).ids),
        )
        self.assertEqual(context["default_skipped_count"], 1)

        self._run_wizard(action)
        self.assertEqual(pending.state, "rejected")
        self.assertEqual(approved.state, "rejected")
        self.assertEqual(pending.rejected_by, self.manager)

    def test_mass_approve_marks_expired_plans_instead_of_approving(self):
        pending = self._make_approval()
        action = pending.with_user(self.manager).action_mass_approve()
        # план истёк между открытием визарда и подтверждением
        pending._system_write(
            {"expires_at": fields.Datetime.now() - timedelta(minutes=1)}
        )
        self._run_wizard(action)
        self.assertEqual(pending.state, "expired")

    def test_mass_approve_excludes_expired_plans_from_wizard(self):
        expired = self._make_approval(expired=True)
        with self.assertRaises(UserError):
            expired.with_user(self.manager).action_mass_approve()

    def test_mass_actions_require_manager_group(self):
        approval = self._make_approval()
        with self.assertRaises(AccessError):
            approval.with_user(self.mcp_user).action_mass_approve()
        with self.assertRaises(AccessError):
            approval.with_user(self.mcp_user).action_mass_reject()

    def test_mass_wizard_rechecks_state_on_confirm(self):
        pending = self._make_approval()
        action = pending.with_user(self.manager).action_mass_reject()
        # план успели выполнить, пока визард был открыт
        pending._system_write({"state": "executed"})
        self._run_wizard(action)
        self.assertEqual(pending.state, "executed")

    def test_mass_delete_removes_only_expired_plans(self):
        expired = self._make_approval(state="expired")
        pending = self._make_approval()
        selection = expired | pending

        action = selection.with_user(self.manager).action_mass_delete_expired()
        context = action["context"]
        self.assertEqual(context["default_approval_ids"], [(6, 0, expired.ids)])
        self.assertEqual(context["default_skipped_count"], 1)

        self._run_wizard(action)
        self.assertFalse(expired.exists())
        self.assertEqual(pending.state, "pending")

    def test_mass_delete_rechecks_state_on_confirm(self):
        expired = self._make_approval(state="expired")
        action = expired.with_user(self.manager).action_mass_delete_expired()
        # состояние сменилось, пока визард был открыт — запись не трогаем
        expired._system_write({"state": "failed"})
        self._run_wizard(action)
        self.assertTrue(expired.exists())
        self.assertEqual(expired.state, "failed")

    def test_mass_delete_requires_manager_and_expired_state(self):
        pending = self._make_approval()
        with self.assertRaises(AccessError):
            pending.with_user(self.mcp_user).action_mass_delete_expired()
        with self.assertRaises(UserError):
            pending.with_user(self.manager).action_mass_delete_expired()
