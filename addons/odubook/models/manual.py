# -*- coding: utf-8 -*-
import base64
import logging
import os
import re
from urllib.parse import quote

from markupsafe import escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .markdown import md_to_html

_logger = logging.getLogger(__name__)

#: Расширение файла решает, как документ показывается читателю. MIME-тип,
#: присланный браузером, для этого не годится: он зависит от ОС загрузившего.
KIND_BY_EXTENSION = {
    "md": "markdown",
    "markdown": "markdown",
    "txt": "text",
    "log": "text",
    "csv": "text",
    "html": "html",
    "htm": "html",
    "pdf": "pdf",
    "png": "image",
    "jpg": "image",
    "jpeg": "image",
    "gif": "image",
    "svg": "image",
    "webp": "image",
    "bmp": "image",
}
#: Файлы, чей текст модуль рендерит сам; для остальных браузер получает байты.
RENDERED_KINDS = ("markdown", "text")
#: Полка рассчитана на документы, а не на дистрибутивы.
MAX_MANUAL_BYTES = 25 * 1024 * 1024
#: Отрендеренный текст не должен занимать всё время запроса.
MAX_RENDERED_BYTES = 4 * 1024 * 1024
#: MIME-тип отдаваемого файла, когда расширение ни о чём не говорит.
FALLBACK_MIMETYPE = "application/octet-stream"
MIMETYPE_BY_EXTENSION = {
    "md": "text/markdown",
    "markdown": "text/markdown",
    "txt": "text/plain",
    "log": "text/plain",
    "csv": "text/csv",
    "html": "text/html",
    "htm": "text/html",
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "svg": "image/svg+xml",
    "webp": "image/webp",
    "bmp": "image/bmp",
}
#: Язык версии документа: короткий код (``en``), как и у книжных зеркал.
LANG_CODE_RE = re.compile(r"^[a-z]{2,3}$")
#: Язык, на который откатывается полка, когда версии на языке читателя нет.
FALLBACK_LANG = "en"


