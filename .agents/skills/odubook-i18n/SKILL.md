---
name: odubook-i18n
description: Manage and validate multilingual Markdown documentation for Oduflow client Odoo modules. Use when adding, translating, syncing, reviewing, or removing documentation languages; editing user_guide.md, admin_guide.md, translated change entries, LANG.md, LANG.local.md, doc/i18n mirrors, or documentation SHA markers; or checking translation structure and marker-only updates against a git base.
---

# Multilingual module documentation

Read `LANG.md` and `LANG.local.md` completely before changing documentation.
Operate on configured files below `addons/<module>/doc/`; module prefixes do not
matter.

## Authoring contract

- Edit the configured source-language file first.
- Mirror `translate` files at `addons/<module>/doc/i18n/<lang>/<file>`.
- Never mirror `source-only` files.
- Keep one source-language change entry per module and day.
- Preserve heading levels, list/table structure, fenced code, inline code, link
  targets, URLs, identifiers and section order. Translate prose and headings.

Every mirror starts with:

```html
<!-- i18n source=user_guide.md sha=<first 12 hex of source sha256> lang=<lang> -->
```

The checker owns SHA updates; do not edit them by hand.

## Sync workflow

Choose a git base before editing:

- use `HEAD` for uncommitted source and mirror changes;
- use the PR target such as `origin/19.0` when reviewing committed branch work;
- for an already-committed stale mirror, choose a revision from before the
  source changed.

Inspect stale state and the exact source delta:

```bash
python3 .agents/skills/odubook-i18n/scripts/check_docs.py \
  --against HEAD --show-diff
```

Translate every reported `missing`, `stale` or `unchanged` mirror. Delete only
reported `orphaned` mirrors. Then update safe markers:

```bash
python3 .agents/skills/odubook-i18n/scripts/check_docs.py \
  --against HEAD --fix-markers
```

`--fix-markers` updates only a valid stale marker whose mirror body changed and
whose structure passes. Use `--allow-unchanged` only after manually proving that
the source change needs no target-language change.

Finish with both checks:

```bash
python3 .agents/skills/odubook-i18n/scripts/check_docs.py
python3 .agents/skills/odubook-i18n/scripts/check_docs.py --against HEAD
```

Use `--lang <code>` to limit any command to one configured target.

## Checker guarantees

The default check validates configured targets, missing/orphaned mirrors and
marker correctness. With `--against`, it additionally blocks:

- a changed source whose mirror body did not change;
- changed documents whose heading levels, lists, tables, fenced code, inline
  code, links or URLs drift from the source.

Run `--strict-structure` only for an explicit full-repository legacy audit; it
may expose pre-existing debt outside the current change.

## Language operations

- **Add:** validate a lowercase language code, translate every applicable
  source, add it to `targets`, update the daily change entry and run the sync
  workflow.
- **Remove:** delete that language's mirrors, remove it from `targets`, update
  the daily change entry and check every remaining target.
- **Review:** compare against the PR base and treat every non-zero result as
  blocking.

Keep Odoo UI `.po`/`.pot` translations separate from Markdown mirrors.
