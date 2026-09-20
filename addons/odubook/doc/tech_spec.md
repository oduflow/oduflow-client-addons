# odubook — Module SPEC

## Identity & Manifest

- Technical name: `odubook`.
- Display name: `Odubook`.
- Version: `19.0.1.0.0` for Odoo 19.
- Category: `Tools`; author: `VelesAgro`; license: `LGPL-3`.
- Flags: `application = True`, `installable = True`.
- Dependencies: `base`, `web`; there is no dependency on `odu_base`.
- Data: `security/ir.model.access.csv`, `security/odubook_security.xml`,
  `views/odubook_views.xml`, `views/odubook_users_views.xml`,
  with optional demo content in `data/odubook_manual_data.xml`.
- Backend assets: the Book SCSS; Book, Admin Book, Audit, Manuals and Changes OWL 2
  client actions and templates in `web.assets_backend`; the user-menu language dialog
  (`static/src/user_menu/language.js` and `language.xml`).
- External Python dependencies: none; `markupsafe` is supplied by Odoo.

## Models & Fields

### `odubook`

- Type: `models.AbstractModel`; no database table or fields.
- `_description = "User Book"`.
- Reads installed module metadata and documentation files on demand.
- Constants define the `doc` directory, source filenames, translated-mirror
  directory, change-file pattern, administrator group, language-code pattern,
  1 MiB file-size limit, `SOURCE_LANG = "en"`, rendered-HTML cache,
  `NEW_ENTRY_DAYS = 3`,
  `UNREAD_HORIZON_DAYS = 90`, the change-file pathspec, `GIT_TIMEOUT = 20` and
  `GIT_HEAD_TTL = 60`, plus the commit-time, `HEAD`, repository-root and git
  `HOME` caches.

### `odubook.manual`

- Type: `models.Model`; one manually uploaded document of the **Manuals** shelf.
- `_description = "Manual"`; `_order = "sequence, name, id"`.
- Fields: `name` (`Char`, required), `sequence` (`Integer`, default 10),
  `file_ids` (`One2many` to `odubook.manual.file`), `active` (`Boolean`,
  default `True`).

### `odubook.manual.file`

- Type: `models.Model`; one language version of a document — the file itself.
- `_description = "Manual File"`; `_order = "lang, id"`.
- Fields: `manual_id` (required, indexed, `ondelete="cascade"`), `lang` (`Char`,
  required, indexed, short code), `file` (`Binary`, `attachment=True`,
  required), `file_name` (`Char`, required), `kind` and `format` (computed from
  `file_name` and stored, readonly).
- `kind` values: `markdown`, `text`, `html`, `pdf`, `image`, `download`;
  `format` is the upper-case extension shown beside the title.
- `models.Constraint`: `unique(manual_id, lang)` — one file per language.
- Constants define the extension→kind and extension→MIME maps, the kinds the
  server renders itself (`markdown`, `text`), `MAX_MANUAL_BYTES = 25 MiB`,
  `MAX_RENDERED_BYTES = 4 MiB`, the short-language pattern `^[a-z]{2,3}$` and
  `FALLBACK_LANG = "en"`.

### `odubook.change.read`

- Type: `models.Model`; personal read marks.
- `_description = "Read Change Entry"`.
- Fields: `user_id` (`res.users`, required, indexed, `ondelete="cascade"`,
  defaults to the current user), `module` (`Char`, required, indexed),
  `change_date` (`Date`, required).
- `models.Constraint`: `unique(user_id, module, change_date)`.
- One row means «this user has seen this entry»; rows are never updated.

### `res.users`

- `res.users.odubook_lang_id` is a computed/inverse, non-stored `Many2one` to
  `res.lang` that holds a reader's optional personal Book language.
- Values are persisted in `ir.config_parameter` under
  `odubook.user_language.<user_id>`. No new column on a core table is required
  when the registry starts with server code newer than the database schema.
- `SELF_READABLE_FIELDS` and `SELF_WRITEABLE_FIELDS` let the current user read
  and change the preference through the standard Preferences form.
- This is a new Odoo 19 addon; legacy Odoo 15 database migrations are not
  included. Existing documents, read marks and preferences require a separate
  database migration when upgrading an existing installation.

## Shipped Content

