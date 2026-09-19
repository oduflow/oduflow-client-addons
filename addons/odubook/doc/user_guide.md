# Documentation Book

The **Odubook** application brings the documentation of installed Odoo modules
together in one place. It reads documentation stored next to each module's code,
so the instructions follow the deployed version of the feature.

## Available sections

- **User Guide** contains day-to-day instructions for business users.
- **Manuals** is a shelf of documents added by hand: files that do not live
  next to module code — design artifacts, contracts, scanned instructions.
- **Admin Guide** contains settings and privileged procedures. It is visible
  only to Settings administrators.
- **Changes** shows the history of documentation updates, as a chronological
  feed, by module and date, or by module.

## Reading documentation

Open **Odubook → User Guide** and select a module on the left. Use the search field
to filter modules by title. The selected guide appears on the right and may
contain headings, lists, tables, links, images and code examples.

The Book shows a guide in the **Odubook Language** selected in your Odoo
**Preferences**. Leave that preference empty to follow the interface language.
If a translation is unavailable, the Book falls back to the English source for
that guide.

## Taking a guide with you

A checkbox and two buttons sit beside every heading of a guide, its title
included, and appear when you point at it. They work in the **User Guide** and in the **Admin
Guide** alike:

- the PDF button downloads what stands under that heading — the whole guide
  when you press it beside the title, or a single section with all of its
  subsections. The document is downloaded in the language you are reading.
  Fenced code examples remain complete even when they demonstrate another
  language-tagged Markdown fence.
- the checkbox puts that heading into a set, so that several chapters leave the
  Book as one PDF. It is described in the next section.
- the link button copies a link to that heading into your clipboard. Opening
  the link elsewhere reopens the Book on the same guide, in the same language,
  scrolled to the same heading. Where the browser refuses access to the
  clipboard — over plain HTTP it always does — the link is shown to you
  instead, to be copied by hand.

## Collecting several chapters into one PDF

The PDF button exports one heading at a time. When you need a booklet of
several chapters — from one guide or from different ones — tick the checkbox
beside every heading you want. A ticked heading keeps its checkbox in sight, so
you always see what the set already holds.

The set survives moving around the Book: tick a few sections in one module,
open another module and tick more there. While the set is not empty, two
buttons stand above the document:

- **Export selected sections** downloads the whole set as one PDF, in the order
  you ticked it. Every chapter keeps its own heading, preceded by the name of
  the module it came from.
- **Clear the selection** empties the set.

The set is remembered by your browser: reload the page, come back to the Book
tomorrow, and it is still there, waiting to be exported or cleared. The
**User Guide** and the **Admin Guide** keep their sets apart. Headings are
named differently in different languages, so choose the language before you
start collecting — a section ticked in another language does not reach the
document.

## Reading in another language

Above the text, in every section of the Book, sit the language buttons — for
example **EN**, **PL** and **RU**. They offer only the languages the
documentation is actually written in, so a button never opens an empty page.
The button of the language you are reading is highlighted; click another one and
the same section reappears in that language.

The choice applies to what you are reading and to nothing else: your Odoo
profile, your menus and your other windows stay in your own language. It is not
remembered either — open the Book again and it is back to your language. Use it
to check a colleague's wording, or to read the English original when a
translation looks unclear.

To change the language of everything else, not only of the page you are
reading, see the next section.

## Changing the language of Odoo

Click your name in the top right corner and choose **Language**. A small window
lists the languages installed in your database and marks the one you are
working in. Pick another one and the page reloads translated: menus, buttons,
field labels, messages, reports and the Book along with them.

This is your own setting and nobody else's — your colleagues keep their
languages, and the documents you create keep the language of the person they
are addressed to. It is the same setting as **Language** in **Preferences**
under the same menu; the entry here only saves you the trip through the
preferences form.

Two things worth knowing before you switch:

- The page reloads, so finish or save what you are editing first.
- The list holds the languages an administrator has installed. If the one you
  need is missing, ask an administrator to add it; the language buttons inside
  the Book work regardless and need no installed language at all.

## Reading the manuals

Open **Odubook → Manuals**. The shelf lists documents uploaded by an administrator, with their file formats. Search by title or file name and select a document to read it. With demo data enabled, the shelf also includes the multilingual **Sales Cube — sales management model** example:

- Markdown and plain-text documents are formatted and shown like a guide.
- HTML documents — an interactive artifact, for example — run inside the page.
- PDF files and images are displayed as they are.
- Any other format (a spreadsheet, an archive) is offered for download.

