# OduMCP Technical Specification

## User Assignment

`res.users` owns `mcp_active`, `mcp_profile_id`, `mcp_event_channel`, and
`mcp_event_version`. `_mcp_for_user()` returns a sudoed user only when the Odoo
user, MCP flag, and profile are active. The obsolete `odumcp.access` model
does not exist.

`mcp_active` defaults to `False` and is a switch independent of the assignment:
`_check_mcp_profile()` forbids the flag without `mcp_profile_id`, while a
profile with the flag cleared is the supported suspended state. `_mcp_for_user()`
returns `mcp_access_not_configured` without a profile and `inactive_mcp_access`
when the user, the flag or the profile is inactive; controllers answer `403` for
both, which the MCP server passes on to its client as `401`.

Enabling or disabling `mcp_active` does not create or delete API keys. The
profile inverse `_inverse_assigned_user_ids()` clears `mcp_active` together
with `mcp_profile_id`, which satisfies `_check_mcp_profile()` and immediately
makes every existing key fail the controller's `_mcp_for_user()` check.
Personal permanent keys remain credentials for external MCP clients. OduPilot
validates the same access state before issuing its separate signed session token.

The event fields are internal plumbing and do not appear in the user form.
`mcp_event_channel` is unique by generated value and is created for existing
users by migration or lazily before use.

## Quotas and Audit

Quota checks count `odumcp.audit.log` rows by `user_id`. No request,
failure, or last-use counters are stored on `res.users`. Audit and approval rows
store direct `user_id` and `profile_id` references.

## HTTP Surface

All endpoints live under `/odumcp/v1` and answer JSON with `Cache-Control:
no-store`, `Pragma: no-cache`, and `X-Content-Type-Options: nosniff`.

| Route | Auth | Method | Purpose |
| --- | --- | --- | --- |
| `/health` | public | GET | Liveness probe, no database state. |
| `/identity` | `mcp` | GET | Database, user, and profile code. |
| `/capabilities` | `mcp` | GET | Profile limits, features, and model list. |
| `/execute` | `mcp` | POST | Single `{"operation", "params"}` envelope. |
| `/events/ticket` | `mcp` | POST | Issues a short-lived event ticket. |
| `/events` | `mcp_event` | POST | Long-poll of the user bus channel. |

`ir.http._auth_method_mcp` accepts only a `Bearer` Odoo API key whose scope is
`mcp`, and refuses a key that contradicts an existing session uid.
`_auth_method_mcp_event` accepts only an unexpired event ticket, runs as the
public user, and carries the channel in `odumcp_event_channel`.

Every authenticated route returns `service_disabled` (503) while
`odumcp.enabled` is false. `/execute` rejects a request larger than
`odumcp.max_payload_bytes` before authentication work, and replaces an
oversized response body with `response_too_large` (413).

## Operations

`odumcp.service.execute_request` wraps every dispatch in a savepoint,
except `changes.execute`, whose approval state transitions must survive a failed
business change; that one isolates the business work in an inner savepoint
instead. Every request writes exactly one `odumcp.audit.log` row, including
denials and errors, with a SHA-256 of the canonical input rather than the input
itself.

| Operation | Gate beyond the model policy |
| --- | --- |
| `capabilities`, `system.info`, `identity.whoami` | none |
| `models.list` | none; lists policy models plus, under a non-explicit default, every readable model |
| `models.describe` | `allow_schema` |
| `records.search`, `records.read`, `records.count` | read policy |
| `records.aggregate` | `allow_aggregate` on both the profile and the model policy; aggregated fields must be stored |
| `attachments.read` | `allow_attachments` plus read policy on the attachment host model |
| `reports.render` | `allow_reports`, read policy on the report model, at most 20 records |
| `changes.preview`, `changes.status`, `changes.execute` | per-action, see below |

Read paths validate field paths through `_allowed_field_names` before touching
the ORM: search domains, `order`, `fields`, and `groupby` all reject a field the
policy does not expose, including across relational hops.

