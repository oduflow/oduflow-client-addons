# Agent Instructions

This is the canonical agent instruction file for this repository.
`CLAUDE.md` includes it; add shared rules here.

## Project

Oduflow client addons for Odoo 19. Modules live under `addons/` at the repository root.
`odubook` is the Odoo 19 port of VelesAgro's `odu_book` and displays documentation
from installed modules.

## UI testing

- Use the `agent-browser` skill for UI testing.
- Always run `agent-browser close` after testing, including failed or interrupted
  test runs.

## Living module documentation

Update code and the documentation of its user-visible behavior together in the
same change. Add files under `addons/<module>/doc/` to include a module in the shared
Book; the module's technical prefix does not matter.

- `doc/user_guide.md`: instructions for regular users.
- `doc/admin_guide.md`: configuration and privileged operations, when applicable.
- `doc/tech_spec.md`: the precise technical contract for developers and agents.
- `doc/changes/YYYY-MM-DD.md`: a user-visible daily change entry; use one file
  per module per day.
- `doc/i18n/<lang>/{user_guide.md,admin_guide.md,changes/*.md}`: translated mirrors.

Write source documentation in English. Read [LANG.md](LANG.md) and
[LANG.local.md](LANG.local.md) for the language policy and active targets.
After changing source documentation, synchronize every configured target using
[odubook-i18n](.agents/skills/odubook-i18n/SKILL.md), then run:

```sh
python3 .agents/skills/odubook-i18n/scripts/check_docs.py
python3 .agents/skills/odubook-i18n/scripts/check_docs.py --against HEAD
```

For committed changes, replace `HEAD` with the relevant PR base or a revision
from before the source changed. The Claude-compatible entry point is
`.claude/skills/odubook-i18n/scripts/check_docs.py`.

A task that changes user-visible behavior is complete only when the applicable
user/admin guides, technical specification, daily change entry and all language
mirrors are current. Always create or update the Polish change mirror at
`doc/i18n/pl/changes/YYYY-MM-DD.md` together with its source; the Russian mirror
is also required by the active language configuration.

Keep `tech_spec.md` source-only. Translate Odoo UI strings separately through
standard module `i18n/*.po` and `*.pot` files.

Perform final translation synchronization, SHA marker updates and documentation
checks after targeted tests pass and behavior is stable. For documentation-only
changes, do not rerun application tests if Python, XML and data files have not
changed.

The documentation policy and translation skill were adapted from
`oduist/velesagro` for this repository's module layout and `odubook` name.

## Oduflow deployment journal

For every Oduflow service installation, reconfiguration, upgrade, credential
rotation, recovery or removal performed for this repository, create or update
`deploy/log/YYYY-MM-DD-<environment>-<service-or-stack>.md` using the UTC operation
date. Use one entry per environment/service scope per day and append separate
timestamped operations. Start from [the template](deploy/log/TEMPLATE.md) and add
the entry to [the journal index](deploy/log/README.md).

Record the work as it happens, including failed or partial attempts, and finish
the entry before reporting completion. Documentation-only imports must state
their source, import date and historical operation date; never present imported
results as checks performed now. Mark unknown values as unknown, not guessed.

Record enough detail to reproduce and operate the installation:

- Purpose, UTC times, operator/tool, Oduflow instance/team, environment, database,
  service IDs/names, dependencies and initial state.
- Repository URL, branch and deployed commit; image tags and digests when available.
- Hostnames, URLs, internal container/network names, ports, public routes, VPN
  ranges, DNS, ACL policy, volume names/mounts, ownership and persistence.
- Exact tool names and arguments or commands in execution order, configuration
  paths and sanitized contents/diffs (or links pinned to the applied revision),
  non-secret environment variables and prerequisite steps.
- Secret variable names and storage references, issuance/expiry dates and rotation
  steps; NEVER record tokens, passwords, private keys, enrollment commands with
  key secrets, session cookies or unredacted tool responses. Replace values with
  `<redacted>` before writing files; record how to provision replacements.
- Operation/job/output IDs, exit statuses, failures and fixes; distinguish planned,
  executed and unverified steps. Include backup location/reference and rollback
  procedure/result, or explicitly say no backup/rollback was performed.
- Actual health, API, module-test and end-to-end checks with expected/observed
  results; final state, remaining limitations, cleanup, owners and follow-up work.

Keep historical observations intact; append corrections and later operations.
Put reusable installation/operation instructions in the module's `doc/admin_guide.md`
and technical contracts in `doc/tech_spec.md`. Keep `deploy/README.md` as the
service/configuration overview, and link it to the journal. Write journal entries
in English; they are operational records, outside the module translation mirrors.
