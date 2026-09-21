# OduMCP Administrator Guide

## Security Roles

- **MCP Auditor** can inspect profiles, approvals, and audit records.
- **MCP Manager** can configure profiles, enable users, and decide approvals.

Do not use an administrator account as an MCP user. Odoo access rights, record
rules, allowed companies, and the MCP profile are all enforced together: the
profile can only narrow what the assigned Odoo user is already allowed to do.

## Enable MCP for a User

1. Open **Settings > Users & Companies > Users** and select the user.
2. Open the existing **Account Security** tab.
3. Enable **MCP Active**.
4. Select a **Profile**.
5. Save the user.

Saving these fields does not create a permanent API key. OduPilot checks the
user, flag, and profile when each conversation starts and issues its own
signed session token, which is revoked when the conversation closes. A person
who connects an external MCP client creates a personal key under **Preferences
> Account Security**, where the secret is displayed once. Such a key works on
the MCP endpoints and nowhere else, and a regular **All APIs** key is rejected
by them.

There is no separate User Access record or menu. Each user stores exactly one
MCP flag and one profile directly. Usage counters are not stored on the user;
rate and daily quotas are calculated from immutable audit records.

**MCP Active** and **Profile** are deliberately two fields. The profile states
what a user may do; the flag states whether that user may do anything at all.
The flag is off by default, so a profile alone opens nothing — a profile that
arrives from a user template or a copied user never grants access on its own.
The opposite combination is refused: enabling the flag without a profile raises
**Select an MCP profile before enabling MCP access**.

## Configure a Security Profile

Open **MCP > Security Profiles**. A profile is default-deny: without an
explicit Model Policy and without a broader default access, nothing is exposed.

Installing the module seeds two profiles. **Administrator** (code `admin`)
reads, updates and creates on any model its connector user may already use,
through the default model access rather than through Model Policies. Deletion,
reports, auto-approval and partial field reads stay off. **Read Only** (code
`readonly`) only reads and aggregates. Neither is assigned to anyone: a profile
alone opens nothing until a user gets **MCP Active** and that profile. Upgrades
never overwrite them, so tightening one is safe; copy it instead when a client
needs a different scope.

### Profile and Limits

- **Allowed Companies** intersects the connector user's companies. An empty
  list means every company the user already has. No intersection at all is an
  error, not silent full access.
- **Max Records Per Call** caps search, read, aggregate and report results.
- **Max Batch Size** caps how many records one create/update/delete plan may
  touch.
- **Rate Limit Per Minute** and **Daily Quota** are counted from audit rows.
  A daily quota of zero disables the daily check; the day boundary is UTC.
- **Approval TTL Minutes** is how long a change plan stays executable.

### Default Model Access

This is the fallback used only for models that have no explicit Model Policy.

- **Explicit policies only** — the recommended default. Nothing outside the
  Model Policies tab is reachable.
- **Read any accessible model** — read and, if **Aggregate** is on, aggregate
  every non-transient model the Odoo user may read.
- **Read and update any accessible model** — additionally allows updates.

**Create on Any Accessible Model** and **Delete from Any Accessible Model** add
those two operations to the same fallback. All of them still require the
matching Odoo access right on the connector user, and every change still goes
through an approval.

Under the fallback, fields whose names look like secrets (`password`, `pass`,
`token`, `api_key`, `secret`, `private`, `credential`, `authorization`) and all
binary fields are hidden, and write is additionally limited to non-readonly,
non-technical fields.

System parameters (`ir.config_parameter`) follow normal model policies and
profile-wide access, subject to the connector user's Odoo permissions. For
restricted read access, add an explicit Model Policy with only Read enabled,
select `key` and `value` as readable fields, and set a forced domain such as
`[["key", "=like", "oduflow.%"]]`. This matches keys beginning with
`oduflow.`; use `oduflow%` to include every key beginning with `oduflow`.
Parameter values can contain credentials; field-name filtering does not identify
secrets stored in the generic `value` field.

The fallback never covers:

- transient (wizard) models;
- `res.users.apikeys` and the OduMCP models
  themselves — these can never be exposed, not even by an explicit policy.

On the security models the fallback is read-only, whatever the mode:

- `base.automation`, `ir.actions.server`, `ir.cron`, `ir.mail_server`,
  `ir.model.access`, `ir.rule`, `ir.ui.view`, `res.groups` — reading them only
  reports the rules the connector already works under, while writing them would
  bypass this policy layer; an explicit Model Policy can still open them for
  writing deliberately;