A document may exist in several languages. You always open the version of the
language set in your Odoo profile; when that translation is missing, the English
one is shown, or the only version there is. The language buttons above the
document — **EN**, **PL**, **RU** — switch it by hand, exactly like in the
guides; here they list the languages the document itself was uploaded in.

**Download** above the document always saves the file of the version you are
reading. Administrators also see **Add a document** below the shelf, **Remove**
beside **Download**, and a dashed language button for every translation that is
still missing: clicking it uploads that translation. Ordinary users read the
shelf without changing it.

## Reading the change archive

Open **Odubook → Changes** — it is the first menu of the Book, so opening the
application lands here. One entry is one module on one date. The switch above
the list on the left offers three views:

- **By date** is a chronological feed. Select a month on the left and read every
  change of that month on the right, the most recently published entry on top.
  Each entry is headed by the module it applies to and by its day. The **Chart**
  button beside **Change archive** is off when you open the view; switch it on
  and a chart appears above the feed showing how busy every month was: one bar
  per month, oldest on the left, its height the number of changes. The unread
  part of a month is drawn on top of the bar in a stronger color, so a glance
  tells you both how much happened and how much of it is still waiting for you.
  Click a bar to open that month; point at one to see its exact figures. Switch
  the button off again and the chart disappears; it is offered in this view
  only.
- **By module** lists modules. Select one to read its complete history.
- **By module & date** lists days, newest first and grouped by month. Select a
  day to read the entries of every module changed on it.

Every entry says when it was published — the moment the change reached this
server, not the moment somebody wrote it — and the archive is ordered by that
moment, the freshest on top. The date of an entry is the day its author filed
it, and it can be older than the publication: a change written on Friday and
published on Monday stands among Monday's news. An entry that is written but
not published yet says **Not published yet** and stands above everything
published; on this server you see one only while a change is being prepared.

Every entry is titled by what changed, never by its date: the day is already
shown beside it, so a date at the front of the title is dropped. An entry whose
author gave it no title of its own is titled by its module in the two date
views, and carries no title at all in **By module**, where the module name
already stands above the whole group.

Two buttons sit beside every title, the title of the open month, day or module
included, and appear when you point at it:

- the PDF button downloads what stands under that title — the single entry, or
  every entry of the open group. Downloading an entry does not mark it read.
- the link button copies a link to that title into your clipboard. Opening the
  link elsewhere reopens the archive in the same view, on the same group and
  scrolled to the same entry, in the language you were reading. Where the
  browser refuses access to the clipboard — over plain HTTP it always does —
  the link is shown to you instead, to be copied by hand.

In every view, added lines are highlighted in green and removed lines in red.
The language buttons beside the title of the open month, day or module work
exactly as in the guides, and the archive itself — which entries exist and which
of them you have read — does not depend on the language you read them in.

## Collecting several changes into one PDF

The PDF button of an entry exports that entry alone. When you need several of
them in one document — a month of one module, or everything that changed across
modules before a release — tick the checkbox at the head of every entry you
want.

The set survives moving around the archive: tick a few entries in the feed,
switch to **By module** and tick more there. An entry is remembered by its
module and its date, so changing the view or the reading language leaves the set
untouched. While it is not empty, two buttons stand beside the title of the open
group:

- **Export selected entries** downloads the whole set as one PDF, in the order
  you ticked it.
- **Clear the selection** empties the set.

Your browser remembers the set, so reloading the page no longer empties it. The
set of the archive and the set of the guides are kept apart. Ticking an entry
does not mark it read.

## Unread entries and the New label

Entries you have not read yet are shown in bold. A month, a day or a module
carries two badges: the filled one on the left counts the entries you have not
read yet and appears only while some are left, and the pale one on the right
counts every entry of that group. An entry published within the last three days also
carries a green **New** label.

Both marks are personal: your colleagues keep their own unread list. An entry
counts as read once you have actually seen it: a day or a module is read as a
whole, while in the month feed only the entries you scrolled to are marked. The
highlight stays until you move to another month, day or module, so it never
disappears while you are still reading. **Mark all as read** clears everything
at once.

Entries older than three months are never counted as unread, so the historical
archive stays readable instead of turning into a wall of bold text.

Every entry is available in English, Polish and Russian. Entries follow the
language of your Odoo profile, exactly like the guides do, and can be switched
by hand with the language buttons above them.

The User Guide answers “what is true now”. The Changes archive answers “what
changed and when”.

## Module audits

Administrators can open **Book → Audit** to read module audit reports. This
section is hidden from regular users. Reports describe the reviewed revision,
findings and validation limits; opening the section does not run an audit.