class OduBookManual(models.Model):
    """Документ, вложенный в книгу вручную.

    В отличие от руководств и летописи, эти документы не собираются с диска
    модулей: их кладёт на полку администратор, а формат может быть любым --
    Markdown, HTML-артефакт, PDF, картинка или файл, который остаётся только
    скачать.

    Один документ -- одна карточка на полке и один или несколько файлов, по
    файлу на язык. Читатель получает версию своего языка, а при её отсутствии
    -- английскую или единственную имеющуюся.
    """

    _name = "odubook.manual"
    _description = "Manual"
    _order = "sequence, name, id"

    name = fields.Char(string="Title", required=True)
    sequence = fields.Integer(string="Sequence", default=10)
    file_ids = fields.One2many(
        "odubook.manual.file",
        "manual_id",
        string="Language Versions",
    )
    active = fields.Boolean(string="Active", default=True)

    def _can_edit(self):
        """Полку ведёт администратор: остальные её только читают."""
        return self.has_access("create")

    @api.model
    def _reader_lang(self):
        """Короткий код языка читателя (``pl_PL`` -> ``pl``).

        Личная настройка языка Книги важнее языка интерфейса.
        """
        book_lang = self.env.user.sudo().odubook_lang_id.code
        lang = (
            book_lang or self.env.context.get("lang") or self.env.user.lang or "en"
        ).split("_")[0]
        return lang if LANG_CODE_RE.match(lang) else "en"

    def _version_for(self, lang=None):
        """Вернуть версию документа для языка читателя.

        Порядок: точное совпадение языка, затем английская версия, затем первая
        по порядку -- документ, вложенный на одном языке, читают все.
        """
        self.ensure_one()
        versions = self.file_ids
        if not versions:
            return versions
        wanted = lang or self._reader_lang()
        for candidate in (wanted, FALLBACK_LANG):
            match = versions.filtered(lambda version: version.lang == candidate)
            if match:
                return match[0]
        return versions[0]

    @api.model
    def get_manuals(self, lang=None):
        """Собрать полку для сайдбара: карточки, языки и ссылки на содержимое.

        Текст в индекс не попадает: клиент запрашивает его отдельно через
        :meth:`read_manual`, когда читатель открывает документ.

        :param lang: язык, выбранный читателем вручную; по умолчанию его
            собственный язык.
        :return: ``{"can_edit": bool, "languages": [{"code", "name"}, ...],
            "manuals": [...]}`` -- in shelf order.
        """
        # Карточка без файлов -- след неудачной загрузки: читателю показывать
        # нечего, поэтому на полку она не попадает.
        manuals = self.search([("file_ids", "!=", False)])
        return {
            "can_edit": self._can_edit(),
            "languages": self._available_languages(),
            "manuals": [manual._manual_data(lang) for manual in manuals],
        }

    @api.model
    def _available_languages(self):
        """Языки, установленные в базе: короткий код и название."""
        languages = []
        seen = set()
        for language in self.env["res.lang"].sudo().search([]):
            code = language.code.split("_")[0]
            if code in seen or not LANG_CODE_RE.match(code):
                continue
            seen.add(code)
            languages.append({"code": code, "name": language.name})
        return languages

    def _manual_data(self, lang=None):
        """Описание одного документа для клиента."""
        self.ensure_one()
        version = self._version_for(lang)
        url = version._content_url() if version else False
        return {
            "id": self.id,
            "name": self.name,
            "langs": sorted(self.file_ids.mapped("lang")),
            "lang": version.lang if version else False,
            "file_name": version.file_name if version else False,
            "kind": version.kind if version else False,
            "format": version.format if version else False,
            "url": url,
            "download_url": "%s?download=1" % url if url else False,
        }

    @api.model
    def read_manual(self, manual_id, lang=None):
        """Вернуть готовый к показу текст документа.

        Рендерится только то, что модуль показывает своими силами: Markdown и
        обычный текст. HTML, PDF, картинки и прочие файлы браузер получает
        байтами по ссылке из индекса.

        :param manual_id: идентификатор документа.
        :param lang: язык версии; по умолчанию язык читателя.
        :return: ``{"id", "lang", "kind", "html"}``; ``html`` -- ``False`` для
            видов, которые модуль не рендерит, и для нечитаемого файла.
        """
        manual = self.browse(int(manual_id)).exists()
        if not manual:
            return {"id": False, "lang": False, "kind": False, "html": False}
        # Обычное чтение: право проверяет ORM, документ виден всем сотрудникам.
        manual.check_access("read")
        version = manual._version_for(lang)
        if not version:
            return {"id": manual.id, "lang": False, "kind": False, "html": False}
        return {
            "id": manual.id,
            "lang": version.lang,
            "kind": version.kind,
            "html": version._render_html(),
        }

    @api.model
    def upload_manual(self, name, file_name, data, lang=None, manual_id=None):
        """Положить документ на полку и вернуть обновлённый индекс.

        Право проверяет ORM: создавать записи может только администратор.

        :param name: заголовок в сайдбаре; пустой заменяется именем файла.
        :param file_name: имя файла с расширением -- оно решает вид документа.
        :param data: содержимое файла в base64.
        :param lang: язык версии; по умолчанию язык загружающего.
        :param manual_id: документ, к которому добавляется языковая версия;
            без него создаётся новая карточка полки. Версия того же языка
            заменяется, а не задваивается.
        :return: тот же словарь, что и :meth:`get_manuals`.
        """
        file_name = (file_name or "").strip()
        if not file_name or not data:
            raise UserError(_("Select a file to upload."))
        code = (lang or self._reader_lang()).split("_")[0]
        if not LANG_CODE_RE.match(code):
            raise UserError(_("Select a language for this document."))
        values = {"lang": code, "file_name": file_name, "file": data}
        manual = self.browse(int(manual_id)).exists() if manual_id else self.browse()
        if manual:
            existing = manual.file_ids.filtered(lambda version: version.lang == code)
            if existing:
                existing.write(values)
            else:
                self.env["odubook.manual.file"].create(dict(values, manual_id=manual.id))
        else:
            title = (name or "").strip() or os.path.splitext(file_name)[0]
            self.create({"name": title, "file_ids": [(0, 0, values)]})
        return self.get_manuals()

    @api.model
    def delete_manual(self, manual_id, lang=None):
        """Снять документ (или одну его языковую версию) с полки.

        :param lang: язык удаляемой версии; без него уходит вся карточка.
        :return: тот же словарь, что и :meth:`get_manuals`.
        """
        manual = self.browse(int(manual_id)).exists()
        if manual and lang:
            version = manual.file_ids.filtered(lambda item: item.lang == lang)
            # Последняя версия уходит вместе с карточкой: пустая карточка на
            # полке читателю не нужна.
            if version and len(manual.file_ids) > 1:
                version.unlink()
            else:
                manual.unlink()
        elif manual:
            manual.unlink()
        return self.get_manuals()