- `res.users` — readable, but never creatable, writable, or deletable, because
  that changes group membership.

Reading them still requires the matching Odoo access right on the connector
user: `ir.model.access` and `ir.rule` are limited to Access Rights managers,
and `ir.ui.view`, `ir.cron`, `ir.mail_server`, `base.automation` and
`ir.actions.server` to Settings users.

### Capabilities

Each capability switches one specific operation on or off. They add nothing on
their own — the model and field policies still apply on top.

| Capability | What it actually allows |
| --- | --- |
| **Schema** | Describing a model's fields. Listing the allowed models is always available. |
| **Aggregate** | Grouped aggregation. A per-model policy can still disable it for one model. |
| **Reports** | Rendering a PDF report, for at most 20 records, if the profile may read the report's model. |
| **Attachments** | Downloading an attachment of a readable record, and uploading an attachment to a writable record. |
| **Chatter** | Posting a chatter message on a record the profile may write, on a model that has a chatter. |
| **Activities** | Full control of the connector's own activities: scheduling, reading, updating and closing. See below. |
| **Auto Approve Low Risk** | Creating the plans for chatter messages and scheduled activities as already approved. |
| **Partial Field Reads** | Answering a read with the readable columns instead of refusing it when the field list also names a field the profile withholds. |

Three of these are narrower than their names suggest:

- **Activities** is scoped by ownership, not by model. It opens `mail.activity`
  only for the activities the connector user created or is assigned to — the
  same definition Odoo's own `mail_activity_rule_user` uses. Colleagues'
  activities on the same records stay invisible.
- **Auto Approve Low Risk** is not "approve everything that looks harmless". A
  plan is auto-approved only when its computed risk is low **and** its action
  is a chatter message or a scheduled activity. Risk levels are fixed in code:
  create and update and attachment upload are medium, delete is high, chatter
  and activity are low, and a method call takes the risk level of its Method
  Policy. Method auto-approval is controlled separately by **Require Human Approval**.

- **Partial Field Reads** trims only a plain field list. A withheld field used
  in a search domain or in the sort order still fails, because skipping it would
  return a different set of records rather than the same records with fewer
  columns, and a write is never trimmed. A read whose fields are all withheld
  still fails too, so the client never receives an empty success. The response
  carries an `omitted_fields` block naming what was skipped.

  Leave it off for a profile whose allowlists are the real access control: a
  client that receives data plus a note may report a withheld field as empty
  rather than as unavailable. Turn it on for a wide internal profile, where the
  saved round trip is worth more than the strict refusal.

Auto-approval removes only the human click. The client still has to preview and
then execute the plan, and both steps are audited.

#### What Activities Opens

With the capability on, and unless an explicit Model Policy for `mail.activity`
overrides it, the profile grants the connector user:

| Operation | Allowed | How |
| --- | --- | --- |
| Read | yes | `records.search`, `records.read`, `records.count`, and aggregation when **Aggregate** is on |
| Create | through the host record | `activity.schedule`, which requires write access to the record the activity is attached to |
| Update | yes | `activity.update` on `activity_type_id`, `summary`, `note`, `date_deadline`, `user_id` |
| Close | yes | `activity.done`, which posts the feedback into the record's chatter |
| Delete | never | `record.delete` on `mail.activity` is refused, and there is no cancel action |

On Odoo 16, `activity.done` uses `_action_done` to post feedback and complete the activity. Completed activities are removed after feedback is posted. Raw deletion through MCP remains forbidden so that completion retains its audit trail.

Two fields are deliberately not writable: `res_model` and `res_id`. Moving an
activity to another record would attach it to a record the profile may not be
allowed to touch, so re-targeting is refused with `field_denied`.

Direct `record.create` on `mail.activity` is refused for the same reason:
`activity.schedule` checks write access on the host model, a bare create would
not.

An explicit Model Policy for `mail.activity` still wins over all of this — use
it when a profile genuinely needs a different scope, including deletion.

### Model Policies

Use the **Model Policies** tab for model-specific rules or exceptions. Per
model you can set:

- the allowed operations: read, aggregate, create, write, delete;
- **Readable Fields** and **Writable Fields** are independent allowlists. An empty
  list allows all fields for that operation; a populated list allows only selected
  fields. `id` and `display_name` remain readable. Odoo access rights, readonly
  fields and the separate binary permissions still apply;