An empty read or write field list on an explicit model policy allows every field
visible to the connector user for that operation. The lists are independent;
populated lists remain restrictive. Binary permission flags, readonly and magic
write-field checks, operation permissions, Odoo ACLs and record rules still apply.
Existing empty policies acquire this behavior on upgrade; no field selections
are rewritten. Fallback policies for models without an explicit policy are unchanged.

`odumcp.model.policy.read_field_ids` and `write_field_ids` carry
`domain="[('model_id', '=', model_id)]"` on the field definition itself, not only
in the form view. A policy is edited in a dialog above the `policy_ids` list, where
the record datapoint keeps `viewType="list"`; the "Search More" dialog asks for
the domain without a view type, does not find these fields in the tree view and
falls back to the domain of the field. Moving the domain back into the view alone
makes that dialog list every field of every model again.

## Error Reporting

`McpServiceError` carries an optional `data` dictionary that `_error_body` puts
into `error.data`, so a client can repair a rejected call instead of probing for
the cause. Rejections stay all-or-nothing: one bad name or id fails the whole
request, and the payload names every offender.

`_check_field_names` is the single gate for `fields`, write values, `order`, and
domain paths. It splits a rejected name in two:

| Condition | Code | Status | `error.data` |
| --- | --- | --- | --- |
| The name is absent from `Model._fields` | `unknown_field` | 422 | `model`, `unknown_fields`, `denied_fields` |
| The name exists but the policy withholds it | `field_denied` | 403 | `model`, `denied_fields` |
| A write targets a readonly field | `field_denied` | 403 | `model`, `readonly_fields` |
| A domain hop reaches a model without a read policy | `field_denied` | 403 | `model`, `denied_path` |
| Requested ids exist but are out of scope | `access_denied` | 403 | `model`, `denied_ids` |
| One or more requested ids do not exist | `record_not_found` | 404 | `model`, `missing_ids`, `denied_ids` |

A call carrying both an unknown and a denied name reports `unknown_field` and
lists the denied ones alongside, because a name that does not exist is the more
likely defect. This discloses nothing new: every reported name came from the
client's own request.

`_records_in_policy` first searches under the forced domain, then uses `exists()`
on the unmatched ids to separate deleted rows from rows that still exist outside
the policy. A mixed request reports `record_not_found` and carries both groups in
`missing_ids` and `denied_ids`, so the client can remove every unusable id in one
retry. A later ORM `MissingError` also maps to `record_not_found` (404), while
`AccessError` keeps `access_denied` (403). The audit row stores the resulting
`error_code` and the originating `error_class`.

### Partial Field Reads

With `odumcp.profile.allow_partial_field_reads`, `_read_fields_with_omissions`
trims an explicit `fields` list instead of refusing the call: `records.search` and
`records.read` return the readable columns plus an `omitted_fields` block holding
`denied`, `unknown` and a human-readable `note`. The flag defaults to false, so an
upgrade does not change how an existing profile answers.

Trimming is deliberately limited to a plain field list. A denied field in a domain
or in `order` still fails, because dropping a domain leaf would silently widen the
result set rather than narrow the columns, and `_write_values` never trims — a
partial write would lose part of an approved change. A request whose fields are
*all* rejected still raises `unknown_field` or `field_denied`, so a trimmed read
can never degrade into an empty success.

`odumcp.audit.log.omitted_fields` records what was trimmed
(`denied=a,b; unknown=c`), because such a request is audited as `success` and would
otherwise leave no trace of the policy acting.

## Change Actions

`changes.preview` normalizes the payload, stores its canonical JSON with a
SHA-256, and returns a redacted diff. `changes.execute` re-runs `_prepare_action`
on the stored payload, so a policy tightened between preview and execution
applies. Idempotency is `UNIQUE(user_id, idempotency_key)`; the same key with a
different payload hash is a 409.

All three change operations serialize the plan through `_public_dict`, including
idempotent preview and execution retries. The additive `approval_url` field is
an absolute Odoo 19 form URL: `get_base_url()` (from `web.base.url`, with trailing
slashes removed) plus `/odoo/action-<approval action id>/<approval record id>`.
It identifies the exact immutable plan, including when several plans share a
request reference. No request host header or access token is used. Normal web
session authentication, record access and approval permissions still apply.
Pending plans also mention `approval_url` in `next_step`.

