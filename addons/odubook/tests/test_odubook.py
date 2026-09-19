# -*- encoding: utf-8 -*-

import os
import shutil
import subprocess
import tempfile
import unittest
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user

from ..models import odubook


class TestOduBook(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        for code in ("pl_PL", "de_DE", "ru_RU"):
            cls.env["res.lang"]._activate_lang(code)
        cls.module = cls.env["ir.module.module"].search([("name", "=", "base")], limit=1)
        cls.user = cls.env.ref("base.public_user")

    def setUp(self):
        super().setUp()
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.module_path = self.tempdir.name
        self.doc_path = os.path.join(self.module_path, "doc")
        os.makedirs(self.doc_path)
        for cache in (
            odubook._RENDER_CACHE,
            odubook._COMMIT_CACHE,
            odubook._HEAD_CACHE,
            odubook._ROOT_CACHE,
        ):
            cache.clear()
            self.addCleanup(cache.clear)

    def _write(self, relative_path, content, binary=False):
        filepath = os.path.join(self.module_path, relative_path)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        mode = "wb" if binary else "w"
        kwargs = {} if binary else {"encoding": "utf-8"}
        with open(filepath, mode, **kwargs) as handle:
            handle.write(content)
        return filepath

    def _module_path(self, module_name):
        return self.module_path if module_name == self.module.name else None

    def _days_ago(self, days):
        return str(fields.Date.context_today(self.env["odubook"]) - timedelta(days=days))

    def _get_changes(self):
        with patch.object(odubook, "get_module_path", side_effect=self._module_path):
            return self.env["odubook"].get_changes()["entries"]

    def test_collects_documented_module_without_prefix(self):
        self._write("doc/user_guide.md", "# Generic module\n\nSource text.")

        with patch.object(odubook, "get_module_path", side_effect=self._module_path):
            result = self.env["odubook"].get_book()

        self.assertEqual([page["module"] for page in result["pages"]], ["base"])
        self.assertIn("Source text.", result["pages"][0]["html"])

    def test_translation_and_source_fallback(self):
        self._write("doc/user_guide.md", "# English\n\nSource text.")
        self._write(
            "doc/i18n/pl/user_guide.md",
            "<!-- i18n source=user_guide.md sha=abc lang=pl -->\n# Polski\n\nTekst.",
        )

        with patch.object(odubook, "get_module_path", side_effect=self._module_path):
            polish = self.env["odubook"].with_context(lang="pl_PL").get_book()
            german = self.env["odubook"].with_context(lang="de_DE").get_book()

        self.assertIn("Polski", polish["pages"][0]["html"])
        self.assertNotIn("i18n source", polish["pages"][0]["html"])
        self.assertIn("English", german["pages"][0]["html"])

    def test_language_buttons_follow_the_mirrors_on_disk(self):
        self._write("doc/user_guide.md", "# English")
        self._write("doc/i18n/pl/user_guide.md", "# Polski")
        self._write("doc/i18n/ru/changes/%s.md" % self._days_ago(1), "# Zapis")
        # Пустое зеркало языка кнопку не даёт: переводить в нём нечего.
        os.makedirs(os.path.join(self.doc_path, "i18n", "de"))

        with patch.object(odubook, "get_module_path", side_effect=self._module_path):
            book = self.env["odubook"].get_book()
            changes = self.env["odubook"].get_changes()

        self.assertEqual([item["code"] for item in book["languages"]], ["en", "pl"])
        self.assertEqual([item["code"] for item in changes["languages"]], ["en", "ru"])

    def test_reader_can_open_the_book_in_another_language(self):
        self._write("doc/user_guide.md", "# English\n\nSource text.")
        self._write(
            "doc/i18n/pl/user_guide.md",
            "<!-- i18n source=user_guide.md sha=abc lang=pl -->\n# Polski\n\nTekst.",
        )

        with patch.object(odubook, "get_module_path", side_effect=self._module_path):
            polish = self.env["odubook"].get_book(lang="pl")
            missing = self.env["odubook"].get_book(lang="de")

        self.assertEqual(polish["lang"], "pl")
        self.assertIn("Polski", polish["pages"][0]["html"])
        # Язык без зеркала кнопкой не предлагается, а запрошенный в обход
        # интерфейса -- игнорируется.
        self.assertEqual(missing["lang"], "en")
        self.assertIn("English", missing["pages"][0]["html"])

    def test_entry_can_be_read_in_another_language(self):
        date = self._days_ago(1)
        entries = [{"module": "base", "date": date}]
        self._write("doc/changes/%s.md" % date, "# Source entry")
        self._write(
            "doc/i18n/ru/changes/%s.md" % date,
            "<!-- i18n source=changes/%s.md sha=abc lang=ru -->\n# Zapis" % date,
        )

        with patch.object(odubook, "get_module_path", side_effect=self._module_path):
            russian = self.env["odubook"].read_changes(entries, mark_read=False, lang="ru")
            english = self.env["odubook"].read_changes(entries, mark_read=False, lang="en")

        self.assertEqual(russian["entries"]["base|%s" % date]["heading"], "Zapis")
        # На исходном языке зеркала нет -- читается сам исходник.
        self.assertEqual(
            english["entries"]["base|%s" % date]["heading"], "Source entry"
        )

    def test_invalid_language_falls_back_to_english(self):
        book = self.env["odubook"].with_context(lang="../../secret")

        self.assertEqual(book._doc_lang(), "en")

    def test_book_language_is_stored_without_a_user_column(self):
        user_field = self.env["res.users"]._fields["odubook_lang_id"]
        language = self.env.ref("base.lang_en")

        self.assertFalse(user_field.store)

        self.env.user.write({"odubook_lang_id": language.id})

        parameter = self.env["ir.config_parameter"].sudo().get_param(
            "odubook.user_language.%s" % self.env.user.id
        )
        self.assertEqual(parameter, str(language.id))
        self.assertEqual(self.env.user.odubook_lang_id, language)

    def test_audit_book_reads_source_and_skips_missing_reports(self):
        self._write("doc/module-audit.md", "# Base audit\n\n## Findings\n\nAudit evidence.")
        self._write("doc/i18n/en/module-audit.md", "# Wrong mirror")
        self._write("doc/i18n/pl/module-audit.md", "# Wrong translation")
        with patch.object(odubook, "get_module_path", side_effect=self._module_path):
            book = self.env["odubook"].get_audit_book(lang="pl")
            self.assertEqual(book["lang"], "en")
            self.assertEqual([lang["code"] for lang in book["languages"]], ["en"])
            self.assertEqual([page["module"] for page in book["pages"]], ["base"])
            self.assertIn("Audit evidence.", book["pages"][0]["html"])
            self.assertNotIn("Wrong", book["pages"][0]["html"])
            self.assertEqual(self.env["odubook"].get_book()["pages"], [])
            self.assertEqual(self.env["odubook"].get_admin_book()["pages"], [])
            os.remove(os.path.join(self.doc_path, "module-audit.md"))
            self.assertEqual(self.env["odubook"].get_audit_book()["pages"], [])

    def test_audit_access_includes_rpc_and_both_pdf_exports(self):
        reader = new_test_user(self.env, login="audit_reader", groups="base.group_user")
        portal = new_test_user(self.env, login="audit_portal", groups="base.group_portal")
        for user in (reader, portal, self.user):
            book = self.env["odubook"].with_user(user)
            with self.subTest(user=user.login):
                with self.assertRaises(AccessError):
                    book.get_audit_book()
                with self.assertRaises(AccessError):
                    book.guide_pdf("base", book="audit")
                with self.assertRaises(AccessError):
                    book.guide_bundle_pdf([{"module": "base"}], book="audit")

    def test_audit_pdf_uses_report_for_single_and_bundle_exports(self):
        self._write("doc/module-audit.md", "# Base audit\n\n## Findings\n\nAudit evidence.")
        self._write("doc/user_guide.md", "# User guide\n\nUnrelated guide.")
        report = type(self.env["ir.actions.report"])
        bodies = []

        def fake_pdf(record, htmls, **kwargs):
            bodies.extend(htmls)
            return b"%PDF-audit"

        with patch.object(odubook, "get_module_path", side_effect=self._module_path), \
                patch.object(report, "_run_wkhtmltopdf", fake_pdf):
            book = self.env["odubook"]
            single = book.guide_pdf("base", book="audit", section="findings")
            bundle = book.guide_bundle_pdf([{"module": "base"}], book="audit")
        self.assertEqual(single["pdf"], b"%PDF-audit")
        self.assertEqual(bundle["pdf"], b"%PDF-audit")
        for body in bodies:
            self.assertIn("Audit evidence.", body)
            self.assertNotIn("Unrelated guide.", body)

    def test_admin_book_requires_system_group(self):
        with self.assertRaises(AccessError):
            self.env["odubook"].with_user(self.user).get_admin_book()

    def test_changes_index_is_ordered_and_carries_no_html(self):
        self._write("doc/changes/%s.md" % self._days_ago(1), "# Older")
        self._write("doc/changes/%s.md" % self._days_ago(0), "# Newer")
        self._write("doc/changes/not-a-date.md", "# Ignored")

        entries = self._get_changes()

        self.assertEqual(
            [entry["date"] for entry in entries],
            [self._days_ago(0), self._days_ago(1)],
        )
        self.assertEqual(entries[0]["module"], "base")
        self.assertNotIn("html", entries[0])

    def test_publication_time_falls_back_to_mtime_outside_a_working_copy(self):
        date = self._days_ago(1)
        filepath = self._write("doc/changes/%s.md" % date, "# Entry")
        # 1 700 000 000 -- 2023-11-14 22:13:20 UTC.
        os.utime(filepath, (1700000000, 1700000000))

        entry = self._get_changes()[0]

        self.assertEqual(entry["published"], "2023-11-14 22:13:20")

    @unittest.skipUnless(shutil.which("git"), "git is not available")
    def test_publication_time_is_the_commit_time_of_the_entry(self):
        date = self._days_ago(1)
        filepath = self._write("doc/changes/%s.md" % date, "# Entry")
        # mtime намеренно расходится с коммитом: git при checkout ставит своё.
        os.utime(filepath, (1700000000, 1700000000))
        self._git("init")
        self._git("add", "doc")
        self._git(
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-m",
            "entry",
            GIT_AUTHOR_DATE="2024-03-05T10:20:30+00:00",
            GIT_COMMITTER_DATE="2024-03-05T10:20:30+00:00",
        )

        entry = self._get_changes()[0]

        self.assertEqual(entry["published"], "2024-03-05 10:20:30")

    @unittest.skipUnless(shutil.which("git"), "git is not available")
    def test_entry_outside_prod_history_is_not_published_and_comes_first(self):
        published_date = self._days_ago(1)
        self._write("doc/changes/%s.md" % published_date, "# Published")
        self._git("init")
        self._git("add", "doc")
        self._commit("published", "2024-03-05T10:20:30+00:00")
        # Отпечаток прода: сюда влито только первое изменение.
        self._git("update-ref", "refs/remotes/origin/prod", "HEAD")
        self._git("checkout", "-q", "-b", "feature")
        # Второе изменение живёт только в ветке -- значит, не опубликовано.
        self._write("doc/changes/%s.md" % self._days_ago(2), "# In a branch")
        self._git("add", "doc")
        self._commit("branch", "2024-04-01T09:00:00+00:00")

        entries = self._get_changes()

        self.assertEqual([entry["published"] for entry in entries],
                         [False, "2024-03-05 10:20:30"])
        self.assertEqual([entry["date"] for entry in entries],
                         [self._days_ago(2), published_date])

    def _commit(self, message, when):
        self._git(
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-m",
            message,
            GIT_AUTHOR_DATE=when,
            GIT_COMMITTER_DATE=when,
        )

    def _git(self, *args, **env):
        subprocess.run(
            ["git", "-C", self.module_path] + list(args),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=dict(os.environ, **env),
        )

    def test_new_and_unread_follow_the_entry_age(self):
        for age in (1, 5, 200):
            self._write("doc/changes/%s.md" % self._days_ago(age), "# Entry")

        by_date = {entry["date"]: entry for entry in self._get_changes()}

        self.assertTrue(by_date[self._days_ago(1)]["is_new"])
        self.assertTrue(by_date[self._days_ago(1)]["unread"])
        self.assertFalse(by_date[self._days_ago(5)]["is_new"])
        self.assertTrue(by_date[self._days_ago(5)]["unread"])
        self.assertFalse(by_date[self._days_ago(200)]["unread"])

    def test_reading_an_entry_returns_html_and_clears_the_flags(self):
        date = self._days_ago(1)
        self._write("doc/changes/%s.md" % date, "# Fresh entry")

        with patch.object(odubook, "get_module_path", side_effect=self._module_path):
            result = self.env["odubook"].read_changes(
                [{"module": "base", "date": date}]
            )
            # Повторное чтение не должно падать на уникальном индексе.
            self.env["odubook"].read_changes([{"module": "base", "date": date}])

        self.assertEqual(result["entries"]["base|%s" % date]["heading"], "Fresh entry")
        self.assertEqual(
            self.env["odubook.change.read"].search_count(
                [("user_id", "=", self.env.uid), ("module", "=", "base")]
            ),
            1,
        )
        entry = self._get_changes()[0]
        self.assertFalse(entry["unread"])
        self.assertFalse(entry["is_new"])

    def test_rendering_without_mark_read_leaves_the_entry_unread(self):
        date = self._days_ago(1)
        self._write("doc/changes/%s.md" % date, "# Fresh entry")
        book = self.env["odubook"]

        with patch.object(odubook, "get_module_path", side_effect=self._module_path):
            book.read_changes([{"module": "base", "date": date}], mark_read=False)
            still_unread = self._get_changes()[0]["unread"]
            book.mark_entries_read([{"module": "base", "date": date}])
            now_read = self._get_changes()[0]["unread"]

        self.assertTrue(still_unread)
        self.assertFalse(now_read)

    def test_read_marks_are_personal(self):
        date = self._days_ago(1)
        self._write("doc/changes/%s.md" % date, "# Fresh entry")
        # Берём существующего внутреннего пользователя: create() res.users в
        # этой базе тянет за собой mail-компьюты и к отметкам отношения не имеет.
        other = self.env.ref("base.user_admin")

        with patch.object(odubook, "get_module_path", side_effect=self._module_path):
            self.env["odubook"].read_changes([{"module": "base", "date": date}])
            other_entries = self.env["odubook"].with_user(other).get_changes()["entries"]

        self.assertTrue(other_entries[0]["unread"])

    def test_unknown_entries_are_ignored(self):
        date = self._days_ago(1)
        self._write("doc/changes/%s.md" % date, "# Fresh entry")
        marks = self.env["odubook.change.read"]
        # База может уже содержать чужие отметки: сравниваем изменение, не ноль.
        before = marks.search_count([])

        with patch.object(odubook, "get_module_path", side_effect=self._module_path):
            result = self.env["odubook"].read_changes(
                [
                    {"module": "no_such_module", "date": date},
                    {"module": "base", "date": "2026-99-99"},
                    {"module": "base", "date": "../../../etc/passwd"},
                    {"module": "base", "date": self._days_ago(2)},
                ]
            )

        self.assertEqual(result["entries"], {})
        self.assertEqual(marks.search_count([]), before)

    def test_entry_prefers_the_readers_mirror(self):
        date = self._days_ago(1)
        self._write("doc/changes/%s.md" % date, "# Entry\n\nEnglish source.")
        self._write(
            "doc/i18n/ru/changes/%s.md" % date,
            "<!-- i18n source=changes/%s.md sha=abc123abc123 lang=ru -->\n"
            "# Запись\n\nРусский перевод." % date,
        )
        book = self.env["odubook"]

        with patch.object(odubook, "get_module_path", side_effect=self._module_path):
            russian = book.with_context(lang="ru_RU").read_changes(
                [{"module": "base", "date": date}]
            )
            english = book.with_context(lang="en_US").read_changes(
                [{"module": "base", "date": date}]
            )

        entry = russian["entries"]["base|%s" % date]
        self.assertIn("Русский перевод.", entry["html"])
        self.assertNotIn("i18n source", entry["html"])
        self.assertIn(
            "English source.", english["entries"]["base|%s" % date]["html"]
        )

    def test_mirror_without_source_does_not_add_an_entry(self):
        date = self._days_ago(1)
        self._write(
            "doc/i18n/ru/changes/%s.md" % date,
            "<!-- i18n source=changes/%s.md sha=abc123abc123 lang=ru -->\n# Осиротело"
            % date,
        )

        with patch.object(odubook, "get_module_path", side_effect=self._module_path):
            entries = self.env["odubook"].with_context(lang="ru_RU").get_changes()

        self.assertEqual(entries["entries"], [])

    def test_entry_heading_loses_the_date_stamp(self):
        date = self._days_ago(1)
        self._write(
            "doc/changes/%s.md" % date,
            "# 28 August 2026 — Customer negotiation history\n\nBody text.",
        )

        with patch.object(odubook, "get_module_path", side_effect=self._module_path):
            result = self.env["odubook"].read_changes(
                [{"module": "base", "date": date}], mark_read=False
            )

        entry = result["entries"]["base|%s" % date]
        self.assertEqual(entry["heading"], "Customer negotiation history")
        # Заголовок уезжает из текста: его показывает и озаглавливает клиент.
        self.assertNotIn("<h1", entry["html"])
        self.assertIn("Body text.", entry["html"])

    def test_entry_named_by_a_date_alone_has_no_heading(self):
        date = self._days_ago(1)
        self._write("doc/changes/%s.md" % date, "# %s\n\nBody text." % date)

        with patch.object(odubook, "get_module_path", side_effect=self._module_path):
            result = self.env["odubook"].read_changes(
                [{"module": "base", "date": date}], mark_read=False
            )

        entry = result["entries"]["base|%s" % date]
        self.assertEqual(entry["heading"], "")
        self.assertIn("Body text.", entry["html"])

    def test_date_stamps_of_every_written_form_are_recognised(self):
        stripped = {
            "2026-08-28 — Customer negotiation history": "Customer negotiation history",
            "August 2026 — CMR Management": "CMR Management",
            "August 14, 2026: KSeF": "KSeF",
            "17 августа 2026 — Транспорт": "Транспорт",
            "Sierpień 2026 - Veles Sales Cockpit": "Veles Sales Cockpit",
            "27 августа 2026 г. — Транспорт": "Транспорт",
            "2026-08-28": "",
            "August 2026": "",
            # Дата в середине названия его не начинает, поэтому остаётся на месте.
            "Lost stage — a pipeline end": "Lost stage — a pipeline end",
            "Quotations of August 2026": "Quotations of August 2026",
        }

        for title, expected in stripped.items():
            self.assertEqual(odubook.strip_date_stamp(title), expected, title)

    def test_pdf_export_carries_every_requested_entry(self):
        first, second = self._days_ago(1), self._days_ago(2)
        self._write("doc/changes/%s.md" % first, "# %s — Fresh\n\nFirst body." % first)
        self._write("doc/changes/%s.md" % second, "# %s\n\nSecond body." % second)
        report = type(self.env["ir.actions.report"])
        captured = []

        def fake_pdf(self, bodies, **kwargs):
            captured.extend(bodies)
            return b"%PDF-fake"

        with patch.object(odubook, "get_module_path", side_effect=self._module_path), \
                patch.object(report, "_run_wkhtmltopdf", fake_pdf):
            pdf = self.env["odubook"].change_pdf(
                [
                    {"module": "base", "date": first},
                    {"module": "base", "date": second},
                ],
                title="August 2026",
            )

        self.assertEqual(pdf, b"%PDF-fake")
        document = captured[0]
        self.assertIn("August 2026", document)
        self.assertIn("First body.", document)
        self.assertIn("Second body.", document)
        # Запись без собственного названия остаётся без заголовка, но со своей
        # шапкой: модуль и дата.
        self.assertIn("<h1>Fresh</h1>", document)
        self.assertIn(second, document)

    def test_pdf_export_does_not_repeat_the_cover_title(self):
        day = self._days_ago(1)
        self._write("doc/changes/%s.md" % day, "# %s — Fresh\n\nBody." % day)
        report = type(self.env["ir.actions.report"])
        captured = []

        def fake_pdf(self, bodies, **kwargs):
            captured.extend(bodies)
            return b"%PDF-fake"

        with patch.object(odubook, "get_module_path", side_effect=self._module_path), \
                patch.object(report, "_run_wkhtmltopdf", fake_pdf):
            self.env["odubook"].change_pdf(
                [{"module": "base", "date": day}], title="Fresh"
            )

        # Название статьи совпало с заголовком обложки: печатается один раз.
        self.assertEqual(captured[0].count("Fresh"), 1)

    def test_guide_pdf_exports_the_whole_document(self):
        self._write(
            "doc/user_guide.md",
            "# Generic module\n\nIntro.\n\n## Daily work\n\nBody.\n",
        )
        report = type(self.env["ir.actions.report"])
        captured = []

        def fake_pdf(self, bodies, **kwargs):
            captured.extend(bodies)
            return b"%PDF-fake"

        with patch.object(odubook, "get_module_path", side_effect=self._module_path), \
                patch.object(report, "_run_wkhtmltopdf", fake_pdf):
            document = self.env["odubook"].guide_pdf("base")

        self.assertEqual(document["title"], "Generic module")
        self.assertEqual(document["pdf"], b"%PDF-fake")
        self.assertIn("Intro.", captured[0])
        self.assertIn("Body.", captured[0])
        # Название документа стоит на обложке и не повторяется в тексте.
        self.assertEqual(captured[0].count("Generic module"), 1)

    def test_guide_pdf_exports_a_single_section(self):
        self._write(
            "doc/user_guide.md",
            "# Generic module\n\nIntro.\n\n## Daily work\n\nBody.\n\n"
            "## Settings\n\nOther.\n",
        )
        report = type(self.env["ir.actions.report"])
        captured = []

        def fake_pdf(self, bodies, **kwargs):
            captured.extend(bodies)
            return b"%PDF-fake"

        with patch.object(odubook, "get_module_path", side_effect=self._module_path), \
                patch.object(report, "_run_wkhtmltopdf", fake_pdf):
            document = self.env["odubook"].guide_pdf("base", section="daily-work")
            missing = self.env["odubook"].guide_pdf("base", section="no-such-section")
            unknown = self.env["odubook"].guide_pdf("no_such_module")

        self.assertEqual(document["title"], "Daily work")
        self.assertIn("Body.", captured[0])
        self.assertNotIn("Other.", captured[0])
        self.assertNotIn("Intro.", captured[0])
        self.assertIsNone(missing)
        self.assertIsNone(unknown)

    def test_guide_pdf_follows_the_selected_language(self):
        self._write("doc/user_guide.md", "# English\n\nSource text.")
        self._write(
            "doc/i18n/pl/user_guide.md",
            "<!-- i18n source=user_guide.md sha=abc lang=pl -->\n# Polski\n\nTekst.",
        )
        report = type(self.env["ir.actions.report"])
        captured = []

        def fake_pdf(self, bodies, **kwargs):
            captured.extend(bodies)
            return b"%PDF-fake"

        with patch.object(odubook, "get_module_path", side_effect=self._module_path), \
                patch.object(report, "_run_wkhtmltopdf", fake_pdf):
            document = self.env["odubook"].guide_pdf("base", lang="pl")

        self.assertEqual(document["title"], "Polski")
        self.assertIn("Tekst.", captured[0])
        self.assertNotIn("i18n source", captured[0])

    def test_guide_pdf_of_the_admin_book_requires_the_system_group(self):
        self._write("doc/admin_guide.md", "# Admin\n\nSecret.")

        with patch.object(odubook, "get_module_path", side_effect=self._module_path):
            with self.assertRaises(AccessError):
                self.env["odubook"].with_user(self.user).guide_pdf("base", book="admin")

    def test_guide_bundle_pdf_keeps_the_order_of_the_selection(self):
        self._write(
            "doc/user_guide.md",
            "# Generic module\n\nIntro.\n\n## Daily work\n\nBody.\n\n"
            "## Settings\n\nOther.\n",
        )
        report = type(self.env["ir.actions.report"])
        captured = []

        def fake_pdf(self, bodies, **kwargs):
            captured.extend(bodies)
            return b"%PDF-fake"

        with patch.object(odubook, "get_module_path", side_effect=self._module_path), \
                patch.object(report, "_run_wkhtmltopdf", fake_pdf):
            document = self.env["odubook"].guide_bundle_pdf(
                [
                    {"module": "base", "section": "settings"},
                    {"module": "base", "section": "daily-work"},
                    # Повтор отмеченного раздела и неизвестное отбрасываются.
                    {"module": "base", "section": "settings"},
                    {"module": "base", "section": "no-such-section"},
                    {"module": "no_such_module", "section": "daily-work"},
                ],
                title="My selection",
            )

        self.assertEqual(document["title"], "My selection")
        self.assertEqual(document["pdf"], b"%PDF-fake")
        body = captured[0]
        self.assertIn("My selection", body)
        self.assertIn("<h1>Settings</h1>", body)
        self.assertIn("<h1>Daily work</h1>", body)
        self.assertLess(body.index("Other."), body.index("Body."))
        self.assertEqual(body.count("Other."), 1)
        self.assertNotIn("Intro.", body)

    def test_guide_bundle_pdf_takes_a_whole_guide_without_an_anchor(self):
        self._write(
            "doc/user_guide.md",
            "# Generic module\n\nIntro.\n\n## Daily work\n\nBody.\n",
        )
        report = type(self.env["ir.actions.report"])
        captured = []

        def fake_pdf(self, bodies, **kwargs):
            captured.extend(bodies)
            return b"%PDF-fake"

        with patch.object(odubook, "get_module_path", side_effect=self._module_path), \
                patch.object(report, "_run_wkhtmltopdf", fake_pdf):
            self.env["odubook"].guide_bundle_pdf([{"module": "base"}])

        self.assertIn("Intro.", captured[0])
        self.assertIn("<h1>Generic module</h1>", captured[0])

    def test_guide_bundle_pdf_follows_the_selected_language(self):
        self._write("doc/user_guide.md", "# English\n\n## Work\n\nSource text.")
        self._write(
            "doc/i18n/pl/user_guide.md",
            "<!-- i18n source=user_guide.md sha=abc lang=pl -->\n"
            "# Polski\n\n## Praca\n\nTekst.",
        )
        report = type(self.env["ir.actions.report"])
        captured = []

        def fake_pdf(self, bodies, **kwargs):
            captured.extend(bodies)
            return b"%PDF-fake"

        with patch.object(odubook, "get_module_path", side_effect=self._module_path), \
                patch.object(report, "_run_wkhtmltopdf", fake_pdf):
            document = self.env["odubook"].guide_bundle_pdf(
                [{"module": "base", "section": "praca"}], lang="pl"
            )

        self.assertTrue(document)
        self.assertIn("Tekst.", captured[0])
        self.assertNotIn("i18n source", captured[0])

    def test_guide_bundle_pdf_of_the_admin_book_requires_the_system_group(self):
        self._write("doc/admin_guide.md", "# Admin\n\n## Secrets\n\nSecret.")

        with patch.object(odubook, "get_module_path", side_effect=self._module_path):
            with self.assertRaises(AccessError):
                self.env["odubook"].with_user(self.user).guide_bundle_pdf(
                    [{"module": "base", "section": "secrets"}], book="admin"
                )

    def test_guide_bundle_pdf_of_an_empty_selection_returns_nothing(self):
        with patch.object(odubook, "get_module_path", side_effect=self._module_path):
            self.assertIsNone(self.env["odubook"].guide_bundle_pdf([]))
            self.assertIsNone(
                self.env["odubook"].guide_bundle_pdf(
                    [{"module": "no_such_module", "section": "work"}]
                )
            )

    def test_pdf_export_of_unknown_entries_returns_nothing(self):
        with patch.object(odubook, "get_module_path", side_effect=self._module_path):
            self.assertFalse(
                self.env["odubook"].change_pdf(
                    [{"module": "no_such_module", "date": self._days_ago(1)}]
                )
            )

    def test_mark_all_read_clears_every_entry(self):
        for age in (1, 5):
            self._write("doc/changes/%s.md" % self._days_ago(age), "# Entry")

        with patch.object(odubook, "get_module_path", side_effect=self._module_path):
            self.env["odubook"].mark_all_read()

        self.assertFalse(any(entry["unread"] for entry in self._get_changes()))

    def test_oversized_and_non_utf8_files_are_skipped(self):
        oversized = self._write("doc/oversized.md", "12345")
        broken = self._write("doc/broken.md", b"\xff", binary=True)
        book = self.env["odubook"]

        with patch.object(odubook, "MAX_DOC_BYTES", 4):
            self.assertIsNone(book._render_doc_html(oversized, strip_marker=False))
        self.assertIsNone(book._render_doc_html(broken, strip_marker=False))

    def test_render_cache_is_invalidated_by_mtime(self):
        filepath = self._write("doc/cached.md", "First")
        book = self.env["odubook"]
        first = book._render_doc_html(filepath, strip_marker=False)
        self._write("doc/cached.md", "Second")
        stat = os.stat(filepath)
        os.utime(filepath, (stat.st_atime, stat.st_mtime + 1))
        second = book._render_doc_html(filepath, strip_marker=False)

        self.assertIn("First", first)
        self.assertIn("Second", second)
