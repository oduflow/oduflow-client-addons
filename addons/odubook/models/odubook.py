# -*- coding: utf-8 -*-
import logging
import os
import re
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone

from psycopg2 import IntegrityError

from markupsafe import escape

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.modules.module import get_module_path

from .markdown import md_to_html, split_section, split_title

_logger = logging.getLogger(__name__)

#: Каталог пользовательской документации внутри модуля.
DOC_DIRNAME = "doc"
#: Имя руководства обычного пользователя.
GUIDE_FILENAME = "user_guide.md"
#: Имя руководства администратора: настройки и привилегированные операции.
ADMIN_GUIDE_FILENAME = "admin_guide.md"
#: Source-only technical audit report.
AUDIT_FILENAME = "module-audit.md"
#: Каталог дневной истории изменений документации.
CHANGES_DIRNAME = "changes"
#: Файл истории именуется по дате: ``YYYY-MM-DD.md``.
CHANGE_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")
#: Каталог зеркал перевода: ``doc/i18n/<lang>/<file>``.
I18N_DIRNAME = "i18n"
#: Исходный язык видимой документации: он же фолбэк любого документа, поэтому
#: в списке языков книги присутствует всегда.
SOURCE_LANG = "en"
#: Служебный маркер происхождения перевода, удаляемый перед рендерингом.
I18N_MARKER_RE = re.compile(r"\A<!--\s*i18n\b[^>]*-->[ \t]*\r?\n?")
#: Группа, необходимая для чтения документации администратора.
ADMIN_GROUP = "base.group_system"
#: Короткий код языка строчными буквами, необязательно с ``@variant``.
#: Другие значения отклоняются для защиты файлового пути.
LANG_CODE_RE = re.compile(r"^[a-z]{2,3}(@[a-z0-9]+)?$")
#: Один аномально большой файл не должен занимать всё время рендеринга.
MAX_DOC_BYTES = 1024 * 1024
#: Названия месяцев языков книги -- английского, польского и русского -- в
#: именительном и родительном падежах и английские сокращения. По ним заголовок
#: записи опознаётся как одна лишь дата.
MONTH_WORDS = frozenset(
    """
    january february march april may june july august september october
    november december jan feb mar apr jun jul aug sep sept oct nov dec
    styczeń stycznia luty lutego marzec marca kwiecień kwietnia maj maja
    czerwiec czerwca lipiec lipca sierpień sierpnia wrzesień września
    październik października listopad listopada grudzień grudnia
    январь января февраль февраля март марта апрель апреля май мая
    июнь июня июль июля август августа сентябрь сентября октябрь октября
    ноябрь ноября декабрь декабря
    """.split()
)
#: Слова-хвосты русской и польской даты: «27 августа 2026 г.», «27 sierpnia
#: 2026 r.». Названием записи они не являются.
DATE_TAIL_WORDS = frozenset(["г", "год", "года", "r", "rok", "roku"])
#: Разделитель даты и названия в заголовке записи: тире или двоеточие с
#: пробелом. Пробел обязателен, иначе разделителем стал бы дефис самой даты
#: ``2026-08-28``.
STAMP_SPLIT_RE = re.compile(r"(?:\s*[–—:]|\s+-)\s+")
#: Границы слов внутри даты: пробелы и знаки любого её написания.
STAMP_WORD_RE = re.compile(r"[\s,./|-]+")
#: Сколько дней запись летописи носит отметку «new».
NEW_ENTRY_DAYS = 3
#: Горизонт непрочитанного: более старые записи никогда не считаются
#: непрочитанными, иначе исторический архив выглядит стеной жирного текста.
UNREAD_HORIZON_DAYS = 90
#: Записи летописи внутри рабочей копии: pathspec одного вызова ``git log``.
CHANGE_PATHSPEC = "*%s/%s/*.md" % (DOC_DIRNAME, CHANGES_DIRNAME)
#: Git не должен подвесить веб-запрос.
GIT_TIMEOUT = 20
#: Как долго верим известной ветке публикации, не спрашивая git заново.
GIT_HEAD_TTL = 60
#: Ключ сортировки для ещё не опубликованной записи: она свежее любой даты.
NOT_PUBLISHED_SORT_KEY = "9999-12-31 23:59:59"
#: Ветка, попадание в которую и считается публикацией изменения.
PROD_BRANCH = "prod"
#: Где искать историю публикации, когда рабочая копия стоит не на prod.
#: Полные имена ссылок: короткое имя git разрешает неоднозначно.
PUBLICATION_REFS = ("refs/remotes/origin/%s" % PROD_BRANCH,
                    "refs/heads/%s" % PROD_BRANCH)

