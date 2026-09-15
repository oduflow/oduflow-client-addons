# -*- encoding: utf-8 -*-
"""Читаемый YAML-предпросмотр JSON-снимков MCP: диффа, результата, payload.

Свой минимальный дампер вместо PyYAML: библиотеки нет в зависимостях Odoo 15,
а снимки — простые деревья из dict/list/скаляров. Дампер сразу отдаёт HTML с
классами, поэтому подсветка обходится одним scss и не требует JS.
"""

import json
import re

from markupsafe import Markup

from odoo.tools import html_escape

REDACTED = "[REDACTED]"

# Слова, которые YAML прочитает как булево значение или null: такие строки
# обязаны быть в кавычках, иначе предпросмотр соврёт про тип значения.
_RESERVED = {"true", "false", "yes", "no", "on", "off", "null", "none", "~", "y", "n"}
_NUMBER = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")
_UNSAFE_HEAD = "-?:,[]{}#&*!|>'\"%@`"
_INDENT = "  "


def _is_plain(text):
    """Можно ли вывести строку без кавычек."""
    if not text or text != text.strip():
        return False
    if text.lower() in _RESERVED or _NUMBER.match(text):
        return False
    if text[0] in _UNSAFE_HEAD:
        return False
    # Двоеточие внутри строки YAML 1.1 читает как время ("12:30" → 750),
    # решётка — как начало комментария, поэтому такие строки закавычиваем.
    return ":" not in text and "#" not in text and "\n" not in text


def _span(text, css_class):
    return '<span class="o_mcp_yaml_%s">%s</span>' % (css_class, text)


def _quoted(text):
    return text if _is_plain(text) else json.dumps(text, ensure_ascii=False)


def _scalar(value):
    if value is None:
        return _span("null", "const")
    if value is True:
        return _span("true", "const")
    if value is False:
        return _span("false", "const")
    if isinstance(value, (int, float)):
        return _span(html_escape(str(value)), "num")
    text = value if isinstance(value, str) else str(value)
    css_class = "redacted" if text == REDACTED else "str"
    return _span(html_escape(_quoted(text)), css_class)


def _key(name):
    text = name if isinstance(name, str) else str(name)
    return _span(html_escape(_quoted(text)), "key") + _span(":", "punct")


def _render(value, depth):
    """Блок YAML уровня depth в виде списка готовых HTML-строк."""
    pad = _INDENT * depth
    lines = []
    if isinstance(value, dict):
        if not value:
            return [pad + _span("{}", "punct")]
        for key, item in value.items():
            head = pad + _key(key)
            if isinstance(item, dict):
                lines.append(head if item else head + " " + _span("{}", "punct"))
            elif isinstance(item, list):
                lines.append(head if item else head + " " + _span("[]", "punct"))
            else:
                lines.append(head + " " + _scalar(item))
                continue
            if item:
                lines.extend(_render(item, depth + 1))
        return lines
    if isinstance(value, list):
        if not value:
            return [pad + _span("[]", "punct")]
        for item in value:
            block = _render(item, depth + 1)
            # Первую строку вложенного блока подтягиваем к дефису, иначе
            # список словарей растягивается вдвое.
            lines.append(pad + _span("-", "punct") + " " + block[0][len(_INDENT * (depth + 1)):])
            lines.extend(block[1:])
        return lines
    return [pad + _scalar(value)]


def json_to_yaml_html(raw):
    """JSON-строку отдать подсвеченным YAML для readonly Html-поля."""
    if not raw:
        return False
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        # Не JSON — показываем исходный текст, экранируя его через Markup.
        return Markup('<pre class="o_mcp_yaml">%s</pre>') % raw
    return Markup('<pre class="o_mcp_yaml">%s</pre>' % "\n".join(_render(data, 0)))
