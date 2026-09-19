# Documentation Book Administration

The Book is file-based. Module guides and the change archive store no
documentation in the database and are not translated at request time. The
database holds only the personal read marks of the change archive and the
documents put on the **Manuals** shelf by hand.

## Access control

The User Guide, Manuals and Changes sections are available to internal users.
The Admin Guide is restricted to the Settings group (`base.group_system`) both in
the menu and on the server endpoint. On the Manuals shelf internal users have
read access only; adding and removing documents requires the Settings group,
which is enforced by the ACL, not by hiding the buttons.

Read marks live in `odubook.change.read` (one row per user, module and date).
Internal users may read, create and update rows, never delete them, and a record
rule limits every operation to their own rows.

## Unread entries

An entry is one module on one date. It is marked as read as soon as its text is
served to the reader; **Mark all as read** marks everything currently on disk.

Two thresholds are constants in `models/odubook.py`:

| Constant | Default | Meaning |
|---|---|---|
| `NEW_ENTRY_DAYS` | 3 | how long an entry carries the green **New** label |
| `UNREAD_HORIZON_DAYS` | 90 | entries older than this are never counted as unread |

The horizon keeps a backfilled historical archive from turning every list into
bold text, and it applies to new employees as well without any data migration.
Removing read marks (for example to replay the archive for one user) is a plain
delete on `odubook.change.read`.

## The Manuals shelf

**Manuals** holds documents that do not live next to module code. One record of
`odubook.manual` is one document: `name` is the title in the sidebar and
`sequence` orders the shelf. Its files live in `odubook.manual.file`, one row
per language, each with its own `file_name`.

Add a document with **Add a document** below the shelf: pick the file, correct
the proposed title, choose the language and confirm. A dashed language button
above an open document uploads the missing translation; uploading the same
language again replaces that file instead of adding a second one.

With demo data enabled, the module ships one example document: **Sales Cube — sales management model**,
the interactive artifact behind `veles_sales_cube`, in English, Polish and
Russian. It is created once on install with `noupdate="1"`, so editing or
removing it in the UI survives the next upgrade; shipping a newer artifact means
uploading it on the shelf.

A reader gets the version of their own language, then the English one, then the
only version on the shelf — so a document uploaded in one language stays
readable for everybody. **Remove** takes off the open translation, and the last
remaining one takes the whole document with it.

The extension of the file — not the MIME type sent by the browser — decides how
a document is displayed:

| Extension | Shown as |
|---|---|
| `md`, `markdown` | rendered Markdown, like a guide |
| `txt`, `log`, `csv` | escaped plain text |
| `html`, `htm` | the document itself, inside a sandboxed frame |
| `pdf` | the browser PDF viewer |
| `png`, `jpg`, `jpeg`, `gif`, `svg`, `webp`, `bmp` | an image |
| anything else | a download link only |

An uploaded HTML document is served with `Content-Security-Policy: sandbox` and
displayed in an `iframe` without `allow-same-origin`, so its scripts run in
their own origin and cannot reach the reader's Odoo session. Even so, the shelf
is administrator-writable on purpose: treat an uploaded artifact as code you
vouch for.

A file may not exceed 25 MB, and only a text document below 4 MB is rendered
server-side; a larger or non-UTF-8 text file falls back to a download link.

## Adding documentation to a module

A module opts in by adding files below its `doc/` directory:

| File | Purpose |
|---|---|
| `user_guide.md` | Instructions for business users |
| `admin_guide.md` | Settings and privileged procedures |
| `tech_spec.md` | Technical contract; not displayed in the Book |
| `changes/YYYY-MM-DD.md` | One day of changes, authored in the source language |

Only installed modules are shown. A technical-name prefix is not required.

## Documentation languages

English is the source language. The configured target languages are Polish and
Russian. Human-guide mirrors live at
`doc/i18n/<lang>/user_guide.md` and `doc/i18n/<lang>/admin_guide.md`, and change
entries are mirrored one file at a time at
`doc/i18n/<lang>/changes/YYYY-MM-DD.md`.

Both guides and every change entry are maintained in all three languages:
English, Polish and Russian.

Each mirror starts with a SHA marker identifying the exact source revision from
which it was translated. Maintain translations through the `odubook-i18n` skill
and verify them with:

```bash
python3 .claude/skills/odubook-i18n/scripts/check_docs.py
```

The runtime selects the short code from the user's Odoo language (`pl_PL` →
`pl`) and falls back to the English source per missing document — per guide and
per change entry alike. Which dates exist in the archive is always decided by
the English sources, so a missing or extra mirror can never add or hide an
entry. `tech_spec.md` remains source-only.

The language buttons a reader sees above a guide or a change entry are not
configured anywhere: they are the mirrors found on disk. A language appears as
soon as one installed module carries `doc/i18n/<lang>/` with that document, and
disappears with the last such mirror; English is always offered. The buttons
may therefore differ per section if its configured mirrors differ, and a
language requested outside that list is ignored by the server. Adding a target
language to `LANG.local.md` and translating the configured documents is all it
takes for the button to appear; no configuration record is involved.

Reading in another language never writes anything: the choice lives in the open
view only.

## The Language entry in the user menu

**Language**, between **Shortcuts** and **My Profile** under the user's own
name, changes the language of the whole interface. It is the opposite of the
Book buttons: it writes `lang` on the reader's own `res.users` record and
reloads the page, because an assembled web client cannot swap its own
translations.

Every user may set that entry for themselves without any extra right: `lang` is
one of Odoo's self-writeable user fields, and the dialog writes nothing else and
nothing on anybody else. No group guards the entry, and there is nothing to
configure for it.

The dialog lists the **active** `res.lang` records, so a language appears there
only after it has been installed through **Settings → Translations → Languages**.
Installing a language does not translate custom modules by itself — a module is
translated for it only if it ships an `i18n/<lang>.po`. The Book's own language
buttons are independent of all this: they read Markdown mirrors from disk and
work for a language that is not installed in the database at all.

## Failure isolation

Unreadable, invalid UTF-8 or oversized documentation files are skipped and
logged without breaking the complete Book. Rendered HTML is cached per worker
and refreshed when a file's modification time changes.

## Odoo 16 compatibility

Use branch `16.0` for a fresh installation on Odoo 16. Install the module from `addons` together with its declared dependencies. This branch does not downgrade an existing Odoo database.