#: Каркас экспортируемого документа: wkhtmltopdf получает готовый HTML-файл,
#: а не фрагмент, поэтому кодировка и стили едут вместе с текстом.
PDF_DOCUMENT = """<!DOCTYPE html>
<html><head><meta charset="utf-8"/><style>%(style)s</style></head>
<body>%(body)s</body></html>"""
#: Печатный вид статей: экранная вёрстка книги на бумаге не нужна, нужен
#: читаемый текст и видимая граница между записями.
PDF_STYLE = """
body { font-family: sans-serif; font-size: 11pt; color: #212529; margin: 0; }
h1 { font-size: 17pt; margin: 0 0 0.5em; }
h1.cover { border-bottom: 1px solid #adb5bd; padding-bottom: 0.3em; }
h2 { font-size: 13pt; margin: 1em 0 0.4em; }
h3 { font-size: 12pt; margin: 1em 0 0.4em; }
section { margin-bottom: 1.5em; page-break-inside: avoid; }
p.meta { font-size: 9pt; color: #6c757d; text-transform: uppercase;
         letter-spacing: 0.04em; margin: 0 0 0.2em; }
table { border-collapse: collapse; }
td, th { border: 1px solid #adb5bd; padding: 0.2em 0.4em; }
pre { background: #f1f3f5; padding: 0.5em; white-space: pre-wrap; }
img { max-width: 100%; }
"""
#: Кэш Markdown: ``(filepath, strip_marker)`` -> ``(mtime, html)``.
#: Хранится в worker и инвалидируется при изменении mtime файла.
_RENDER_CACHE = {}
#: Кэш времени коммитов: корень репозитория -> ``(head, {путь: время})``.
_COMMIT_CACHE = {}
#: Кэш ветки публикации: корень -> ``(проверено_в, (ref, sha) или None)``.
_HEAD_CACHE = {}
#: Кэш корня рабочей копии: каталог -> корень или ``False``.
_ROOT_CACHE = {}
#: Одноразовый HOME для git и уже разрешённые в нём корни репозиториев.
_GIT_HOME = None
_GIT_SAFE_ROOTS = set()


def _is_date_stamp(text):
    """Состоит ли текст из одной лишь даты.

    Дату пишут по-разному -- ``2026-08-28``, ``August 2026``,
    ``August 14, 2026``, ``28 August 2026``, ``17 августа 2026``, -- поэтому
    разбираем не формат, а слова: год из четырёх цифр обязателен, а всё
    остальное -- день, номер месяца или его название на языке книги.
    """
    tokens = [token for token in STAMP_WORD_RE.split(text.strip()) if token]
    if not tokens:
        return False
    has_year = False
    for token in tokens:
        if token.isdigit():
            if len(token) == 4:
                has_year = True
            elif len(token) > 2:
                return False
        else:
            word = token.strip(".").lower()
            if word not in MONTH_WORDS and word not in DATE_TAIL_WORDS:
                return False
    return has_year


def _same_heading(first, second):
    """Одно ли и то же название: регистр и лишние пробелы значения не имеют."""
    return " ".join((first or "").split()).lower() == " ".join((second or "").split()).lower()


def strip_date_stamp(title):
    """Убрать из заголовка записи ведущую дату.

    День записи книга и так показывает рядом с ней, поэтому в заголовке он --
    шум. Возвращает ``""``, когда кроме даты в заголовке ничего нет: чем его
    заменить, решает читающая сторона.
    """
    if not title:
        return ""
    title = title.strip()
    parts = STAMP_SPLIT_RE.split(title, 1)
    if len(parts) == 2 and _is_date_stamp(parts[0]):
        return parts[1].strip()
    return "" if _is_date_stamp(title) else title