- **Allow Binary Read/Write** to opt binary fields into those allowlists;
- a **Forced Domain**, a JSON Odoo domain AND-ed into every search and checked
  again after a change, so a change cannot move a record out of scope;
- **Max Records**, which can only lower the profile limit.

Security-sensitive OduMCP and credential models are rejected here as well.

### Allowed Methods

The **Allowed Methods** tab is the only way to let a client call a business
method. Nothing is callable by default and private methods are always refused.
Per entry you define the model, the method name, its risk level, how many
records it may receive, whether it may be called without record ids, whether
positional arguments are allowed, the exact permitted keyword argument names,
and the maximum argument size.

Enter an exact name in **Method Name**, or `*` to allow all public business
methods on that model. An active exact-name policy takes precedence over `*`;
its settings replace the wildcard settings completely. Inactive entries are
ignored. Patterns such as `action_*` are not supported.

**Require Human Approval** defaults to enabled. Disable it on the selected
policy to approve valid plans automatically, regardless of the risk level.
Preview, execution and audit still apply. Wildcard policies keep the same
record and argument limits; an empty keyword list still forbids keyword
arguments, and calls without record ids still need **Allow Model Method**.

Private methods (including methods marked private for RPC) and generic ORM/web
framework methods are unavailable, even with an exact policy. Use dedicated
MCP operations for CRUD, search and aggregation so their operation, field and
domain checks apply. Archive/unarchive actions remain available. Business
methods can change data internally; a read-only Model Policy does not make a
permitted business method read-only. No wildcard policy is enabled by default.

### Users

The **Users** tab assigns the profile to users directly and mirrors the field
on the user form.

## Review Changes

Preview and status responses include `approval_url` so an agent can send the
approver directly to the plan. The link uses the configured `web.base.url`; keep
that parameter set to your public HTTPS address. It contains no access token
and requires the usual Odoo login and MCP manager permissions to approve.

Open **MCP > Approval Inbox**. The list is grouped by **Request**: all
plans a client produced for one task carry the same request reference, so a
task that touches a hundred records is reviewed and decided as one group. Tick
the plans — or the header checkbox after opening a group — and use **Approve
Selected**, **Reject Selected**, or **Delete Selected Expired**. The
confirmation dialog lists what will be processed and how many selected records
are skipped because their state does not fit the action.

Review the redacted diff, target model,
risk, expiry, user, and profile before approving. Approval records are
immutable; rejection or expiry requires the client to create a new plan. An
approved plan can be executed only once and only before it expires.

The **Redacted Diff**, **Result**, and **Integrity** tabs present the stored
snapshots as highlighted YAML instead of raw JSON; **Integrity** also shows the
submitted payload, and every redacted value is marked in red. Enable developer
mode to see the underlying JSON next to each block, for example to copy it into
a ticket.

The stored payload is hashed. If it no longer matches its hash at execution
time, the plan fails instead of running.

## Audit and Quotas

Open **MCP > Audit Log** to inspect request outcomes. Every request is
logged — success, denial, and error alike — with the operation, model, target
ids, status code, error code, duration, remote address, and user agent. The
request body itself is not stored; only a hash and a short summary are. A
partial read also records the fields it skipped, so a request answered as
success still shows the policy at work. Audit
rows are immutable and drive the per-minute and daily quota checks. User
records do not duplicate request totals, failure totals, or last-use
timestamps. **Target Records** lists the affected ids as YAML, with the raw
JSON kept in developer mode.

## Global Settings

Use **Settings > MCP** to enable or disable the control API and set
payload, binary, retention, request-grouping, and event-ticket limits. Disabling the API keeps
all user MCP settings unchanged and makes every authenticated operation return
`service_disabled`.

**Request Grouping Window (minutes)** decides how plans without an explicit
batch key are grouped. Plans of the same connector user and profile join the
last request while less than that many minutes pass between them; the default
is 10. Zero puts every plan in its own request. A client that sends a batch key
is unaffected by this setting.

Retention is enforced by Odoo's autovacuum: audit rows older than the audit
retention window and finished approvals older than the approval retention
window are deleted, and expired plans are marked expired. Nothing else can
delete these rows.

## Disable Access

