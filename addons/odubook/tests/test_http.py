import json
import base64

from odoo.tests import HttpCase, tagged
from odoo.tests.common import new_test_user


@tagged("post_install", "-at_install")
class TestOdubookHttp(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.reader = new_test_user(cls.env, login="odubook_http_reader", groups="base.group_user")
        cls.portal = new_test_user(cls.env, login="odubook_http_portal", groups="base.group_portal")
        cls.manual = cls.env["odubook.manual"].create({
            "name": "HTTP manual",
            "file_ids": [(0, 0, {
                "lang": "en",
                "file_name": "guide #1.html",
                "file": base64.b64encode(b"<h1>Manual</h1><script>window.example = true;</script>"),
            })],
        })

    def _rpc(self, route, params=None):
        response = self.url_open(route, data=json.dumps({
            "jsonrpc": "2.0", "method": "call", "id": 1, "params": params or {},
        }), headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_jsonrpc_book_and_admin_access(self):
        self.authenticate(self.reader.login, self.reader.login)
        book = self._rpc("/odubook/book", {"lang": "ru"})
        self.assertEqual(book["result"]["lang"], "ru")
        self.assertIn("odubook", [page["module"] for page in book["result"]["pages"]])
        self.assertEqual(self._rpc("/odubook/admin")["error"]["data"]["name"],
                         "odoo.exceptions.AccessError")

    def test_audit_rpc_rejects_non_administrators(self):
        for user in (self.reader, self.portal):
            with self.subTest(user=user.login):
                self.authenticate(user.login, user.login)
                result = self._rpc("/odubook/audit")
                self.assertEqual(result["error"]["data"]["name"],
                                 "odoo.exceptions.AccessError")

    def test_portal_cannot_read_documentation_or_files(self):
        self.authenticate(self.portal.login, self.portal.login)
        self.assertEqual(self._rpc("/odubook/book")["error"]["data"]["name"],
                         "odoo.exceptions.AccessError")
        response = self.url_open(self.manual.file_ids._content_url())
        self.assertEqual(response.status_code, 404)

    def test_manual_content_and_download(self):
        self.authenticate(self.reader.login, self.reader.login)
        url = self.manual.file_ids._content_url()
        self.assertIn("%23", url)
        response = self.url_open(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"<h1>Manual</h1>", response.content)
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("sandbox", response.headers["Content-Security-Policy"])
        self.assertNotIn("allow-same-origin", response.headers["Content-Security-Policy"])
        self.assertTrue(response.headers["Content-Disposition"].startswith("inline;"))
        download = self.url_open(url + "?download=1")
        self.assertTrue(download.headers["Content-Disposition"].startswith("attachment;"))

    def test_reader_cannot_upload(self):
        self.authenticate(self.reader.login, self.reader.login)
        result = self._rpc("/odubook/manuals/upload", {
            "name": "Forbidden", "file_name": "test.md", "data": "IyBUZXN0", "lang": "en",
        })
        self.assertEqual(result["error"]["data"]["name"], "odoo.exceptions.AccessError")

    def test_pdf_exports(self):
        if self.env["ir.actions.report"].get_wkhtmltopdf_state() == "install":
            self.skipTest("wkhtmltopdf is not installed")
        self.authenticate(self.reader.login, self.reader.login)
        routes = [
            "/odubook/guide/pdf?module=odubook&book=user&lang=en",
            "/odubook/guide/pdf/bundle?sections=odubook|&book=user&lang=en",
            "/odubook/changes/pdf?entries=odubook|2026-09-02&lang=en",
        ]
        for route in routes:
            with self.subTest(route=route):
                response = self.url_open(route)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["Content-Type"], "application/pdf")
                self.assertTrue(response.content.startswith(b"%PDF-"))
