# -*- encoding: utf-8 -*-

import base64

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase, tagged

from ..models import manual as manual_module


# Полке нужен обычный сотрудник, а res.users собирается из mail и прочих
# модулей, которые при at_install ещё не загружены.
@tagged("post_install", "-at_install")
class TestOduBookManual(TransactionCase):
    """Полка вручную вложенных документов."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manuals = cls.env["odubook.manual"]
        # Полка -- обычные записи базы, а снимок прода приносит свои. Тест
        # работает на пустой полке: транзакция откатится вместе с очисткой.
        cls.manuals.search([]).unlink()
        cls.reader = cls.env["res.users"].create(
            {
                "name": "Book Reader",
                "login": "odubook_reader",
                "lang": "en_US",
                "groups_id": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )

    def _upload(self, name, file_name, content, lang="en", manual_id=None):
        return self.manuals.upload_manual(
            name,
            file_name,
            base64.b64encode(content.encode("utf-8")),
            lang=lang,
            manual_id=manual_id,
        )

    def _create(self, name, file_name, content=b"x", lang="en"):
        return self.manuals.create(
            {
                "name": name,
                "file_ids": [
                    (
                        0,
                        0,
                        {
                            "lang": lang,
                            "file_name": file_name,
                            "file": base64.b64encode(content),
                        },
                    )
                ],
            }
        )

    def test_kind_follows_extension(self):
        """Вид документа определяется расширением, а не содержимым."""
        cases = {
            "cube.md": "markdown",
            "notes.txt": "text",
            "cube-artifact.html": "html",
            "contract.pdf": "pdf",
            "scheme.png": "image",
            "prices.xlsx": "download",
            "noextension": "download",
        }
        for file_name, expected in cases.items():
            manual = self._create(file_name, file_name)
            self.assertEqual(manual.file_ids.kind, expected, file_name)

    def test_upload_renders_markdown(self):
        """Markdown приезжает читателю готовым HTML, а не исходником."""
        shelf = self._upload("Cube design", "cube.md", "# Cube\n\nThe **cube**.\n")
        self.assertTrue(shelf["can_edit"])
        self.assertEqual(len(shelf["manuals"]), 1)
        entry = shelf["manuals"][0]
        self.assertEqual(entry["name"], "Cube design")
        self.assertEqual(entry["kind"], "markdown")
        self.assertEqual(entry["format"], "MD")
        self.assertEqual(entry["lang"], "en")
        self.assertEqual(entry["langs"], ["en"])
        self.assertTrue(entry["url"].endswith("/cube.md"))
        self.assertEqual(entry["download_url"], "%s?download=1" % entry["url"])
        rendered = self.manuals.read_manual(entry["id"])
        self.assertIn("<h1", rendered["html"])
        self.assertIn("<strong>cube</strong>", rendered["html"])

    def test_upload_without_title_uses_file_name(self):
        """Пустой заголовок заменяется именем файла без расширения."""
        shelf = self._upload("   ", "cube-artifact.html", "<b>cube</b>")
        self.assertEqual(shelf["manuals"][0]["name"], "cube-artifact")

    def test_html_and_binary_are_not_rendered(self):
        """HTML-артефакт и картинка отдаются байтами, а не текстом."""
        shelf = self._upload("Artifact", "cube.html", "<script>alert(1)</script>")
        rendered = self.manuals.read_manual(shelf["manuals"][0]["id"])
        self.assertEqual(rendered["kind"], "html")
        self.assertFalse(rendered["html"])

    def test_plain_text_is_escaped(self):
        """Текстовый документ показывается как есть и не несёт разметки."""
        shelf = self._upload("Notes", "notes.txt", "<b>plain</b>")
        rendered = self.manuals.read_manual(shelf["manuals"][0]["id"])
        self.assertIn("&lt;b&gt;plain&lt;/b&gt;", rendered["html"])
        self.assertNotIn("<b>plain</b>", rendered["html"])

    def test_oversized_file_is_refused(self):
        """Полка рассчитана на документы, а не на дистрибутивы."""
        payload = b"0" * (manual_module.MAX_MANUAL_BYTES + 1024)
        with self.assertRaises(ValidationError):
            self._create("Huge", "huge.pdf", content=payload)

    def test_reader_may_read_but_not_upload(self):
        """Обычный сотрудник читает полку и не может её менять."""
        shelf = self._upload("Cube design", "cube.md", "# Cube\n")
        manual_id = shelf["manuals"][0]["id"]
        reader_manuals = self.manuals.with_user(self.reader)
        reader_shelf = reader_manuals.get_manuals()
        self.assertFalse(reader_shelf["can_edit"])
        self.assertEqual(len(reader_shelf["manuals"]), 1)
        self.assertIn("<h1", reader_manuals.read_manual(manual_id)["html"])
        with self.assertRaises(AccessError):
            reader_manuals.upload_manual(
                "Sneaky", "sneaky.md", base64.b64encode(b"# nope"), lang="en"
            )
        with self.assertRaises(AccessError):
            reader_manuals.delete_manual(manual_id)

    def test_delete_returns_remaining_shelf(self):
        """Снятый с полки документ пропадает из индекса."""
        self._upload("First", "first.md", "# first")
        shelf = self._upload("Second", "second.md", "# second")
        removed_id = shelf["manuals"][0]["id"]
        remaining = self.manuals.delete_manual(removed_id)
        self.assertNotIn(removed_id, [entry["id"] for entry in remaining["manuals"]])
        self.assertEqual(len(remaining["manuals"]), 1)

    def test_missing_manual_is_silent(self):
        """Ссылка на удалённый документ не роняет клиента."""
        shelf = self._upload("Gone", "gone.md", "# gone")
        manual_id = shelf["manuals"][0]["id"]
        self.manuals.delete_manual(manual_id)
        self.assertEqual(
            self.manuals.read_manual(manual_id),
            {"id": False, "lang": False, "kind": False, "html": False},
        )

    def test_reader_gets_the_version_of_their_language(self):
        """Читатель получает свой язык, а без него -- английский."""
        shelf = self._upload("Cube", "cube-en.md", "# Cube EN")
        manual_id = shelf["manuals"][0]["id"]
        self._upload("Cube", "cube-pl.md", "# Cube PL", lang="pl", manual_id=manual_id)
        polish = self.manuals.with_context(lang="pl_PL")
        entry = polish.get_manuals()["manuals"][0]
        self.assertEqual(entry["lang"], "pl")
        self.assertEqual(entry["langs"], ["en", "pl"])
        self.assertIn("Cube PL", polish.read_manual(manual_id)["html"])
        # Русской версии нет: читатель видит английскую.
        russian = self.manuals.with_context(lang="ru_RU")
        self.assertEqual(russian.get_manuals()["manuals"][0]["lang"], "en")
        self.assertIn("Cube EN", russian.read_manual(manual_id)["html"])
        # Явно запрошенный язык сильнее языка профиля.
        self.assertIn("Cube PL", russian.read_manual(manual_id, lang="pl")["html"])

    def test_single_language_document_is_read_by_everyone(self):
        """Документ, вложенный на одном языке, виден всем языкам."""
        shelf = self._upload("Cube", "cube-ru.md", "# Cube RU", lang="ru")
        manual_id = shelf["manuals"][0]["id"]
        polish = self.manuals.with_context(lang="pl_PL")
        self.assertEqual(polish.get_manuals()["manuals"][0]["lang"], "ru")
        self.assertIn("Cube RU", polish.read_manual(manual_id)["html"])

    def test_uploading_the_same_language_replaces_the_version(self):
        """Повторная загрузка того же языка заменяет файл, а не двоит его."""
        shelf = self._upload("Cube", "cube-en.md", "# First")
        manual_id = shelf["manuals"][0]["id"]
        shelf = self._upload("Cube", "cube-en.md", "# Second", manual_id=manual_id)
        self.assertEqual(shelf["manuals"][0]["langs"], ["en"])
        self.assertIn("Second", self.manuals.read_manual(manual_id)["html"])

    def test_removing_one_language_keeps_the_document(self):
        """Уходит только выбранный перевод; последний уносит и карточку."""
        shelf = self._upload("Cube", "cube-en.md", "# Cube EN")
        manual_id = shelf["manuals"][0]["id"]
        self._upload("Cube", "cube-pl.md", "# Cube PL", lang="pl", manual_id=manual_id)
        shelf = self.manuals.delete_manual(manual_id, lang="pl")
        self.assertEqual(shelf["manuals"][0]["langs"], ["en"])
        shelf = self.manuals.delete_manual(manual_id, lang="en")
        self.assertFalse(shelf["manuals"])

    def test_language_code_is_validated(self):
        """В язык версии не попадает произвольная строка."""
        with self.assertRaises(ValidationError):
            self._create("Bad", "cube.md", lang="../etc")