- With demo data enabled, `data/odubook_manual_data.xml` creates the shelf document **Sales Cube —
  sales management model** with three `odubook.manual.file` rows (`en`, `pl`,
  `ru`), each loaded from `data/manuals/cube-sales-model-<lang>.html` through
  `type="base64" file="..."`.
- The block is `noupdate="1"`: the document is created once, and later edits or
  its removal in the UI are not undone by an upgrade.

## Constraints & Invariants

- Documentation language codes joined into paths must match
  `^[a-z]{2,3}(@[a-z0-9]+)?$`; invalid values fall back to `en`.
- Change files contribute only when named `YYYY-MM-DD.md`. A change entry is the
  pair `(module, date)`, and the same pattern validates a date received from the
  client before it is joined into a path.
- A documentation file larger than 1 MiB is not rendered.
- A manual file larger than 25 MiB is refused by `_check_file_size`; a text file
  larger than 4 MiB, or one that is not valid UTF-8, is not rendered and the
  client falls back to the download link.
- The language of a version must match `^[a-z]{2,3}$`; `_check_lang` refuses
  anything else, so an unvalidated value never reaches the shelf.
- The version shown to a reader is the first match of: their own short language,
  `en`, the first version of the document. A document with no file at all is not
  listed on the shelf.
- The kind of a manual follows the file extension only; the MIME type sent by
  the browser is never trusted, because it depends on the uploader's OS.
- Raw Markdown is never inserted into the browser; all text is escaped and URL
  schemes are allowlisted by the Markdown renderer.

## Business Rules & State

- Every installed module is an eligible source, regardless of technical-name
  prefix. A module contributes only when the requested documentation file exists.
- User Guide reads `doc/user_guide.md`.
- Admin Guide reads `doc/admin_guide.md` and requires `base.group_system`.
- Changes reads source files under `doc/changes/`; the client groups the index
  by month (chronological feed), by date or by module.
- Each index entry carries `published`, a UTC datetime string: the commit time
  of the last commit that touched the source file in the history of the
  publication branch (`PROD_BRANCH`, `prod`). It is `False` when that history
  does not carry the file at all — an entry written in a branch that has not
  been merged yet.
- The publication history is `HEAD` when the working copy is on `prod` itself
  (the production deployment), otherwise the first of `refs/remotes/origin/prod`
  and `refs/heads/prod` that resolves, and `HEAD` when neither does.