`changes.preview` also accepts an optional `batch_key` (string, 1..128 chars; a
wrong type or length is `invalid_batch_key`, 400). `_assign_request` turns it
into the grouping pair stored on the plan:

- `request_key` — `key:<batch_key>` when the client sent one, otherwise
  `auto:<uuid4>`. It is the join key, never shown as the group label.
- `request_ref` — the human-readable label from the `odumcp.request`
  sequence (`MCP/<year>/00001`), also returned to the client as `request` in
  `_public_dict`.

With a batch key the plan joins the newest plan of the same `user_id` carrying
the same `request_key`. Without one it joins the newest plan of the same
`user_id` and `profile_id` whose `request_key` starts with `auto:` and whose
`create_date` is younger than `odumcp.request_window_minutes` (default 10,
`0` disables joining). A non-integer parameter falls back to 10.

Both fields are plain indexed `Char`. The Approval Inbox groups on `request_ref`
by default (`search_default_group_request`), and the header buttons act on the
selection, so one request is approved in one step. Migration
Audit chain data is initialized on installation; Odoo 15 migration scripts are not included in this port.

| Action | Capability gate | Policy operation | Risk |
| --- | --- | --- | --- |
| `record.create` | none | `create` | medium |
| `record.update` | none | `write` | medium |
| `record.delete` | none | `unlink` | high |
| `message.post` | `allow_chatter` | `write` on the host model | low |
| `activity.schedule` | `allow_activities` | `write` on the host model | low |
| `activity.update` | `allow_activities` | `write` on `mail.activity` | low |
| `activity.done` | `allow_activities` | `write` on `mail.activity` | low |
| `attachment.create` | `allow_attachments` | `write` on the host model | medium |
| `method.call` | an active `odumcp.method.policy` | `read` | the method policy's own level |

Auto-approval is `auto_approve_low_risk and risk == "low" and action in
AUTO_APPROVED_ACTIONS` (`message.post` plus the three activity actions). It only
sets the initial state to `approved`; the preview/execute round trip and the
audit rows are unchanged. For `method.call`, auto-approval instead follows the
selected method policy: it is enabled when `requires_approval` is false,
regardless of risk level.

### Method policy resolution

`Method Name` accepts either a public business method identifier or the literal
`*`. `_for_method` selects an active exact match for the model first, then an
active wildcard for that same model and profile. Settings are never merged.
Preview and execution resolve the policy again; removing or disabling the only
matching policy prevents execution of an already approved plan.

Method names must be valid public identifiers. Generic methods exposed by the
registry's `base` model are refused even when overridden by a concrete model;
`action_archive`, `action_unarchive` and `toggle_active` are the business-action
exceptions. This blocks direct ORM and web CRUD/search APIs, environment and
recordset manipulation, imports and exports. Use dedicated MCP operations for
those supported operations. Non-callable attributes and nonexistent methods
return not-found; methods decorated with `@api.private` are refused.

The selected policy supplies risk, approval, record and argument limits. Empty
keyword lists forbid kwargs; positional arguments and calls without ids require
their existing opt-ins. Odoo user rights and model read/domain checks still
apply. Business methods may perform writes internally, so granting a method is
not a read-only guarantee. No wildcard is seeded during installation or upgrade.

## Activity Access

`allow_activities` resolves `mail.activity` through `ActivityModelPolicy`, a
third policy adapter alongside `GlobalModelPolicy`. `_get_policy` tries an
explicit `odumcp.model.policy` first, then this adapter when
`_has_activity_access()` holds, then the profile-wide fallback — so an explicit
policy still overrides it. Because the adapter needs the caller, `_get_policy`
takes a `user=` keyword; the service passes `access` at every call site.

The adapter's `_forced_domain()` is
`['|', ('create_uid', '=', uid), ('user_id', '=', uid)]`, matching the core
`mail_activity_rule_user` record rule that Odoo applies to write and unlink.
Odoo does not restrict *reading* activities, so this narrows read as well.
`allow_read` and `allow_write` are true, `allow_aggregate` follows the profile,
and `allow_create` and `allow_unlink` are false. Field access is two fixed sets,
`ACTIVITY_READ_FIELDS` and `ACTIVITY_WRITE_FIELDS`; `res_model`/`res_id` are
readable but not writable, so an activity cannot be re-targeted at a record
outside the profile.

