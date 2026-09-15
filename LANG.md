# Documentation Language Policy

This file defines how module documentation is authored and translated. Active
language choices live in [`LANG.local.md`](LANG.local.md).

Odoo UI translations and documentation translations are independent:

- UI labels and messages use module `i18n/*.po` and `*.pot` files.
- Human guides use Markdown mirrors under `doc/i18n/<lang>/`.

## Fields

- `source` is the canonical authoring language and fallback shown when a mirror
  is missing.
- `targets` lists the short language codes maintained as mirrors.
- `translate` lists the human-facing files mirrored for every target. An entry
  ending with `/` is a directory: every `*.md` inside it is mirrored file by
  file. An entry may be limited to some targets with an `@` suffix, as in
  `changes/@ru` or `changes/@ru+pl`; without a suffix it applies to all of them.
- `source-only` lists technical or historical documents that are never mirrored.

A mirror of `doc/<file>` lives at `doc/i18n/<lang>/<file>`. Its first line must
record the source SHA as described by the `odubook-i18n` skill. The runtime Book
uses the Odoo user's language and falls back to the source file per document.

Visible source documentation is always English. Code identifiers, paths, fenced
code blocks, inline code and `diff` blocks are not translated.