Clear **MCP Active** to stop MCP access without deleting the selected profile.
A user who keeps the profile with the flag cleared is the supported suspended
state, and restoring access is one checkbox. Prefer it to the alternatives:
clearing the profile loses the record of which one was granted, archiving the
profile stops everyone who shares it, and archiving the user stops all of Odoo
for that person. Personal keys are left alone: they are that person's own
credentials, and the cleared flag already refuses them. Revoke those keys from
the user's **Account Security** tab when credentials may be exposed. Existing
OduPilot session tokens are refused immediately. Any of these actions also invalidates outstanding event
tickets.

Removing a user from a profile's **Users** tab is the same revocation seen from
the other side: it clears the profile and the flag together.

## When a Client Reports No Access

A caller without MCP access receives `403` from `/odumcp/v1/*` with one of
two codes: `mcp_access_not_configured` when no profile is selected, and
`inactive_mcp_access` when the Odoo user, the flag or the profile is inactive.
The MCP server reports both to its own client as `401`, and a client such as
OpenCode then exposes no Odoo tool at all. In a chat this reads as a missing
MCP server while the server is in fact refusing that one user, so check both
fields on the user before investigating the server or the session API key. OduPilot requires no permanent key in **Account Security**: it issues a signed token for every conversation.


## Odoo 16 deployment

Install `odumcp` from `addons`; use Oduflow or its accompanying MCP server. The event endpoint `/odumcp/v1/events` uses authenticated short polling; the server waits one second after an empty response. Personal API keys require valid Odoo 16 expiration dates. This port does not migrate an Odoo 15 database.

## Installation identity

Install `odumcp` as a new addon. The addon uses `odumcp.*` models and settings, `/odumcp/v1/` API routes, the `odumcp_server` Python package and `ODUMCP_*` server variables. No migration of an earlier installation is provided. Uninstall the earlier addon before deploying this code; uninstalling it also removes dependent modules and their data. Reinstall required dependent modules afterward. Build the renamed server image locally before using the Compose example (`docker compose -f docker-compose.example.yml up --build -d`); publication of that image is a separate operation.

## Odoo 16 compatibility

Use branch `16.0` for a fresh installation on Odoo 16. Install the module from `addons` together with its declared dependencies. This branch does not downgrade an existing Odoo database.

## Oduflow production integration

Oduflow can call this module directly; a separate MCP server is optional.
Oduflow installs the module when creating an Odoo 16 production and registers
its configured production credential as an MCP-only API key on the administrator.
The managed key is named **Oduflow production (managed)**. Only its password hash
is stored in Odoo; the plaintext credential remains in Oduflow configuration.

The local provisioning operation replaces only the managed key. Personal API
keys remain valid. Existing MCP profiles, policies and suspended access remain
unchanged. If the administrator has no profile, a read-only profile is created;
configure write permissions explicitly before using business change plans.

After changing the production credential and restarting Oduflow, use
`sync_production_mcp` to synchronize one production or all productions in the
team. Review every result and retry failed or stopped targets after recovery.
Each database rotates independently; its old key remains valid until successful
synchronization. Restoring a database backup can restore an old key, so synchronize
after restoration as well. Removing the credential from Oduflow alone does not
revoke it in Odoo; remove the managed API key when retiring the integration.

Requests authenticated with the managed key record `source = oduflow` in the
audit log. This identifies the credential, not a particular human or a verified
network origin, and grants no policy bypass. Business approval remains in Odoo;
production infrastructure operations are authorized separately by Oduflow.

## Unified module upgrade

Version `16.0.1.4.0` combines the platform and client modules. Upgrade `odumcp` in place; keep existing records, profiles, approvals and audit logs. The bundled `deploy/odumcp_server` remains available. The application is now labelled **MCP**.

Review existing Model Policies before upgrading: an empty readable or writable field list now permits all otherwise eligible fields for that operation. Populate those lists to retain a narrow field scope. Operation permissions, Odoo ACLs, forced domains and binary restrictions still apply.

Managed-key provisioning requires a superuser environment. It accepts both `Oduflow production` and `Oduflow production (managed)` as managed MCP key names on the administrator. On the next provisioning call it replaces those rows with one canonical `Oduflow production (managed)` key. Personal keys and keys with another scope remain untouched. Reapplying the same non-expiring canonical key preserves its row. Existing profiles and suspended access remain unchanged. Audit identifies either managed name as `source = oduflow` even before reprovisioning.