class OduBookManualFile(models.Model):
    """Один файл документа: его версия на одном языке."""

    _name = "odubook.manual.file"
    _description = "Manual File"
    _order = "lang, id"

    manual_id = fields.Many2one(
        "odubook.manual",
        string="Manual",
        required=True,
        index=True,
        ondelete="cascade",
    )
    lang = fields.Char(string="Language", required=True, index=True)
    file = fields.Binary(string="File", attachment=True, required=True)
    file_name = fields.Char(string="File Name", required=True)
    # Вид рассчитывается один раз при загрузке: имя файла после неё не меняется,
    # а читающий endpoint не должен разбирать расширение на каждый запрос.
    kind = fields.Selection(
        [
            ("markdown", "Markdown"),
            ("text", "Plain text"),
            ("html", "HTML"),
            ("pdf", "PDF"),
            ("image", "Image"),
            ("download", "Download only"),
        ],
        string="Kind",
        compute="_compute_kind",
        store=True,
        readonly=True,
    )
    format = fields.Char(
        string="Format",
        compute="_compute_kind",
        store=True,
        readonly=True,
    )

    _sql_constraints = [('odubook_manual_file_lang_uniq', 'unique(manual_id, lang)', 'A manual may carry only one file per language.')]

    @api.depends("file_name")
    def _compute_kind(self):
        for version in self:
            version.kind = self._kind_of(version.file_name)
            version.format = self._format_of(version.file_name)

    @api.constrains("file")
    def _check_file_size(self):
        for version in self:
            if self._decoded_size(version.file) > MAX_MANUAL_BYTES:
                raise ValidationError(
                    _("A manual may not be larger than %s MB.")
                    % (MAX_MANUAL_BYTES // (1024 * 1024))
                )

    @api.constrains("lang")
    def _check_lang(self):
        for version in self:
            if not LANG_CODE_RE.match(version.lang or ""):
                raise ValidationError(
                    _("A manual language must be a short code such as “en”.")
                )

    @api.model
    def _kind_of(self, file_name):
        """Вернуть вид документа по расширению имени файла."""
        extension = os.path.splitext(file_name or "")[1].lstrip(".").lower()
        return KIND_BY_EXTENSION.get(extension, "download")

    @api.model
    def _format_of(self, file_name):
        """Вернуть расширение файла для показа рядом с заголовком."""
        extension = os.path.splitext(file_name or "")[1].lstrip(".").upper()
        return extension or "FILE"

    @api.model
    def _mimetype_of(self, file_name):
        """Вернуть MIME-тип для отдачи файла браузеру."""
        extension = os.path.splitext(file_name or "")[1].lstrip(".").lower()
        return MIMETYPE_BY_EXTENSION.get(extension, FALLBACK_MIMETYPE)

    @api.model
    def _decoded_size(self, data):
        """Вернуть размер вложения в байтах по его base64-представлению."""
        if not data:
            return 0
        # base64 кодирует три байта четырьмя символами; хвостовые "=" не в счёт.
        raw = data if isinstance(data, bytes) else data.encode("ascii", "ignore")
        return (len(raw) * 3) // 4 - raw.count(b"=")

    def _content_url(self):
        """Ссылка на байты версии; имя файла в пути ради скачивания."""
        self.ensure_one()
        return "/odubook/manual/%s/%s" % (
            self.id, quote(self.file_name or "document", safe="")
        )

    def _render_html(self):
        """Отрендерить текстовый документ; вернуть ``False``, если это не он."""
        self.ensure_one()
        if self.kind not in RENDERED_KINDS:
            return False
        if self._decoded_size(self.file) > MAX_RENDERED_BYTES:
            _logger.warning("odubook: manual file %s is too large to render", self.id)
            return False
        try:
            raw = base64.b64decode(self.file or b"").decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            _logger.warning("odubook: manual file %s is not readable UTF-8", self.id)
            return False
        if self.kind == "text":
            # Обычный текст показываем как есть, экранированным: разметки в нём
            # нет, а переносы строк значимы.
            return "<pre>%s</pre>" % str(escape(raw))
        try:
            return md_to_html(raw)
        except Exception:  # noqa: BLE001 — сломанный документ не ломает полку
            _logger.exception("odubook: failed to render manual file %s", self.id)
            return False
