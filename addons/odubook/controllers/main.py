# -*- coding: utf-8 -*-
import base64
import re

from odoo import http
from odoo.exceptions import AccessError
from odoo.http import content_disposition, request

#: Вложенный HTML исполняется в собственном origin: даже пришедший от
#: администратора артефакт не должен получить доступ к сессии читателя.
HTML_SANDBOX_CSP = "sandbox allow-scripts allow-popups allow-forms allow-modals"

#: Из заголовка группы получается имя файла: всё, что не буква, цифра, пробел
#: или дефис, стало бы проблемой для файловой системы читателя.
FILENAME_RE = re.compile(r"[^\w \-]+", re.UNICODE)


def _pdf_filename(title):
    """Имя скачиваемого файла по заголовку экспорта."""
    name = FILENAME_RE.sub("", title or "").strip()
    return "%s.pdf" % (name[:80] or "changes")


class OduBookController(http.Controller):
    """JSON-обёртка над ``odubook`` для клиентских действий."""

    @http.route("/odubook/book", type="jsonrpc", auth="user")
    def book(self, lang=None):
        return request.env["odubook"].get_book(lang=lang)

    @http.route("/odubook/admin", type="jsonrpc", auth="user")
    def admin_book(self, lang=None):
        # Группа дополнительно проверяется на сервере в get_admin_book.
        return request.env["odubook"].get_admin_book(lang=lang)

    @http.route("/odubook/changes", type="jsonrpc", auth="user")
    def changes(self, lang=None):
        return request.env["odubook"].get_changes(lang=lang)

    @http.route("/odubook/change", type="jsonrpc", auth="user")
    def change(self, entries=None, mark_read=True, lang=None):
        # Отдаёт текст запрошенных записей; лента отмечает прочитанное сама.
        return request.env["odubook"].read_changes(
            entries or [], mark_read=mark_read, lang=lang
        )

    @http.route("/odubook/languages", type="jsonrpc", auth="user")
    def languages(self):
        # Языки интерфейса для переключателя в меню пользователя.
        return request.env["odubook"].get_ui_languages()

    @http.route("/odubook/changes/read", type="jsonrpc", auth="user")
    def changes_read(self, entries=None):
        # Отмечает прочитанными записи, доскроллленные читателем в ленте.
        return request.env["odubook"].mark_entries_read(entries or [])

    @http.route("/odubook/changes/pdf", type="http", auth="user")
    def changes_pdf(self, entries=None, title=None, lang=None, **kwargs):
        """Отдать PDF со статьями под заголовком: одной записи или всей группы.

        Записи приходят строкой ``module|date,module|date``: ссылку открывает
        сам браузер, поэтому список едет в адресе, а не в теле запроса.
        """
        wanted = []
        for key in (entries or "").split(","):
            module_name, __, date_str = key.partition("|")
            if module_name and date_str:
                wanted.append({"module": module_name, "date": date_str})
        if not wanted:
            raise request.not_found()
        pdf = request.env["odubook"].change_pdf(wanted, title=title, lang=lang)
        if not pdf:
            raise request.not_found()
        headers = [
            ("Content-Type", "application/pdf"),
            ("Content-Length", len(pdf)),
            ("Content-Disposition", content_disposition(_pdf_filename(title))),
        ]
        return request.make_response(pdf, headers=headers)

    @http.route("/odubook/guide/pdf", type="http", auth="user")
    def guide_pdf(self, module=None, book=None, section=None, lang=None, **kwargs):
        """Отдать PDF руководства модуля или одного его раздела.

        Ссылку открывает сам браузер, поэтому раздел приходит якорем заголовка
        в адресе; имя файла собирается из названия раздела.
        """
        if not module:
            raise request.not_found()
        document = request.env["odubook"].guide_pdf(
            module, book=book, section=section, lang=lang
        )
        if not document or not document.get("pdf"):
            raise request.not_found()
        pdf = document["pdf"]
        headers = [
            ("Content-Type", "application/pdf"),
            ("Content-Length", len(pdf)),
            ("Content-Disposition", content_disposition(_pdf_filename(document["title"]))),
        ]
        return request.make_response(pdf, headers=headers)

    @http.route("/odubook/guide/pdf/bundle", type="http", auth="user")
    def guide_bundle_pdf(self, sections=None, book=None, title=None, lang=None,
                         **kwargs):
        """Отдать один PDF из разделов, отмеченных читателем галочками.

        Разделы приходят строкой ``module|anchor,module|anchor``: ссылку
        открывает сам браузер, поэтому набор едет в адресе, а не в теле
        запроса. Пустой якорь означает руководство модуля целиком.
        """
        wanted = []
        for key in (sections or "").split(","):
            module_name, __, anchor = key.partition("|")
            if module_name:
                wanted.append({"module": module_name, "section": anchor or None})
        if not wanted:
            raise request.not_found()
        document = request.env["odubook"].guide_bundle_pdf(
            wanted, book=book, lang=lang, title=title or None
        )
        if not document or not document.get("pdf"):
            raise request.not_found()
        pdf = document["pdf"]
        headers = [
            ("Content-Type", "application/pdf"),
            ("Content-Length", len(pdf)),
            ("Content-Disposition", content_disposition(_pdf_filename(document["title"]))),
        ]
        return request.make_response(pdf, headers=headers)

    @http.route("/odubook/changes/read_all", type="jsonrpc", auth="user")
    def changes_read_all(self):
        return request.env["odubook"].mark_all_read()

    @http.route("/odubook/manuals", type="jsonrpc", auth="user")
    def manuals(self, lang=None):
        return request.env["odubook.manual"].get_manuals(lang=lang)

    @http.route("/odubook/manuals/read", type="jsonrpc", auth="user")
    def manual_read(self, manual_id=None, lang=None):
        return request.env["odubook.manual"].read_manual(manual_id, lang=lang)

    @http.route("/odubook/manuals/upload", type="jsonrpc", auth="user")
    def manual_upload(self, name=None, file_name=None, data=None, lang=None,
                      manual_id=None):
        # Право на создание проверяет ORM: полку ведёт администратор.
        return request.env["odubook.manual"].upload_manual(
            name, file_name, data, lang=lang, manual_id=manual_id
        )

    @http.route("/odubook/manuals/delete", type="jsonrpc", auth="user")
    def manual_delete(self, manual_id=None, lang=None):
        return request.env["odubook.manual"].delete_manual(manual_id, lang=lang)

    @http.route(
        "/odubook/manual/<int:file_id>/<string:filename>",
        type="http",
        auth="user",
    )
    def manual_content(self, file_id, filename, download=None, **kwargs):
        """Отдать байты языковой версии документа: просмотр или скачивание.

        Имя файла в пути нужно браузеру при сохранении; сам файл всегда берётся
        из записи, поэтому подставить чужое имя через URL нельзя.
        """
        version = request.env["odubook.manual.file"].browse(file_id).exists()
        if not version:
            raise request.not_found()
        try:
            version.check_access("read")
        except AccessError:
            raise request.not_found()
        content = base64.b64decode(version.file or b"")
        disposition = content_disposition(version.file_name or "document")
        if not download:
            disposition = disposition.replace("attachment;", "inline;", 1)
        headers = [
            ("Content-Type", version._mimetype_of(version.file_name)),
            ("Content-Length", len(content)),
            ("X-Content-Type-Options", "nosniff"),
            ("Content-Disposition", disposition),
        ]
        if version.kind == "html" or version.format == "SVG":
            headers.append(("Content-Security-Policy", HTML_SANDBOX_CSP))
        return request.make_response(content, headers=headers)