class OduBook(models.AbstractModel):
    """Сборщик документации установленных модулей.

    Модель не хранит данные: она читает пользовательские и административные
    руководства установленных модулей с диска. Технический ``tech_spec.md``
    намеренно не показывается пользователям.

    Книги показываются на языке пользователя: сначала ищется зеркало в
    ``doc/i18n/<lang>/``, затем исходный файл. История изменений не переводится.
    """

    _name = "odubook"
    _description = "User Book"

    @api.model
    def get_book(self, lang=None):
        """Собрать пользовательскую книгу из установленных модулей.

        Язык по умолчанию -- язык читателя, но он вправе выбрать любой из
        отданных языков: перевод бывает точнее исходника, а исходник -- свежее
        перевода.

        :param lang: короткий код языка, выбранный читателем вручную.
        :return: ``{"pages": [{"id", "module", "title", "html"}, ...],
            "languages": [{"code", "name"}, ...], "lang": ...}`` -- one page per
            module (its ``doc/user_guide.md``).
        """
        return self._book_data(GUIDE_FILENAME, lang)

    @api.model
    def get_admin_book(self, lang=None):
        """Собрать книгу администратора; доступ только системной группе.

        Формат совпадает с :meth:`get_book`, но источник — ``admin_guide.md``.

        :raise AccessError: when the caller is not a system administrator.
        :return: same shape as :meth:`get_book`.
        """
        if not self.env.user.has_group(ADMIN_GROUP):
            raise AccessError(_("Administrator access is required to read the Admin Book."))
        return self._book_data(ADMIN_GUIDE_FILENAME, lang)

    @api.model
    def get_audit_book(self, lang=None):
        """Return module audit reports for system administrators only."""
        filename = self._guide_filename("audit")
        return self._book_data(filename, lang)

    def _book_data(self, filename, lang):
        """Собрать книгу по одному документу модулей на выбранном языке."""
        languages = self._doc_languages(filename)
        selected = self._selected_lang(lang, languages)
        return {
            "pages": self._collect_pages(filename, selected),
            "languages": languages,
            "lang": selected,
        }

    def _doc_lang(self):
        """Вернуть короткий код языка документации текущего пользователя.

        Личная настройка ``odubook_lang_id`` перекрывает язык интерфейса,
        иначе значение берётся из контекста/пользователя (``en_US`` -> ``en``).
        Runtime не читает ``LANG.md``: зеркало используется при наличии,
        иначе возвращается исходный файл.
        """
        book_lang = self.env.user.sudo().odubook_lang_id.code
        lang = (
            book_lang or self.env.context.get("lang") or self.env.user.lang or "en"
        ).split("_")[0]
        # Не добавляем в путь непроверенное значение языка.
        if not LANG_CODE_RE.match(lang):
            return "en"
        return lang

    def _doc_languages(self, filename):
        """Языки, на которых документ есть хотя бы у одного модуля.

        Кнопка языка не должна обещать перевод, которого нет: список собирается
        по факту зеркал на диске. Исходный язык присутствует всегда -- на него
        откатывается каждый непереведённый документ.

        :param filename: имя файла в каталоге ``doc``; ``changes`` означает
            летопись, у которой зеркалится каталог, а не один файл.
        :return: ``[{"code", "name"}, ...]``, исходный язык первым.
        """
        if filename == AUDIT_FILENAME:
            return self._language_names([SOURCE_LANG])
        codes = set()
        for module in self._installed_modules():
            module_path = get_module_path(module.name)
            if not module_path:
                continue
            i18n_path = os.path.join(module_path, DOC_DIRNAME, I18N_DIRNAME)
            try:
                mirrors = os.listdir(i18n_path)
            except OSError:
                continue
            for code in mirrors:
                if code in codes or not LANG_CODE_RE.match(code):
                    continue
                if self._has_mirror(os.path.join(i18n_path, code), filename):
                    codes.add(code)
        codes.discard(SOURCE_LANG)
        return self._language_names([SOURCE_LANG] + sorted(codes))

    def _has_mirror(self, lang_path, filename):
        """Есть ли в зеркале языка запрошенный документ."""
        if filename != CHANGES_DIRNAME:
            return os.path.isfile(os.path.join(lang_path, filename))
        # Летопись переведена, если переведён хотя бы один её день.
        try:
            entries = os.listdir(os.path.join(lang_path, CHANGES_DIRNAME))
        except OSError:
            return False
        return any(CHANGE_FILE_RE.match(entry) for entry in entries)

    def _language_names(self, codes):
        """Дополнить коды языков названиями из ``res.lang``.

        Язык документации не обязан быть установлен в базе, поэтому названия
        ищутся и среди неактивных записей, а неизвестный код показывается сам
        собой.
        """
        names = {}
        languages = self.env["res.lang"].sudo().with_context(active_test=False).search([])
        for language in languages:
            names.setdefault(language.code.split("_")[0], language.name)
        return [{"code": code, "name": names.get(code, code.upper())} for code in codes]

    def _selected_lang(self, lang, languages):
        """Выбрать язык показа: запрошенный читателем, его собственный или исходный."""
        available = {language["code"] for language in languages}
        if lang and LANG_CODE_RE.match(lang) and lang in available:
            return lang
        reader = self._doc_lang()
        return reader if reader in available else SOURCE_LANG

    @api.model
    def get_ui_languages(self):
        """Языки интерфейса, доступные пользователю, и его собственный.

        Меню пользователя переключает язык всего Odoo, а не язык одной книги,
        поэтому список берётся из установленных языков базы.

        :return: ``{"current": "pl_PL", "languages": [{"code", "name"}, ...]}``.
        """
        languages = self.env["res.lang"].sudo().search([])
        return {
            "current": self.env.user.lang or "",
            "languages": [
                {"code": language.code, "name": language.name} for language in languages
            ],
        }

    @api.model
    def _installed_modules(self):
        """Вернуть установленные модули в стабильном порядке."""
        if not self.env.user.has_group("base.group_user"):
            raise AccessError(_("Internal user access is required to read documentation."))
        return self.env["ir.module.module"].sudo().search(
            [("state", "=", "installed")], order="name"
        )

    def _collect_pages(self, filename, lang):
        """Отрендерить ``doc/<filename>`` каждого opt-in модуля.

        :param filename: имя файла в каталоге ``doc`` модуля.
        :param lang: предпочтительный короткий код языка.
        :return: страницы модулей с читаемым файлом в порядке имени модуля.
        """
        pages = []
        for module in self._installed_modules():
            html = self._read_module_doc(module.name, filename, lang)
            if html is None:
                continue
            pages.append(
                {
                    "id": module.name,
                    "module": module.name,
                    "title": module.shortdesc or module.name,
                    "html": html,
                }
            )
        return pages

    def _module_doc_path(self, module_name, filename, lang):
        """Найти файл документа модуля на выбранном языке.

        Сначала ищется ``doc/i18n/<lang>/<filename>``, затем исходник.
        """
        module_path = get_module_path(module_name)
        if not module_path:
            return None
        candidates = [
            os.path.join(module_path, DOC_DIRNAME, I18N_DIRNAME, lang, filename),
            os.path.join(module_path, DOC_DIRNAME, filename),
        ]
        if filename == AUDIT_FILENAME:
            candidates = [os.path.join(module_path, DOC_DIRNAME, filename)]
        for filepath in candidates:
            if os.path.isfile(filepath):
                return filepath
        return None

    def _read_module_doc(self, module_name, filename, lang):
        """Прочитать и отрендерить документ модуля на указанном языке.

        Служебный i18n-маркер удаляется перед рендерингом.
        """
        filepath = self._module_doc_path(module_name, filename, lang)
        if not filepath:
            return None
        return self._render_doc_html(filepath, strip_marker=True)

    def _doc_stat(self, filepath):
        """Вернуть ``os.stat`` документа или ``None``, если читать его не стоит.

        Слишком большой файл до чтения не доходит: один аномальный документ не
        должен занимать всё время рендеринга.
        """
        try:
            stat = os.stat(filepath)
        except OSError:
            _logger.warning("odubook: failed to stat %s", filepath)
            return None
        if stat.st_size > MAX_DOC_BYTES:
            _logger.warning(
                "odubook: skipping oversized doc %s (%d bytes)",
                filepath,
                stat.st_size,
            )
            return None
        return stat

    def _doc_source(self, filepath, strip_marker):
        """Прочитать Markdown документа, убрав служебный i18n-маркер."""
        try:
            with open(filepath, "r", encoding="utf-8") as handle:
                raw = handle.read()
        except (OSError, UnicodeDecodeError):
            _logger.warning("odubook: failed to read %s", filepath)
            return None
        return I18N_MARKER_RE.sub("", raw, count=1) if strip_marker else raw

    def _render_doc_html(self, filepath, strip_marker):
        """Прочитать Markdown, убрать маркер перевода и вернуть HTML.

        Неизменившийся файл берётся из кэша. Слишком большой, нечитаемый или
        сломанный файл возвращает ``None`` и не ломает всю книгу.
        """
        stat = self._doc_stat(filepath)
        if stat is None:
            return None
        key = (filepath, strip_marker)
        cached = _RENDER_CACHE.get(key)
        if cached is not None and cached[0] == stat.st_mtime:
            return cached[1]
        raw = self._doc_source(filepath, strip_marker)
        if raw is None:
            return None
        try:
            html = md_to_html(raw)
        except Exception:  # noqa: BLE001 — one bad file must not sink the book
            _logger.exception("odubook: failed to render %s", filepath)
            return None
        _RENDER_CACHE[key] = (stat.st_mtime, html)
        return html

    def _render_change_entry(self, filepath):
        """Вернуть ``{"heading", "html"}`` записи летописи.

        Заголовок записи отделяется от текста и нормализуется: ведущая дата из
        него уходит, потому что день записи книга показывает и так. Пустой
        ``heading`` означает, что в заголовке не было ничего, кроме даты.
        """
        stat = self._doc_stat(filepath)
        if stat is None:
            return None
        key = (filepath, "entry")
        cached = _RENDER_CACHE.get(key)
        if cached is not None and cached[0] == stat.st_mtime:
            return cached[1]
        raw = self._doc_source(filepath, strip_marker=True)
        if raw is None:
            return None
        title, body = split_title(raw)
        try:
            entry = {"heading": strip_date_stamp(title), "html": md_to_html(body)}
        except Exception:  # noqa: BLE001 — one bad file must not sink the archive
            _logger.exception("odubook: failed to render %s", filepath)
            return None
        _RENDER_CACHE[key] = (stat.st_mtime, entry)
        return entry

    @api.model
    def get_changes(self, lang=None):
        """Собрать индекс летописи изменений без текста записей.

        Запись летописи -- пара ``(модуль, дата)``, то есть один файл
        ``doc/changes/YYYY-MM-DD.md``. Индекс намеренно не рендерит Markdown:
        клиент группирует записи по датам или по модулям, а текст запрашивает
        отдельно через :meth:`read_changes`.

        :param lang: короткий код языка, выбранный читателем вручную; индекс
            от него не зависит, но клиенту нужны кнопки языка и текущий выбор.
        :return: ``{"entries": [{"module", "title", "date", "published",
            "unread", "is_new"}, ...], "languages": [...], "lang": ...}`` --
            ordered by publication time descending, unpublished entries first,
            then by date descending, then module name.
        """
        today = fields.Date.context_today(self)
        horizon = today - timedelta(days=UNREAD_HORIZON_DAYS)
        new_from = today - timedelta(days=NEW_ENTRY_DAYS)
        read_keys = self._read_marks(since=horizon)
        entries = []
        for module in self._installed_modules():
            title = module.shortdesc or module.name
            for date_str, filepath in self._list_module_changes(module.name):
                date = fields.Date.to_date(date_str)
                unread = (module.name, date_str) not in read_keys
                entries.append(
                    {
                        "module": module.name,
                        "title": title,
                        "date": date_str,
                        "published": self._published_at(filepath),
                        "unread": unread and date >= horizon,
                        "is_new": unread and date >= new_from,
                    }
                )
        # Стабильная сортировка: сверху позднее опубликованное, при равном
        # времени -- свежая дата записи, дальше -- по модулю. Читателя
        # интересует не когда изменение написали, а когда оно доехало до него,
        # поэтому время публикации -- главный ключ. Ещё не опубликованное
        # (запись есть на диске, но в истории prod её нет) свежее всего
        # опубликованного и идёт первым.
        entries.sort(key=lambda entry: entry["module"])
        entries.sort(key=lambda entry: entry["date"], reverse=True)
        entries.sort(key=lambda entry: entry["published"] or NOT_PUBLISHED_SORT_KEY,
                     reverse=True)
        languages = self._doc_languages(CHANGES_DIRNAME)
        return {
            "entries": entries,
            "languages": languages,
            "lang": self._selected_lang(lang, languages),
        }

    def _published_at(self, filepath):
        """Вернуть время публикации записи (UTC, строкой) или ``False``.

        Опубликованной запись считается с того момента, как её файл влился в
        ветку публикации (:data:`PROD_BRANCH`): читателя интересует не когда
        изменение писали, а когда оно доехало до него. Берётся время
        последнего такого коммита -- дописанная позже запись публикуется
        заново. ``False`` значит «в истории публикации файла ещё нет»: так
        выглядит запись ветки, которую пока не влили.

        Вне git-рабочей копии и при недоступном git история неизвестна вовсе --
        тогда берётся mtime файла. Источник заведомо слабый (git при checkout
        переписывает файлы) и только запасной.
        """
        root = self._repo_root(os.path.dirname(filepath))
        if root:
            times = self._commit_times(root)
            if times is not None:
                return times.get(os.path.relpath(filepath, root), False)
        try:
            mtime = os.path.getmtime(filepath)
        except OSError:
            _logger.warning("odubook: failed to stat %s", filepath)
            return False
        return fields.Datetime.to_string(datetime.fromtimestamp(mtime, timezone.utc).replace(tzinfo=None))

    def _repo_root(self, dirpath):
        """Вернуть корень git-рабочей копии над каталогом или ``None``."""
        cached = _ROOT_CACHE.get(dirpath)
        if cached is not None:
            return cached or None
        current = os.path.abspath(dirpath)
        root = None
        while True:
            if os.path.exists(os.path.join(current, ".git")):
                root = current
                break
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
        _ROOT_CACHE[dirpath] = root or False
        return root

    def _commit_times(self, root):
        """Вернуть ``{путь от корня репозитория: время публикации}`` летописи.

        Считается по истории ветки публикации, а не рабочей копии: на проде это
        одно и то же, а в ветке разработчика -- нет.

        Один ``git log`` на репозиторий: 300 записей по отдельности стоили бы
        сотни процессов. Результат живёт до смены вершины этой ветки, а сама
        вершина переспрашивается не чаще, чем раз в :data:`GIT_HEAD_TTL` секунд.

        :return: словарь путей или ``None``, когда историю прочитать не вышло --
            это не то же самое, что пустая история, и вызывающий откатывается
            на mtime.
        """
        head = self._publication_head(root)
        if not head:
            return None
        cached = _COMMIT_CACHE.get(root)
        if cached is not None and cached[0] == head:
            return cached[1]
        times = {}
        output = self._git(
            root,
            ["log", "--format=%x00%ct", "--name-only", head[0], "--", CHANGE_PATHSPEC],
        )
        if output is None:
            return None
        for block in output.split("\0"):
            lines = [line for line in block.splitlines() if line]
            if not lines:
                continue
            try:
                stamp = fields.Datetime.to_string(datetime.fromtimestamp(int(lines[0]), timezone.utc).replace(tzinfo=None))
            except (ValueError, OverflowError, OSError):
                continue
            for path in lines[1:]:
                # git log идёт от свежих коммитов к старым, поэтому первое
                # попадание файла -- его последняя правка.
                times.setdefault(path, stamp)
        _COMMIT_CACHE[root] = (head, times)
        return times

    def _publication_head(self, root):
        """Вернуть ``(ref, sha)`` ветки публикации, спрашивая git раз в TTL.

        На проде рабочая копия стоит на :data:`PROD_BRANCH`, и его история --
        это HEAD. В ветке разработчика HEAD несёт ещё не влитые коммиты,
        поэтому история берётся из ``origin/prod`` или локального ``prod``.
        Когда ни того, ни другого нет (чужая рабочая копия, мелкий клон),
        остаётся HEAD: лучше приблизительное время, чем никакого.
        """
        cached = _HEAD_CACHE.get(root)
        now = time.time()
        if cached is not None and now - cached[0] < GIT_HEAD_TTL:
            return cached[1]
        branch = (self._git(root, ["rev-parse", "--abbrev-ref", "HEAD"]) or "").strip()
        refs = ["HEAD"] if branch == PROD_BRANCH else list(PUBLICATION_REFS) + ["HEAD"]
        head = None
        for ref in refs:
            # --quiet: отсутствующая ссылка -- штатный случай перебора, а не сбой.
            sha = (self._git(root, ["rev-parse", "--verify", "--quiet", ref],
                             quiet=True) or "").strip()
            if sha:
                head = (ref, sha)
                break
        _HEAD_CACHE[root] = (now, head)
        return head

    def _git(self, root, args, quiet=False):
        """Выполнить git в рабочей копии; вернуть stdout или ``None``.

        Ни отсутствие git, ни чужой репозиторий, ни таймаут не должны ронять
        летопись -- вызывающий откатывается на mtime.
        """
        try:
            result = subprocess.run(
                ["git", "-C", root] + args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=GIT_TIMEOUT,
                env=self._git_env(root),
            )
        except (OSError, subprocess.SubprocessError):
            _logger.warning("odubook: git %s failed in %s", args[0], root, exc_info=True)
            return None
        if result.returncode:
            if quiet:
                return None
            _logger.warning(
                "odubook: git %s failed in %s: %s",
                args[0],
                root,
                result.stderr.decode("utf-8", "replace").strip()[:200],
            )
            return None
        return result.stdout.decode("utf-8", "replace")

    def _git_env(self, root):
        """Окружение git с разрешением читать чужую рабочую копию.

        Odoo и рабочая копия обычно принадлежат разным пользователям, а git
        отказывается работать с таким репозиторием. ``safe.directory`` он берёт
        только из системного и глобального конфигов -- ни ``-c``, ни
        ``GIT_CONFIG_*`` не годятся, поэтому подкладываем собственный HOME.
        """
        global _GIT_HOME
        if _GIT_HOME is None:
            _GIT_HOME = tempfile.mkdtemp(prefix="odubook_git_")
        if root not in _GIT_SAFE_ROOTS:
            with open(os.path.join(_GIT_HOME, ".gitconfig"), "a", encoding="utf-8") as handle:
                handle.write("[safe]\n\tdirectory = %s\n" % root)
            _GIT_SAFE_ROOTS.add(root)
        return dict(
            os.environ,
            HOME=_GIT_HOME,
            GIT_TERMINAL_PROMPT="0",
            GIT_OPTIONAL_LOCKS="0",
        )

    @api.model
    def read_changes(self, entries, mark_read=True, lang=None):
        """Отрендерить запрошенные записи, по умолчанию отмечая прочитанными.

        Лента месяца грузит текст пачкой, а читатель видит его по мере
        прокрутки, поэтому она передаёт ``mark_read=False`` и отмечает записи
        отдельно через :meth:`mark_entries_read`.

        :param entries: ``[{"module": ..., "date": "YYYY-MM-DD"}, ...]``;
            неизвестные модули, кривые даты и отсутствующие файлы отбрасываются
            молча, чтобы клиент не мог насыпать произвольных отметок.
        :param mark_read: отметить отрендеренные записи прочитанными.
        :param lang: короткий код языка, выбранный читателем вручную; по
            умолчанию берётся язык его профиля.
        :return: ``{"entries": {"<module>|<date>": {"heading", "html"}, ...}}``;
            пустой ``heading`` -- заголовок записи состоял из одной даты.
        """
        installed = set(self._installed_modules().mapped("name"))
        docs_by_key = {}
        keys = set()
        for entry in entries or []:
            module_name = (entry or {}).get("module")
            date_str = (entry or {}).get("date")
            if module_name not in installed or (module_name, date_str) in keys:
                continue
            filepath = self._change_filepath(module_name, date_str, lang)
            if not filepath:
                continue
            # Взятое зеркало начинается со служебного i18n-маркера; в исходнике
            # маркера нет, поэтому снимать его можно безусловно.
            doc = self._render_change_entry(filepath)
            if doc is None:
                continue
            keys.add((module_name, date_str))
            docs_by_key["%s|%s" % (module_name, date_str)] = doc
        if mark_read:
            self._mark_read(keys)
        return {"entries": docs_by_key}

    @api.model
    def change_pdf(self, entries, title=None, lang=None):
        """Собрать PDF из статей летописи в порядке, заданном читателем.

        Экспортируется то же, что читатель видит под заголовком: одна запись
        или все записи открытой группы. Отметки прочитанного экспорт не трогает
        -- скачать не значит прочитать.

        :param entries: ``[{"module", "date"}, ...]``; проверяются как в
            :meth:`read_changes`.
        :param title: заголовок первой страницы; по умолчанию его нет.
        :param lang: короткий код языка, выбранный читателем вручную.
        :return: содержимое PDF байтами.
        :raise UserError: when the server carries no usable wkhtmltopdf.
        """
        report = self._pdf_report()
        docs = self.read_changes(entries, mark_read=False, lang=lang)["entries"]
        titles = {module.name: module.shortdesc or module.name
                  for module in self._installed_modules()}
        parts = []
        for entry in entries or []:
            key = "%s|%s" % ((entry or {}).get("module"), (entry or {}).get("date"))
            doc = docs.get(key)
            if not doc:
                continue
            module_name, __, date_str = key.partition("|")
            # Заголовок обложки и название единственной статьи под ним -- одна
            # и та же строка: печатать её дважды незачем.
            heading = doc["heading"]
            if heading and _same_heading(heading, title):
                heading = ""
            parts.append(
                '<section><p class="meta">%s &middot; %s</p>%s%s</section>'
                % (
                    escape(titles.get(module_name, module_name)),
                    escape(date_str),
                    "<h1>%s</h1>" % escape(heading) if heading else "",
                    doc["html"],
                )
            )
        if not parts:
            return None
        return report._run_wkhtmltopdf([self._pdf_document(title, parts)])

    @api.model
    def guide_pdf(self, module, book=None, section=None, lang=None):
        """Собрать PDF руководства модуля или одного его раздела.

        Экспортируется то же, что читатель видит под заголовком: весь документ,
        когда ``section`` не задан, иначе -- раздел с этим якорем вместе со
        всеми вложенными подразделами.

        :param module: техническое имя установленного модуля.
        :param book: ``"admin"`` or ``"audit"`` for restricted books; otherwise user.
        :param section: якорь заголовка (``id`` в отрендеренном HTML).
        :param lang: короткий код языка, выбранный читателем вручную.
        :return: ``{"title": ..., "pdf": ...}`` или ``None``, если документа
            или раздела нет.
        :raise AccessError: when a non-administrator asks for a restricted book.
        """
        filename = self._guide_filename(book)
        selected = self._selected_lang(lang, self._doc_languages(filename))
        part = self._guide_part(module, filename, selected, section=section)
        if part is None:
            return None
        title, html = part
        report = self._pdf_report()
        parts = ['<section>%s</section>' % html]
        return {
            "title": title,
            "pdf": report._run_wkhtmltopdf([self._pdf_document(title, parts)]),
        }

    @api.model
    def guide_bundle_pdf(self, sections, book=None, lang=None, title=None):
        """Собрать один PDF из разделов, отмеченных читателем галочками.

        Разделы идут в том порядке, в каком их прислал клиент, и могут
        приходить из разных руководств: набор собирается по всей книге.
        Повторы и разделы, которых в документе нет, отбрасываются молча --
        клиент мог отметить раздел до смены языка.

        :param sections: ``[{"module": ..., "section": ...}, ...]``; пустой
            ``section`` означает руководство модуля целиком.
        :param book: ``"admin"`` or ``"audit"`` for restricted books; otherwise user.
        :param lang: короткий код языка, выбранный читателем вручную.
        :param title: заголовок обложки; по умолчанию общий.
        :return: ``{"title": ..., "pdf": ...}`` или ``None``, когда собирать
            нечего.
        :raise AccessError: when a non-administrator asks for a restricted book.
        """
        filename = self._guide_filename(book)
        selected = self._selected_lang(lang, self._doc_languages(filename))
        titles = {module.name: module.shortdesc or module.name
                  for module in self._installed_modules()}
        parts = []
        seen = set()
        for entry in sections or []:
            module_name = (entry or {}).get("module")
            anchor = (entry or {}).get("section") or None
            if (module_name, anchor) in seen:
                continue
            part = self._guide_part(module_name, filename, selected, section=anchor)
            if part is None:
                continue
            seen.add((module_name, anchor))
            heading, html = part
            module_title = titles.get(module_name, module_name)
            # У руководства целиком название модуля и заголовок документа --
            # одна и та же строка: печатать её дважды незачем.
            meta = "" if _same_heading(heading, module_title) else (
                '<p class="meta">%s</p>' % escape(module_title)
            )
            parts.append(
                "<section>%s<h1>%s</h1>%s</section>"
                % (meta, escape(heading), html)
            )
        if not parts:
            return None
        cover = title or _("Selected sections")
        report = self._pdf_report()
        return {
            "title": cover,
            "pdf": report._run_wkhtmltopdf([self._pdf_document(cover, parts)]),
        }

    def _guide_filename(self, book):
        """Имя файла запрошенной книги; книга администратора требует группы."""
        if book == "audit":
            if not self.env.user.has_group(ADMIN_GROUP):
                raise AccessError(_("Administrator access is required to read module audits."))
            return AUDIT_FILENAME
        if book == "admin":
            if not self.env.user.has_group(ADMIN_GROUP):
                raise AccessError(
                    _("Administrator access is required to read the Admin Book.")
                )
            return ADMIN_GUIDE_FILENAME
        return GUIDE_FILENAME

    def _guide_part(self, module, filename, lang, section=None):
        """Заголовок и HTML руководства модуля или одного его раздела.

        Возвращает ``(title, html)`` или ``None``, когда модуля, документа или
        якоря нет.
        """
        installed = self._installed_modules().filtered(lambda m: m.name == module)
        if not installed:
            return None
        filepath = self._module_doc_path(module, filename, lang)
        if not filepath or self._doc_stat(filepath) is None:
            return None
        raw = self._doc_source(filepath, strip_marker=True)
        if raw is None:
            return None
        if section:
            title, body = split_section(raw, section)
            if title is None:
                return None
        else:
            title, body = split_title(raw)
            title = title or installed.shortdesc or module
        return title, md_to_html(body)

    def _pdf_report(self):
        """Отчётный движок для экспорта; без wkhtmltopdf экспорта нет."""
        report = self.env["ir.actions.report"].sudo()
        if report.get_wkhtmltopdf_state() == "install":
            raise UserError(
                _("PDF export needs wkhtmltopdf, which is not installed on this server.")
            )
        return report

    def _pdf_document(self, title, parts):
        """Обернуть статьи в самостоятельный HTML: wkhtmltopdf читает файл."""
        heading = "<h1 class=\"cover\">%s</h1>" % escape(title) if title else ""
        return PDF_DOCUMENT % {"style": PDF_STYLE, "body": heading + "".join(parts)}

    @api.model
    def mark_entries_read(self, entries):
        """Отметить прочитанными записи, которые читатель действительно увидел.

        :param entries: ``[{"module": ..., "date": "YYYY-MM-DD"}, ...]``;
            проверяются так же, как в :meth:`read_changes`.
        """
        installed = set(self._installed_modules().mapped("name"))
        keys = set()
        for entry in entries or []:
            module_name = (entry or {}).get("module")
            date_str = (entry or {}).get("date")
            if module_name not in installed or (module_name, date_str) in keys:
                continue
            if not self._change_filepath(module_name, date_str):
                continue
            keys.add((module_name, date_str))
        self._mark_read(keys)
        return True

    @api.model
    def mark_all_read(self):
        """Отметить прочитанными все записи летописи, лежащие на диске."""
        keys = set()
        for module in self._installed_modules():
            for date_str, __ in self._list_module_changes(module.name):
                keys.add((module.name, date_str))
        self._mark_read(keys)
        return True

    def _read_marks(self, since=None):
        """Вернуть ``{(module, "YYYY-MM-DD")}`` отметок текущего пользователя."""
        domain = [("user_id", "=", self.env.uid)]
        if since:
            domain.append(("change_date", ">=", since))
        marks = self.env["odubook.change.read"].search(domain)
        return {
            (mark.module, fields.Date.to_string(mark.change_date)) for mark in marks
        }

    def _mark_read(self, keys):
        """Досоздать недостающие отметки прочтения для текущего пользователя."""
        missing = set(keys) - self._read_marks()
        if not missing:
            return
        values = [
            {"user_id": self.env.uid, "module": module_name, "change_date": date_str}
            for module_name, date_str in sorted(missing)
        ]
        try:
            # Параллельная вкладка могла отметить то же самое: уникальный индекс
            # не должен ронять запрос, отметки досоздадутся при следующем показе.
            with self.env.cr.savepoint():
                self.env["odubook.change.read"].create(values)
        except IntegrityError:
            _logger.debug("odubook: concurrent read marks skipped")

    def _list_module_changes(self, module_name):
        """Вернуть ``(date_str, filepath)`` для ``doc/changes/*.md`` модуля.

        Markdown не читается и не рендерится: метод обслуживает индекс.
        Учитываются только файлы ``YYYY-MM-DD.md``.
        """
        module_path = get_module_path(module_name)
        if not module_path:
            return []
        changes_dir = os.path.join(module_path, DOC_DIRNAME, CHANGES_DIRNAME)
        if not os.path.isdir(changes_dir):
            return []
        result = []
        for filename in sorted(os.listdir(changes_dir)):
            match = CHANGE_FILE_RE.match(filename)
            if not match:
                continue
            result.append((match.group(1), os.path.join(changes_dir, filename)))
        return result

    def _change_filepath(self, module_name, date_str, lang=None):
        """Вернуть путь к файлу записи или ``None``.

        Сначала ищется зеркало перевода ``doc/i18n/<lang>/changes/``, затем
        исходник -- как и у руководств, откат выполняется по каждой записи
        отдельно. Имя файла проверяется тем же шаблоном, что и при обходе
        каталога, -- в путь не попадает непроверенное значение даты.

        :param lang: язык, выбранный читателем; непонятное значение
            игнорируется, и берётся язык его профиля.
        """
        if not isinstance(date_str, str) or not CHANGE_FILE_RE.match("%s.md" % date_str):
            return None
        module_path = get_module_path(module_name)
        if not module_path:
            return None
        filename = "%s.md" % date_str
        wanted = lang if lang and LANG_CODE_RE.match(lang) else self._doc_lang()
        candidates = [
            os.path.join(
                module_path,
                DOC_DIRNAME,
                I18N_DIRNAME,
                wanted,
                CHANGES_DIRNAME,
                filename,
            ),
            os.path.join(module_path, DOC_DIRNAME, CHANGES_DIRNAME, filename),
        ]
        for filepath in candidates:
            if os.path.isfile(filepath):
                return filepath
        return None
