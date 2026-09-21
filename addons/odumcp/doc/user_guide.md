# OduMCP User Guide

## Before You Start

Your administrator must enable **MCP Active** and select a **Profile** on
your Odoo user. A disabled user, disabled MCP flag, or inactive profile blocks
all MCP requests.

## Your MCP API Keys

OduPilot uses a signed token for each conversation instead of a personal API key. Closing or deleting the conversation revokes its access.

To connect a separate external MCP client, create your own API key:

1. Open your Odoo profile and go to **Account Security**.
2. Create a new API key.
3. Enter a recognizable description.
4. Keep **Access** set to **MCP only**.
5. Copy the key immediately and store it in your password manager.

That key is shown only once. Revoking it immediately disconnects clients that
use it. An MCP-only key cannot authenticate normal Odoo RPC calls, and a
regular **All APIs** key cannot authenticate the MCP API. Creating, replacing,
or revoking a personal key does not affect OduPilot sessions.

## Connect a Client

Configure the OduMCP server URL and use the generated key as its bearer
token. The client acts as your Odoo user and is additionally restricted by the
selected MCP profile: allowed companies, models, fields, operations, record
limits, and request quotas.

## What the Connector Can Do

Everything the client can reach is decided by your profile. Ask your
administrator which of these are enabled for you.

- **Explore** the connected database, the models you may use, and their
  fields.
- **Read** records: search with a domain, read by id, count, and grouped
  aggregation.
- **Download** an attachment of a record, or render a PDF report.
- **Propose changes**: create, update, or delete records; post a chatter
  message; upload an attachment; call a business method allowed by an exact-name policy or a model-wide `*`
  policy. Its approval and argument limits still apply.
- **Manage your activities**: schedule one on a record, reassign it, move its
  due date, reword it, and close it with a feedback note.

## Your Activities

When your profile allows activities, the client works with the activities you
own — the ones you created and the ones assigned to you. Somebody else's
activity on the same record stays invisible and untouchable, exactly as Odoo's
own rules define ownership.

Within that scope the client can read them, change the responsible person, the
due date, the type, the summary and the note, and close them. Closing asks for
a feedback note that stays as a message in the record's chatter, so a finished
activity leaves a trace.

Activities are never deleted. There is no "discard" — an activity you no longer
need is closed with a note saying so. The client also cannot create an activity
as a bare record: it schedules one on a record, which is only possible where
your profile already allows changing that record.

A request that the profile does not permit fails with `policy_denied` instead
of silently returning less data.

## Changes and Approvals

The agent receives `approval_url`, a direct link to the exact plan, and can share
it with you. Open the link, sign in to Odoo if needed, and review the plan.
Opening the link does not approve it; an MCP manager must choose the approval action.

Read operations run immediately when permitted. Nothing is written to Odoo in a
single step: every change is first previewed, then executed.

1. The client sends a **preview** together with an idempotency key. Odoo
   validates the plan against the profile, computes the affected records, and
   stores a redacted diff.
2. An MCP manager reviews the exact plan in **MCP > Approval Inbox**
   and approves or rejects it.
3. The client executes the approved plan. Only an approved and unexpired plan
   can be executed, and only once.

Plans are grouped by the request they came from. A client that changes a
hundred records sends the same **batch key** with every preview, and Odoo puts
all of them under one request reference such as `MCP/2026/00042`. Without a
batch key Odoo groups the plans of one user and profile that arrive close
together, so a single task still lands in a single request.

**MCP > Approval Inbox** is grouped by request by default. Open a
request, tick the records you want — or the header checkbox to take the whole
group — and use **Approve Selected**. **Reject Selected** and **Delete Selected
Expired** work the same way. So a hundred plans of one task are decided in one
step instead of a hundred clicks, while approving only part of a request stays
possible.

Repeating a preview with the same idempotency key returns the existing plan
instead of creating a second one. Reusing that key for a different plan is
refused with `idempotency_conflict`.

A plan expires after the profile's approval TTL. An expired or rejected plan
cannot be revived — the client has to create a new one with a new idempotency
key.

If your profile has **Auto Approve Low Risk** enabled, two actions skip the
manual approval step and are created as already approved: posting a chatter
message and scheduling an activity. The client still has to execute them
explicitly, and they are audited like every other change.

The **Redacted Diff** and **Result** tabs show the plan as highlighted YAML:
one line per key, records separated by a leading dash, and redacted values in
red. The raw JSON behind it stays available in developer mode.

## Live Updates

The client can subscribe to resource updates for your user. It requests a
short-lived event ticket and then polls the event stream. Odoo notifies it when
an approval changes state or when an executed change touched a record, so the
client can refresh without re-reading everything.

## Troubleshooting

- `mcp_access_not_configured`: ask an administrator to select a profile and
  enable MCP in your user's **Account Security** tab.
- `inactive_mcp_access`: check that the user, MCP flag, and profile are active.
- `service_disabled`: an administrator turned off the connector API in
  **Settings > MCP**.
- `policy_denied`: the selected profile does not permit the requested model,
  field, operation, method, or feature.
- `access_denied`: Odoo access rights or record rules refuse it, or an existing
  record is outside the scope forced by the profile. The error lists the denied
  record ids, so the call can be retried without them.
- `field_denied`: the search domain or field list uses a field the profile does
  not expose. The error names those fields. On a profile with **Partial Field
  Reads**, a plain field list succeeds instead and the answer carries an
  `omitted_fields` block: those fields were withheld, not empty.
- `unknown_field`: a requested field does not exist on the model at all, usually
  a typo or a field from another Odoo version. This is not a permission problem
  — the model schema lists the usable names.
- `record_not_found`: one or more requested record ids do not exist. The error
  lists the missing ids and, for a mixed request, any existing but denied ids,
  so all unusable ids can be removed in one retry.
- `rate_limit_exceeded` / `daily_quota_exceeded`: wait before retrying, or ask
  for a larger quota.
- `payload_too_large` / `response_too_large`: the request or its result exceeds
  the configured size limit; narrow the field list or the number of records.
- `idempotency_conflict`: the idempotency key already belongs to another plan.


Choose an expiration date permitted by your Odoo groups when creating a key. Expired keys are rejected even when MCP access remains enabled.

## Odoo 16 compatibility

Use branch `16.0` for a fresh installation on Odoo 16. Install the module from `addons` together with its declared dependencies. This branch does not downgrade an existing Odoo database.

## Requests through Oduflow

Administrators can connect through Oduflow without a separate MCP server.
Review the same approval plans in Odoo; existing model policies and approval
requirements still apply. Audit entries using the managed integration credential
show `source = oduflow` and the administrator as the Odoo user. A shared credential
does not identify the individual person who initiated the request.