- When the history cannot be read at all — outside a git working copy, without
  git, on a timeout — the file mtime is used instead (`False` when the file
  cannot be stat'ed). mtime alone is unreliable, git rewrites it on every
  checkout, so it is only the fallback and never mixes with git times.
- Commit times are read with one `git log --name-only` per repository, cached
  per repository until the tip of the publication branch changes; that tip is
  re-read at most every `GIT_HEAD_TTL` seconds. git runs with a private `HOME`
  whose `.gitconfig` lists the repository under `safe.directory`, because the
  working copy usually belongs to another user. A missing git, a foreign
  repository or a timeout degrades to mtime and never breaks the index.
- An entry is unread when the reader has no matching `odubook.change.read` row.
  It is displayed as unread only within `UNREAD_HORIZON_DAYS`, and carries the
  `New` label only within `NEW_ENTRY_DAYS`; both computed from the date in the
  filename, never from the file mtime.
- Requesting the text of an entry marks it read unless the caller passes
  `mark_read=False`, in which case the client marks the entries the reader has
  actually seen through `mark_entries_read`. Read marks are per user and are
  created only for entries that exist on disk in an installed module.
- Document language defaults to the context or user language (`pl_PL` → `pl`)
  and may be overridden per request by the reader, without touching their
  profile. Lookup is `doc/i18n/<lang>/<filename>` followed by `doc/<filename>`
  for guides, and `doc/i18n/<lang>/changes/<date>.md` followed by
  `doc/changes/<date>.md` for change entries.
- The offered languages are discovered on disk, per document: a language is
  offered when at least one installed module carries `doc/i18n/<lang>/<file>`
  (for the change archive, at least one `doc/i18n/<lang>/changes/<date>.md`).
  `SOURCE_LANG` is always offered first, and an empty mirror directory offers
  nothing. Codes are validated against `LANG_CODE_RE`, names come from
  `res.lang` including inactive records, and an unknown code falls back to the
  code in upper case.
- The repository language policy maintains user guides, administrator guides
  and every change entry in English, Polish and Russian. The runtime remains
  discovery-based and does not hard-code that configured set.
- A requested language outside that list is ignored: the reader's own language
  is used, and the source language when even that has no mirror. The list is
  therefore the whole surface through which a path segment can be chosen.
- The change index is always built from the English sources; a mirror can only
  replace the text of an entry, never add or hide one.
- A leading `<!-- i18n ... -->` provenance marker is removed before rendering.
- `tech_spec.md` is never exposed through the Book.
- Missing, unreadable, invalid UTF-8, oversized or failing documents are skipped
  individually; one file cannot break the complete response.
- Rendered HTML is cached by file path, marker-removal mode and mtime. No HTML is
  persisted in the database.
- Page and change-entry title is `ir.module.module.shortdesc`, falling back to
  the technical module name.
- Pages are ordered by module name. Change entries are ordered by `published`
  descending — what reached the reader last comes first — with the still
  unpublished entries above everything published, then by the date in the
  filename descending, then by module name. The days and months of the left-hand
  archive are calendar-ordered, newest first, independently of that order.

## Methods & Actions

### `odubook.manual`

- `get_manuals(self, lang=None)` (`@api.model`) returns `{"can_edit": bool,
  "languages": [{"code", "name"}, ...], "manuals": [{"id", "name", "langs",
  "lang", "file_name", "kind", "format", "url", "download_url"}, ...]}` in
  `_order`. `can_edit` is the caller's `create` right, `languages` are the
  installed `res.lang` short codes, and the index carries no document text.
- `read_manual(self, manual_id, lang=None)` (`@api.model`) returns `{"id",
  "lang", "kind", "html"}` for one document. `html` is rendered for `markdown`
  and `text` only and is `False` for every other kind, for an unreadable file
  and for a missing record.
- `upload_manual(self, name, file_name, data, lang=None, manual_id=None)`
  (`@api.model`) creates a document from base64 `data`, or adds/replaces one
  language version of `manual_id`, and returns `get_manuals()`. An empty title
  falls back to the file name without its extension; a missing file, name or
  language raises `UserError`. The `create` right is enforced by the ORM.
- `delete_manual(self, manual_id, lang=None)` (`@api.model`) unlinks one
  language version, or the whole document when `lang` is omitted or that version
  is the last one, and returns `get_manuals()`.
- `_version_for(self, lang=None)` resolves the version to show;
  `_reader_lang`, `_available_languages`, `_manual_data` build the client
  payload.
- On `odubook.manual.file`: `_kind_of`, `_format_of`, `_mimetype_of` derive
  kind, displayed format and MIME type from the file name; `_decoded_size`
  measures base64 payloads; `_content_url` builds the content URL;
  `_render_html` renders Markdown or escapes plain text into `<pre>`.

### `odubook`

- `get_book(self, lang=None)` (`@api.model`) returns
  `{"pages": [{"id", "module", "title", "html"}, ...], "languages":
  [{"code", "name"}, ...], "lang": "<code>"}` for user guides.
- `get_admin_book(self, lang=None)` (`@api.model`) returns the same shape for
  administrator guides and raises `AccessError` outside `base.group_system`.
- `_book_data(self, filename, lang)` resolves the offered languages and the
  selected one, and collects the pages of that language.
- `_doc_languages(self, filename)` scans `doc/i18n/` of every installed module
  and returns `[{"code", "name"}, ...]`, source language first. `CHANGES_DIRNAME`
  as `filename` asks for the change archive instead of a single file.
- `_has_mirror(self, lang_path, filename)` tells whether one mirror carries the
  requested document; for the archive, whether it carries at least one
  `YYYY-MM-DD.md`.
- `_language_names(self, codes)` decorates codes with `res.lang` names, reading
  inactive languages too.
- `_selected_lang(self, lang, languages)` picks the requested language when it
  is offered, then the reader's own, then `SOURCE_LANG`.
- `get_ui_languages(self)` (`@api.model`) returns `{"current": "<user lang>",
  "languages": [{"code", "name"}, ...]}` from the active `res.lang` records —
  the interface languages of the user menu, not the documentation ones.
- `get_changes(self, lang=None)` (`@api.model`) returns
  `{"entries": [{"module", "title", "date", "published", "unread", "is_new"},
  ...], "languages": [...], "lang": "<code>"}` ordered by `published`
  descending, unpublished entries first, then by date descending, then module
  name. It carries no HTML.
- `_published_at(self, filepath)` returns the publication time of the entry
  file, `False` when the publication history does not carry it, its mtime when
  that history cannot be read at all, and `False` when the file cannot be
  stat'ed either.
- `_repo_root(self, dirpath)`, `_commit_times(self, root)` (`None` when the
  history is unreadable, which is not the same as an empty history),
  `_publication_head(self, root)`, `_git(self, root, args, quiet=False)` and
  `_git_env(self, root)` implement the cached git lookup described above.
- `mark_entries_read(self, entries)` (`@api.model`) validates `[{"module",
  "date"}, ...]` exactly like `read_changes` and creates the read marks; it
  renders nothing.
- `read_changes(self, entries, mark_read=True, lang=None)` (`@api.model`) accepts
  `[{"module", "date"}, ...]`, returns
  `{"entries": {"<module>|<date>": {"heading", "html"}}}` and marks the rendered
  entries as read when `mark_read` is set. `heading` is the normalized title of
  the entry and `""` when its heading carried nothing but a date; `html` no
  longer contains that heading. Unknown modules, malformed dates and missing
  files are dropped silently.
- `change_pdf(self, entries, title=None, lang=None)` (`@api.model`) renders the
  same entries with `mark_read=False`, wraps them into one self-contained HTML
  document (`PDF_DOCUMENT` / `PDF_STYLE`, one `<section>` per entry headed by
  module and date) and returns `ir.actions.report._run_wkhtmltopdf` bytes,
  `None` when no requested entry survives validation. An entry heading equal to
  the cover `title` (`_same_heading`, case and spacing ignored) is not printed
  again inside the document.
- `guide_pdf(self, module, book=None, section=None, lang=None)` (`@api.model`)
  exports one guide of an installed module: `book="admin"` reads
  `admin_guide.md` and requires `ADMIN_GROUP` (`AccessError` otherwise), any
  other value reads `user_guide.md`. Without `section` the document title is the
  leading first-level heading (or the module title) and the body is everything
  below it; with `section` the anchor is resolved by `split_section` and only
  that heading with its subsections is exported. Returns
  `{"title", "pdf"}`, or `None` when the module, the document or the anchor is
  unknown.
- `guide_bundle_pdf(self, sections, book=None, lang=None, title=None)`
  (`@api.model`) exports several guide sections as one document. `sections` is
  `[{"module", "section"}, ...]` in the order chosen by the reader; an empty
  `section` takes the whole guide of that module. The book access rule is the
  one of `guide_pdf` (`_guide_filename`), every section is resolved by
  `_guide_part` in the language of `lang`, and repeated, unknown or missing
  sections are dropped silently. Each surviving section becomes one `<section>`
  headed by the module title (omitted when it repeats the section heading,
  `_same_heading`) and its own `<h1>`. Returns `{"title", "pdf"}` with `title`
  defaulting to `Selected sections`, or `None` when nothing survives.
- `_guide_filename(self, book)` maps `book` to `admin_guide.md` /
  `user_guide.md` and raises `AccessError` when a non-administrator asks for the
  Admin Book; `_guide_part(self, module, filename, lang, section=None)` returns
  `(title, html)` of a guide or of one anchor, `None` when the module, the
  document or the anchor is unknown. Both exports share them.
- `_pdf_report(self)` returns `ir.actions.report` with `sudo()` and raises
  `UserError` when `get_wkhtmltopdf_state()` is `install`; both exports use it.
- `mark_all_read(self)` (`@api.model`) marks every entry present on disk.
- `_read_marks(self, since=None)` returns the reader's `(module, date)` marks.
- `_mark_read(self, keys)` creates the missing marks inside a savepoint; a
  concurrent tab hitting the unique index is logged, not raised.
- `_list_module_changes(self, module_name)` returns `(date, filepath)` pairs
  from the English sources only, without reading or rendering Markdown.
- `_change_filepath(self, module_name, date_str, lang=None)` resolves one entry
  file, preferring the mirror of `lang` — the reader's own language when it is
  not given or not a valid code — over the source, or `None`.
- `_doc_lang(self)` returns the validated short documentation language.
- `_installed_modules(self)` returns installed `ir.module.module` records with
  `sudo()`, ordered by name.
- `_collect_pages(self, filename, lang)` collects rendered pages from all
  installed modules that contain the requested guide.
- `_module_doc_path(self, module_name, filename, lang)` resolves the document of
  a module, preferring `doc/i18n/<lang>/<filename>` over the source, or `None`;
  `_read_module_doc(self, module_name, filename, lang)` renders what it finds.
- `_doc_stat(self, filepath)` stats the file and refuses anything above
  `MAX_DOC_BYTES`; `_doc_source(self, filepath, strip_marker)` reads UTF-8 and
  optionally removes the i18n marker.
- `_render_doc_html(self, filepath, strip_marker)` enforces limits, reads UTF-8,
  optionally removes the i18n marker, renders, caches and isolates failures.
- `_render_change_entry(self, filepath)` returns `{"heading", "html"}` of one
  archive entry: it splits the leading level-1 heading off the Markdown with
  `split_title`, normalizes it with `strip_date_stamp` and renders the rest. The
  pair is cached in `_RENDER_CACHE` under `(filepath, "entry")` by mtime.
- `strip_date_stamp(title)` (module-level) removes a leading date from an entry
  title and returns `""` when the title was a date alone. `_is_date_stamp(text)`
  decides by words, not by format: a four-digit year is required and every other
  word must be a day, a month number, a month name of a book language
  (`MONTH_WORDS`) or a date tail such as `г.` / `r.` (`DATE_TAIL_WORDS`).
  `STAMP_SPLIT_RE` splits the date from the title on a spaced dash or colon, so
  the hyphens of `2026-08-28` are not mistaken for it.
- `_read_module_changes(self, module_name)` returns valid `(date, html)` pairs.
- `split_title(text)` (in `markdown.py`) returns `(title, rest)` for a leading
  level-1 heading and `("", text)` for anything else.
- `split_section(text, slug)` (in `markdown.py`) returns `(title, body)` of the
  heading whose anchor is `slug` together with every deeper heading below it,
  stopping at the next heading of the same or a higher level, and `(None, "")`
  when the anchor is unknown. Headings inside fenced code blocks are ignored;
  only a marker-only fence closes a block, while a language-tagged fence inside
  it remains code content.
- `slugify(text)` (in `markdown.py`) builds the heading anchor; `md_to_html`
  writes the same value into the `id` of every rendered heading.
- `md_to_html(text)` is a pure dependency-free renderer supporting headings,
  paragraphs, lists, fenced code, diff blocks, blockquotes, tables, horizontal
  rules, emphasis, inline code, links and images.

## Security

- `odubook` is an AbstractModel and has no ACL file or persisted records.
- `odubook.manual` and `odubook.manual.file` grant `base.group_user` read only
  and `base.group_system` full access; no business code uses `sudo()` on it. Uploading, deleting and
  `can_edit` all resolve through those ACLs, so hiding the buttons is a
  convenience, not the control.
- `/odubook/manual/<file_id>/<filename>` re-checks the record rule and answers
  `404` for a missing or unreadable document. It always serves the stored file
  name, so the name in the URL cannot change what is returned. Responses carry
  `X-Content-Type-Options: nosniff`; an `html` document adds
  `Content-Security-Policy: sandbox allow-scripts allow-popups allow-forms
  allow-modals`, and the client frames it without `allow-same-origin`, so an
  uploaded artifact runs in its own origin and cannot reach the session.
- `odubook.change.read` grants `base.group_user` read, write and create but not
  unlink, and rule `odubook_change_read_own_rule` restricts every operation to
  `[('user_id', '=', user.id)]`. No business code uses `sudo()` on it.
- All controllers require an authenticated user.
- Admin Guide access is enforced by both menu group and `get_admin_book()`.
- Module registry reads use `sudo()` without granting users registry access.
- HTML sanitisation escapes all source text. Links and images allow only
  `http`, `https`, `mailto`, scheme-relative and relative URLs; other explicit
  schemes become `#`.
- Client templates use `t-raw` only for the sanitised backend HTML.

## Views & UI

- Root menu `Book` contains `Changes` (sequence 1, so opening the application
  lands on it), `User Guide`, `Manuals` and administrator-only `Admin Guide` and `Audit`.
  Its application icon is loaded from
  `odubook/static/description/icon.png` through the menu's `web_icon` field.
- Five `ir.actions.client` records use tags `odubook.book`, `odubook.admin`,
  `odubook.manuals`, `odubook.changes` and `odubook.audit`.
- `BookApp` is an OWL 2 component with the RPC helper, loading state, title search,
  automatic first-page selection and a two-pane layout. Language buttons above
  the document re-request the whole book in that language and keep the open
  module; they are rendered only when more than one language is offered, carry
  the short code and the language name as `title`, and never touch the reader's
  profile.
- Every `h1`/`h2`/`h3` of a rendered guide carries a selection checkbox
  (`o_odubook_pick`), a PDF and a copy-link button (`o_odubook_tools`),
  appended to the heading after each render because the document arrives as
  ready HTML; clicks are handled by one delegated listener on
  `.o_odubook_doc`. PDF opens `/odubook/guide/pdf` in a new tab through
  `browser.open`; the link button writes
  `/odoo/action-<BookApp.action>?page=<module>&section=<anchor>&book_lang=…` into the
  clipboard and, when the clipboard is unavailable, shows the link in a sticky
  notification instead. `BookApp` reads those parameters from
  `props.action.params` on start (`_linkParams`): `lang` is passed to the first
  load, a known `page` is opened instead of the first module, and
  `_syncLinkScroll` scrolls to the anchor once after the first render.
- `state.selection` is the reader's PDF set: `[{module, section}, ...]` in the
  order the checkboxes were ticked, kept across page and language switches and
  persisted in `browser.localStorage` under `odubook.selection.<book>`, so the
  user and the admin book keep separate sets and a reload keeps them. A missing,
  malformed or non-array value restores an empty set, and a storage that refuses
  to write (private mode, quota) only costs the persistence. `_syncSelection` re-ticks the boxes after every render and
  marks their `o_odubook_tools` with `o_picked` so a ticked heading keeps its
  tools visible. While the set is not empty the document header shows the
  export button with the count and a clear button; export opens
  `/odubook/guide/pdf/bundle` in a new tab with the current `book` and `lang`.
  Anchors are language-specific, so sections ticked in another language are
  dropped by the server.
- `AdminBookApp` reuses `BookApp` with endpoint `/odubook/admin`, action tag
  `odubook.admin` and `book = "admin"`.
- `ManualsApp` is an OWL 2 component with the same two-pane shell: the shelf and
  a title/file-name search on the left, the document on the right. Language
  buttons above the document switch the version and re-request the whole index,
  because the language changes both the content URL and the format of every
  card; a dashed button marks a language without a version and, for an
  administrator, starts its upload. Text kinds are fetched lazily per document
  and language and cached in `state.html` under `"<id>|<lang>"`; `html` and `pdf` are
  framed by URL, `image` is an `<img>`, every other kind offers the download
  link only. With `can_edit` it also renders the upload block: a hidden file
  input, an editable title proposed from the file name, a language selector
  defaulting to the uploader's own language, `Add to shelf` / `Cancel`, and
  `Remove` guarded by a `ConfirmationDialog` that names the translation when the
  document has more than one. A file above the
  25 MB limit is refused client-side with a notification before it is read.
- An entry is titled by `heading` from the server; when it is empty the date
  views fall back to the module title and `By module` renders no title at all.
  Beside that title — and beside the group title in the header — sit a PDF and a
  copy-link button (`o_odu_changes_tools`), dimmed until the title is hovered or
  a button takes focus. PDF opens `/odubook/changes/pdf` in a new tab through
  `browser.open`; the link button writes
  `/odoo/action-odubook.changes?group_by=…&group=…&entry=…&book_lang=…` into the
  clipboard and, when the clipboard is unavailable, shows the link in a sticky
  notification instead.
- The head of every entry carries a selection checkbox (`o_odubook_pick`
  `o_odu_changes_pick`) — the head, not the title, because an entry without a
  `heading` renders no title at all. `state.selection` is the reader's PDF set:
  the `<module>|<date>` keys in the order they were ticked, persisted in
  `browser.localStorage` under `odubook.changes.selection`. A missing,
  malformed or non-array value restores an empty set, entries that are no longer
  in the archive are dropped from it silently, and a storage that refuses to
  write (private mode, quota) only costs the persistence. The set is independent
  of the group, the view and the language, and separate from the guide set of
  `BookApp`. While it is not empty the group header shows the export button with
  the count and a clear button; export posts the selected keys to
  `/odubook/changes/pdf` exactly like a group export, titled `Selected changes`.
  Ticking does not mark an entry read.
- `ChangesApp` reads those same URL parameters from `props.action.params` on
  start (`_linkParams`, `_startGroupKey`): a known `group_by` selects the view,
  a known group or the group of the linked entry is opened instead of the first
  one, `lang` is passed to `/odubook/changes`, and `_syncLinkScroll` scrolls to
  the linked entry once after the first render. Unknown values fall back to the
  default view and the first group.
- `ChangesApp` carries the same language buttons in the header beside the group
  title. Switching drops the rendered text cached in `state.html` and reloads
  the open group only; the index itself is language-independent, so unread
  marks, badges and the chart are untouched.
- `LanguageDialog` is added to the `user_menuitems` registry as `Language`
  (sequence 35). It lists the active `res.lang` records, marks the current one,
  writes `res.users.lang` for the reader through the ORM service — `lang` is a
  self-writeable field — and reloads the page, because the assembled web client
  cannot swap its own translations. It changes the whole interface, unlike the
  per-document buttons in the Book.
- `ChangesApp` is an OWL 2 component with a `By date` / `By module` /
  `By module & date` switch, a `Mark all as read` button, lazy per-group text loading
  and labels formatted through locale-configured Luxon. It selects the first
  group automatically.
- A group is a month in `By date` (the entries of the month are listed on the
  right in index order — `published` descending — each headed by its module and
  by the day of the entry), a day in `By module & date` and a module in
  `By module`. Every entry head, in every mode, carries `Published <date,
  time>` in the reader's time zone, or `Not published yet`. The internal `groupBy` values
  are `date`, `module_date` and `module`.
- A day or a module group is marked read as a whole when its text is loaded. The
  month feed loads with `mark_read=False` and an `IntersectionObserver` reports
  the entries the reader actually scrolled to; only those are marked read and
  lose their highlight when the reader leaves the group.
- `By date` renders a month histogram above the feed (`monthChart` getter, inline
  SVG, no charting library) while `state.showChart` is on. That state starts as
  `false`, so the chart is hidden until the reader asks for it. The `Chart`
  toggle sits in the sidebar header next to `Change archive`, is rendered in the
  feed view only and flips that state. The histogram draws one bar per month, oldest left,
  height proportional to the month's entry count, the unread share drawn on top
  in the accent color and the read share below it. Bars are click targets that
  call `selectGroup`; the active bar is highlighted, the value label is shown for
  the active and the tallest bar and on hover, and an SVG `<title>` carries
  month, count and unread count. The chart is skipped for fewer than two months,
  scrolls horizontally and opens on its right edge (newest months).
- A sidebar group carries two badges: the unread count with `o_unread`, rendered
  only while the group has unread entries, and the total count of the group to
  its right. Both carry a translated `title`.
- Unread groups and entry headers get `o_odu_changes_unread` (bold), fresh
  entries a green `o_odu_changes_new` label. The highlight of the open group is
  cleared only when the reader moves on, so it never vanishes mid-read.
- Empty, loading and no-selection states are displayed explicitly.

## API Endpoints

- `POST /odubook/book`: `type="jsonrpc"`, `auth="user"`; takes an optional `lang`
  and returns `get_book(lang)`.
- `POST /odubook/admin`: `type="jsonrpc"`, `auth="user"`; takes an optional `lang`
  and returns `get_admin_book(lang)`, and therefore enforces the administrator
  group.
- `POST /odubook/languages`: `type="jsonrpc"`, `auth="user"`; returns
  `get_ui_languages()` for the user-menu dialog.
- `POST /odubook/manuals`: `type="jsonrpc"`, `auth="user"`; takes an optional
  `lang` and returns `get_manuals()`.
- `POST /odubook/manuals/read`: `type="jsonrpc"`, `auth="user"`; takes `manual_id`
  and an optional `lang`, and returns `read_manual()`.
- `POST /odubook/manuals/upload`: `type="jsonrpc"`, `auth="user"`; takes `name`,
  `file_name`, base64 `data`, `lang` and an optional `manual_id`, and returns
  the refreshed shelf. The ACL limits it to the Settings group.
- `POST /odubook/manuals/delete`: `type="jsonrpc"`, `auth="user"`; takes
  `manual_id` and an optional `lang`, and returns the refreshed shelf; ACL as
  above.
- `GET /odubook/manual/<int:file_id>/<string:filename>`: `type="http"`,
  `auth="user"`; serves the bytes of one language version inline, or as an
  attachment with `?download=1`, and answers `404` when the record is missing or
  unreadable.
- `POST /odubook/changes`: `type="jsonrpc"`, `auth="user"`; takes an optional
  `lang` and returns `get_changes(lang)`.
- `POST /odubook/change`: `type="jsonrpc"`, `auth="user"`; takes `entries`,
  `mark_read` (default `True`) and an optional `lang`, and returns
  `read_changes(entries, mark_read, lang)`.
- `POST /odubook/changes/read`: `type="jsonrpc"`, `auth="user"`; takes `entries`
  and returns `mark_entries_read(entries)`.
- `GET /odubook/changes/pdf`: `type="http"`, `auth="user"`; takes `entries`
  (`"<module>|<date>,<module>|<date>"`), an optional `title` and an optional
  `lang`, and answers with `change_pdf(...)` as an attachment named after the
  title (`_pdf_filename`, non-word characters dropped, 80 characters, defaulting
  to `changes.pdf`). Unparsable or unknown entries answer 404.
- `GET /odubook/guide/pdf`: `type="http"`, `auth="user"`; takes `module`, an
  optional `book` (`user` / `admin` / `audit`), an optional `section` anchor and an
  optional `lang`, and answers with `guide_pdf(...)` as an attachment named
  after the exported title (`_pdf_filename`). A missing module, document or
  anchor answers 404.
- `GET /odubook/guide/pdf/bundle`: `type="http"`, `auth="user"`; takes
  `sections` (`"<module>|<anchor>,<module>|<anchor>"`, an empty anchor meaning
  the whole guide), an optional `book`, an optional `title` and an optional
  `lang`, and answers with `guide_bundle_pdf(...)` as an attachment named after
  the cover title (`_pdf_filename`). An empty list and a selection where nothing
  resolves answer 404.
- `POST /odubook/changes/read_all`: `type="jsonrpc"`, `auth="user"`; returns
  `mark_all_read()`.

## Automation

- No crons, automated actions or background jobs.

## Seed / Demo Data

- Client actions, menus and security records only. Documentation files are module
  resources read from disk; they are not database seed data. Read marks are
  created by readers at runtime, never seeded.

## Module audit shelf

- Source: `doc/module-audit.md` of installed modules only; modules without
  readable reports are omitted. Reports are source-only English, including PDF
  export; `doc/i18n/` mirrors are ignored. Existing rendering sanitisation,
  file-size limits and mtime cache apply.
- `get_audit_book(lang=None)` returns the existing book payload with `lang=en`
  and English as the only available language. It requires `base.group_system`
  before collecting or reading reports.
- `POST /odubook/audit` uses authenticated JSON-RPC and delegates to
  `get_audit_book`. Both guide PDF endpoints accept `book=audit`;
  `_guide_filename` enforces the same administrator check before file access.
- Client action `odubook.audit` uses `AuditBookApp`, inheriting `BookApp`,
  with endpoint `/odubook/audit` and book key `audit`. Search, section links,
  PDF selection and exports reuse the existing viewer. Local storage key
  `odubook.selection.audit` isolates its selection.
- Menu `menu_odubook_audit`, action `action_odubook_audit`, label `Audit`,
  sequence 8 under the Book root, is restricted to `base.group_system`.
- `.agents/skills/audit-modules/SKILL.md` defines the repository audit workflow.
  Its scope includes all modules in `addons/`, even uninstalled ones; it writes
  reports without automatically applying fixes. Viewing reports runs no audit.
