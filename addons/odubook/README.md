# Odubook for Odoo 19

A port of `odu_book` from [oduist/velesagro](https://github.com/oduist/velesagro),
directory `addons_veles/odu_book`, source commit
`a402851711591196977380c5a2a143dc8fec0ee3` (version `15.0.1.17.0`).

## Features

- User and administrator guides from the `doc/` directories of installed modules.
- Change history, grouping, chart and personal read markers.
- Document shelf: Markdown, text, HTML, PDF, images and file downloads.
- Russian and Polish translations, a separate book language and Odoo language selection.
- PDF export of guides, sections and selected changes; links to sections.

## Installation

Add this repository's `addons/` directory to `addons_path` and install `odubook`:

```sh
odoo -d DATABASE -i odubook --stop-after-init
```

Dependencies: `base`, `web`. PDF export requires a working `wkhtmltopdf`, as do
standard Odoo reports. Publication timestamps from repository history require
`git`; otherwise, file modification times are used. The “Sales Cube” example
is loaded only when demo data is enabled.

## Adding Documentation

| File within a module | Section |
| --- | --- |
| `doc/user_guide.md` | User guide |
| `doc/admin_guide.md` | Administrator guide |
| `doc/changes/YYYY-MM-DD.md` | Change history |
| `doc/i18n/ru/…`, `doc/i18n/pl/…` | Translations of the same files |

English text is used when a translation is missing. The Book is available to
internal users. The administrator guide and shelf editing require Settings
administrator permissions.

## Porting Changes

Client actions use Owl 2: imports, DOM references, event handlers, safe HTML
rendering and dialogs. Templates are included in `web.assets_backend`.
Routes use `jsonrpc`, links use `/odoo/action-…`, database constraints use
`models.Constraint`, and access checks use `check_access` / `has_access`.

The technical name, models, XML IDs, routes, parameters and browser keys use
`odubook`. This is a new module installation for Odoo 19. Moving records from an
existing Odoo 15 database (documents, attachments, read markers and settings)
requires a separate database migration; legacy `15.0.*` migrations are not
included in the port.

## Validation

```sh
odoo -d TEST_DATABASE -i odubook --without-demo \
  --test-enable --test-tags /odubook --stop-after-init
```

Tests cover Markdown, languages, documentation assembly, Git history, personal
read markers, document uploads and deletion, JSON-RPC, permissions, file serving
and actual PDF export. Install `git` and `wkhtmltopdf` for the full suite.

Validated on Odoo `19.0-20260908`: 64 tests passed both on upgrade and on a clean
installation with demo data and `ru_RU`, `pl_PL` translations. Browser checks
covered all four sections, language switching, document upload and deletion,
user settings and a direct link that scrolls to a section.

License: LGPL-3. Original author: VelesAgro; port: Oduflow.
