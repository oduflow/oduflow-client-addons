# -*- encoding: utf-8 -*-

from odoo.tests.common import TransactionCase

from ..models.markdown import md_to_html, split_section, split_title


class TestMarkdown(TransactionCase):

    def test_supported_markdown(self):
        source = """# Title

**Bold** and *italic* with `code`.

| A | B |
|---|---|
| 1 | 2 |

```diff
+added
-removed
```
"""
        html = md_to_html(source)

        self.assertIn('<h1 id="title">Title</h1>', html)
        self.assertIn("<strong>Bold</strong>", html)
        self.assertIn("<em>italic</em>", html)
        self.assertIn("<code>code</code>", html)
        self.assertIn("<table>", html)
        self.assertIn('class="o_diff_add"', html)
        self.assertIn('class="o_diff_del"', html)

    def test_unsafe_html_and_urls_are_neutralized(self):
        source = '<script>alert(1)</script> [bad](javascript:alert) ![x](data:text/html)'
        html = md_to_html(source)

        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("javascript:", html)
        self.assertNotIn("data:text", html)
        self.assertEqual(html.count('="#"'), 2)

    def test_safe_and_relative_urls_are_preserved(self):
        html = md_to_html("[web](https://example.com) [local](/web#id=1)")

        self.assertIn('href="https://example.com"', html)
        self.assertIn('href="/web#id=1"', html)

    def test_split_title_takes_only_a_leading_first_level_heading(self):
        title, rest = split_title("# Title\n\nBody.")
        deeper, kept = split_title("## Subtitle\n\nBody.")

        self.assertEqual(title, "Title")
        self.assertEqual(rest.strip(), "Body.")
        # Заголовок второго уровня названием документа не считается.
        self.assertEqual(deeper, "")
        self.assertIn("## Subtitle", kept)

    def test_split_section_keeps_subsections_and_stops_at_a_peer(self):
        text = (
            "# Guide\n\nIntro.\n\n## Daily work\n\nBody.\n\n"
            "### Details\n\nMore.\n\n## Settings\n\nOther.\n"
        )

        title, body = split_section(text, "daily-work")

        self.assertEqual(title, "Daily work")
        self.assertIn("Body.", body)
        self.assertIn("### Details", body)
        self.assertNotIn("Other.", body)

    def test_split_section_of_the_document_title_takes_everything(self):
        text = "# Guide\n\nIntro.\n\n## Daily work\n\nBody.\n"

        title, body = split_section(text, "guide")

        self.assertEqual(title, "Guide")
        self.assertIn("Body.", body)

    def test_split_section_ignores_headings_inside_code_and_unknown_anchors(self):
        text = "# Guide\n\n```\n## Fenced\n```\n\nTail.\n"

        self.assertEqual(split_section(text, "fenced"), (None, ""))
        self.assertIn("Tail.", split_section(text, "guide")[1])

    def test_split_section_does_not_close_fence_on_an_info_string(self):
        text = (
            "## Section\n\nBefore.\n\n```text\n```python\n## Code sample\n```\n\n"
            "After.\n\n## Next\n\nOther.\n"
        )

        title, body = split_section(text, "section")

        self.assertEqual(title, "Section")
        self.assertIn("## Code sample", body)
        self.assertIn("After.", body)
        self.assertNotIn("Other.", body)
