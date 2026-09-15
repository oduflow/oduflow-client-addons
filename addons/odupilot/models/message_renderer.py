# -*- encoding: utf-8 -*-
import re

from lxml import etree
from lxml import html as lxml_html
from markdown_it import MarkdownIt
from markupsafe import Markup, escape

from odoo import tools


_MARKDOWN = MarkdownIt('commonmark', {
    'breaks': True,
    'html': True,
    'linkify': True,
}).enable([
    'linkify',
    'strikethrough',
    'table',
])

# Модель не знает адреса Odoo, поэтому по системной инструкции ссылается на
# запись компактным маркером odoo://<модель>/<id>. Собственную схему вырезал бы
# html_sanitize, поэтому маркер разворачивается в обычный URL до рендера.
_RECORD_MARKER = re.compile(r'odoo://([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+)/(\d+)')

_TRACE_TEMPLATE = (
    '<details class="o_AiChatTrace o_AiChatTrace_%(kind)s">'
    '<summary class="o_AiChatTrace_summary">'
    '<i class="fa %(icon)s" aria-hidden="true"></i> %(summary)s'
    '</summary>'
    '<div class="o_AiChatTrace_body">%(body)s</div>'
    '</details>'
)


def _source_text(text, *args):
    return text % args if args else text


def render_assistant_message(text, base_url=''):
    """Отрисовать CommonMark и HTML модели как безопасный mail.message."""
    return _sanitize(_render_markdown(text, base_url))


def render_assistant_blocks(blocks, base_url='', env=None):
    """Отрисовать шаг ответа: рассуждения и вызовы инструментов — свёрнутыми
    блоками, сам ответ — обычным Markdown.

    Идущие подряд служебные блоки собираются в одну свёрнутую группу: цепочка
    из десятка вызовов инструментов иначе занимает весь экран и прячет ответ.
    """
    translate = env._ if env is not None else _source_text
    chunks = []
    group = []
    for block in blocks or []:
        block_type = block.get('type')
        if block_type in ('reasoning', 'tool'):
            group.append(block)
            continue
        chunks.append(_render_group(group, base_url, translate))
        group = []
        if block_type == 'text':
            chunks.append(_render_markdown(block.get('text'), base_url))
    chunks.append(_render_group(group, base_url, translate))
    return _sanitize(''.join(chunks))


def trace_group_summary(blocks, _):
    """Заголовок свёрнутой группы служебных блоков."""
    tools = []
    for block in blocks:
        tool = (block.get('tool') or '').strip()
        if block.get('type') == 'tool' and tool and tool not in tools:
            tools.append(tool)
    count = len(blocks)
    summary = (
        _('AI work: 1 step') if count == 1
        else _('AI work: %s steps', count))
    if not tools:
        return summary
    shown = ', '.join(tools[:3])
    if len(tools) > 3:
        shown = '%s, …' % shown
    return '%s (%s)' % (summary, shown)


def tool_status_label(status, _):
    """Человекочитаемое состояние вызова инструмента."""
    if status == 'error':
        return _('Tool call failed')
    if status == 'running':
        return _('Tool call in progress')
    if status == 'pending':
        return _('Tool call requested')
    return _('Tool call finished')


def _render_markdown(text, base_url):
    source = str(text or '').replace('\r\n', '\n').replace('\r', '\n')
    if not source.strip():
        return ''
    source = _expand_record_links(source, base_url)
    return _decorate_tables(_MARKDOWN.render(source))


def _sanitize(rendered):
    return Markup(tools.html_sanitize(
        rendered,
        sanitize_attributes=True,
        sanitize_style=True,
    ))


def _render_trace(kind, icon, summary, body):
    return _TRACE_TEMPLATE % {
        'kind': kind,
        'icon': icon,
        'summary': escape(summary),
        'body': body,
    }


def _render_group(blocks, base_url, _):
    """Служебные блоки хода: цепочка — одной свёрнутой группой."""
    if not blocks:
        return ''
    rendered = ''.join(
        _render_reasoning(block, base_url, _) if block.get('type') == 'reasoning'
        else _render_tool(block, _)
        for block in blocks
    )
    if len(blocks) == 1:
        return rendered
    return _render_trace(
        'group', 'fa-tasks', trace_group_summary(blocks, _), rendered)


def _render_reasoning(block, base_url, _):
    return _render_trace(
        'reasoning',
        'fa-lightbulb-o',
        _('AI reasoning'),
        _render_markdown(block.get('text'), base_url),
    )


def _render_tool(block, _):
    name = (block.get('tool') or '').strip()
    summary = tool_status_label(block.get('status'), _)
    if name:
        summary = '%s: %s' % (summary, name)
    body = []
    title = (block.get('title') or '').strip()
    if title:
        body.append('<p class="o_AiChatTrace_title">%s</p>' % escape(title))
    for label, value in (
            (_('Tool input'), block.get('input')),
            (_('Tool output'), block.get('output'))):
        if not value:
            continue
        body.append(
            '<p class="o_AiChatTrace_label">%s</p>'
            '<pre class="o_AiChatTrace_code">%s</pre>' % (
                escape(label), escape(value)))
    return _render_trace('tool', 'fa-wrench', summary, ''.join(body))


def _expand_record_links(source, base_url):
    """Развернуть маркеры записей в ссылки на форму Odoo."""
    root = (base_url or '').rstrip('/')
    return _RECORD_MARKER.sub(
        lambda match: '%s/web#model=%s&id=%s&view_type=form' % (
            root, match.group(1), match.group(2)),
        source,
    )


def _decorate_tables(rendered):
    root = lxml_html.fragment_fromstring(rendered, create_parent='div')
    for table in root.xpath('.//table'):
        classes = set((table.get('class') or '').split())
        classes.update(('table', 'table-sm', 'table-bordered', 'table-hover'))
        table.set('class', ' '.join(sorted(classes)))
        parent = table.getparent()
        if parent is None or parent.get('class') == 'table-responsive':
            continue
        wrapper = etree.Element('div', {'class': 'table-responsive'})
        parent.replace(table, wrapper)
        wrapper.append(table)
    return ''.join(
        etree.tostring(
            child,
            encoding='unicode',
            method='html',
        )
        for child in root
    )