`activity.update` writes through `_records_in_policy` and re-checks the forced
domain afterwards. `activity.done` calls `mail.activity.action_feedback`, whose
`_action_done` posts the feedback message and then unlinks the row; the handler
reads `res_model`/`res_id` before that call because the record is gone after it.
`_publish_execution_updates` prefers `res_model`/`res_id` from a result, so the
event points at the host record rather than at a deleted activity.

`_op_models_list` adds `mail.activity` to the listing when the capability is on
even under `default_model_access = explicit`.

## Policy Resolution

`odumcp.profile._get_policy` returns an explicit `odumcp.model.policy`
when one is active for the model. Otherwise it builds a `GlobalModelPolicy`
adapter from `default_model_access`, `allow_global_create`, and
`allow_global_unlink`, unless the model is transient or listed in
`BLOCKED_POLICY_MODELS`. Models in `GLOBAL_ACCESS_READONLY_MODELS`
(`base.automation`, `ir.actions.server`, `ir.cron`, `ir.mail_server`,
`ir.model.access`, `ir.rule`, `ir.ui.view`, `res.groups`, `res.users`) stay
readable but never creatable, writable or deletable through that adapter.

`BLOCKED_POLICY_MODELS` cannot be named by an explicit policy at all, and is the
only set the fallback refuses outright. The adapter's field allowlist excludes
binary fields and anything matching `SENSITIVE_FIELD_NAME_RE`, which also covers
a bare `pass` segment such as `ir.mail_server.smtp_pass`; for `create`/`write`
it also drops readonly and `WRITE_MAGIC_FIELDS`.

`_records_in_policy` re-searches the requested ids under the forced domain,
classifies unmatched ids as missing or denied, and lists them in `error.data`
before calling `check_access_rights` and `check_access_rule`.
`_enforce_forced_domain_postcondition` re-checks the forced domain after a write
or create so a change cannot move a record out of scope.

## Immutability and Retention

`odumcp.audit.log` refuses `create` without `mcp_audit_system_create`,
refuses `write` unconditionally, and refuses `unlink` outside a system-level
`mcp_retention_cleanup`. `odumcp.approval` refuses any `write` outside
`mcp_approval_system_write` and the same cleanup context for `unlink`. Both
models autovacuum on `odumcp.audit_retention_days` (90) and
`odumcp.approval_retention_days` (30); the approval vacuum also expires
pending or approved plans past `expires_at`.

## Events

`odumcp.event.ticket.user_id` binds each short-lived ticket to the user.
Approval state changes increment `res.users.mcp_event_version` and publish on
`res.users.mcp_event_channel`, as does every record touched by an executed
change (`odoo://record/<model>/<id>`).

`odumcp.event.ticket` stores only a SHA-256 of its token, expires after
`odumcp.event_ticket_ttl_seconds` (600, clamped to 60..3600), and is
autovacuumed. `_check` also revalidates that the user, the MCP flag, and the
profile are still active.

## API Keys

`res.users.apikeys._check_mcp_credentials` authenticates only a key whose scope
is `mcp` on an active user; global keys are excluded by the SQL filter, so an
MCP key never authenticates a normal RPC call and vice versa. The description
wizard exposes `scope_mode` and passes `odumcp_api_key_scope` into
`_generate`.

OduPilot issues signed session tokens and does not create temporary API-key
rows. Session validation is provided by the OduPilot authentication extension.
Personal MCP keys are checked against their expiration date both when matching
a specific key and when authenticating the MCP endpoint. `_generate` forwards
the mandatory Odoo 19 expiration argument to the core implementation.

## Odoo 19 port

The module installs on Odoo 19 alongside its accompanying MCP server. It does
not migrate existing Odoo 15 data. Groups use `res.groups.privilege` and
`res.users.group_ids`; views use list roots, inline modifiers and Settings apps.
ORM domains use `fields.Domain`, access checks use `check_access`, and database
constraints use `models.Constraint`.

The events controller polls `bus.bus._poll` on the authenticated ticket's
private channel without closing the request cursor. The MCP server waits one
second after an empty response. It does not require Odoo 15's event dispatch
long-polling API. Completed activities may be archived by Odoo 19 while their
feedback remains in the chatter.

## YAML Snapshot Preview

`models/yaml_preview.py` holds a minimal YAML dumper (`json_to_yaml_html`) that
turns a stored JSON snapshot into a `<pre class="o_mcp_yaml">` block whose
tokens carry `o_mcp_yaml_key`, `_str`, `_num`, `_const`, `_punct`, and
`_redacted` classes. PyYAML is not a dependency; the dumper quotes any scalar
that YAML would otherwise read as a number, boolean, timestamp, or comment, and
escapes every value through `html_escape`. Invalid JSON is rendered as escaped
text instead of raising.

`odumcp.approval` exposes the non-stored computed fields `diff_yaml`,
`result_yaml`, and `payload_yaml` (`groups="odumcp.group_mcp_manager"`,
like `payload_json`); `odumcp.audit.log` exposes `target_ids_yaml`. All of
them are `fields.Html(sanitize=False)` and are rendered read-only. The raw
`*_json` fields stay on the same form behind `groups="base.group_no_one"`.
Colours live in `static/src/scss/yaml_preview.scss`, loaded through
`web.assets_backend`; no JavaScript is involved.

## User Interface

The user form view inherits `auth_totp.view_totp_form` and adds **MCP Access**
inside the existing **Account Security** page. Only MCP managers see and edit
the two fields. No separate MCP page is introduced.

## Installation identity

The technical addon name is `odumcp`, the model namespace is `odumcp.*`, and HTTP routes begin with `/odumcp/v1/`. The MCP protocol can be served by Oduflow or by the bundled `deploy/odumcp_server` package. Existing Odoo 19 `odumcp` installations upgrade in place; installations under an earlier addon identity are outside this upgrade contract. OduPilot depends on `odumcp`. Upstream contributor attribution is retained.

## System Parameter Policies

`ir.config_parameter` uses the standard explicit policy and global fallback paths.
Odoo ACLs remain enforced in the connector user environment with `su=False`.
Explicit forced domains restrict searches and reads by ID; a Read-only policy
denies mutation operations even when the profile fallback allows writes.


## Sidecar Publishing

`deploy/publish.sh` reads the immutable image version from
`deploy/odumcp_server/pyproject.toml`, runs the complete sidecar tests and
Ruff, then pushes the versioned tag and `latest`. Release checks are fail-closed:
an unavailable `uv` executable aborts unless `SKIP_TESTS=1` was explicitly set,
and any registry inspection failure other than a confirmed missing manifest
aborts instead of assuming that the version tag is free. `ODUMCP_OVERWRITE=1`
is the only path that deliberately replaces an existing versioned tag.


## Oduflow managed keys

`res.users.apikeys._set_oduflow_key(key)` is a private, superuser-only provisioning
method. It accepts 32..512 ASCII characters without whitespace, serializes on the
administrator user row and replaces only MCP-scoped keys with the reserved
managed name. Reapplying the same key returns `changed = false`. Personal keys
and existing profiles/suspension are preserved. An absent profile receives read
access without global create/delete or auto-approval. Keys use the native Odoo
password hash and index; their plaintext is neither persisted nor returned.

Authentication annotates the request context from the matched API-key record.
`odumcp.audit.log.source` is `oduflow` for the managed key and `mcp` otherwise.
This metadata labels the credential and is not an additional authorization grant
or proof of network origin. Rotation and revocation remain explicit across
independent databases. Infrastructure authorization belongs to Oduflow.


## Unified provisioning compatibility

The superuser-only `_set_oduflow_key` locks the administrator row before provisioning. Both managed MCP key names are reconciled on the next call, preserving personal keys, other scopes, user policies and suspension. The result preserves both callers: `user_id`, `changed`, `key_set`, `user`, `scope`, `profile`, `mcp_active`, and `replaced_keys`. It never returns credentials. Idempotence requires one canonical non-expiring key with the supplied hash match.
