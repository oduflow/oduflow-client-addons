# OduPilot technical specification

## Origin and installation boundary

OduPilot is the Odoo 19 port of VelesAgro `ai_chat` 15.0.1.46.0. The addon and
model prefix is `odupilot`; assets, XML IDs, configuration parameters, bridge
methods and environment variables use that namespace. The original OPL-1
license and Odooist attribution remain. This addon installs into a new Odoo 19
database; it does not perform a database upgrade from Odoo 15. Imported daily
change entries are historical records of the source implementation.

Dependencies are `mail`, `auth_totp` and the accompanying Odoo 19 `odumcp`.
Browser and event functionality previously supplied by `streams` and
`bus_actions` is implemented locally. The Python requirements are declared in
`.oduflow/requirements.txt` and the manifest.

## Records and authorization

`odupilot.profile` stores model, provider credentials, workspace policy, agent
availability and session limits. `odupilot.agent` stores instructions, tool
rules and MCP server bindings. A session belongs to one user, profile, agent
and private `discuss.channel` with `channel_type='group'`.

`discuss.channel.is_odupilot` persists after session deletion and drives the
sidebar category. `discuss.channel.member` replaces the Odoo 15 membership
model. Session owners and administrators manage invitations; invited members
cannot reshare. Guests and inactive/external users are rejected. Worktree
members must be administrators. Direct member creation, removal and identity
changes are guarded as well as the channel invitation methods. An owner
leaving closes the session; another participant leaving does not. The active
session's bot cannot be removed, including by supplying a bypass context.

Record rules expose sessions, permissions, recoveries and audit events only to
members or administrators. Public bridge methods require
`odupilot.group_bridge`, independently of administrator status. The group is
part of an Odoo 19 `res.groups.privilege`; installation does not alter existing
user memberships. Methods that need credentials elevate access internally
after verifying the caller.

## Session and command protocol

A session progresses through `init`, `ready`, `busy`, `waiting_approval`,
`error` and `closed`. Status includes a bounded error, agent identity and the
`discuss_only` flag for worktree sessions. State changes publish
`odupilot.session/status` only to channel participants.

`odupilot.command` is the durable outbox. Commands have idempotency identifiers,
processing timestamps, retry state and an ordered claim/ack lifecycle. Claiming
uses row locks and respects per-session ordering and prerequisites. Commands
carry only the credentials needed by the dedicated bridge. Closing or deleting
a session preserves sufficient cleanup data for the bridge.

The bridge authenticates by XML-RPC for model operations and an HTTP session
for `POST /odupilot/bridge/poll` (JSON-RPC). This route accepts a nonnegative
integer `last`, checks bridge membership and polls only `odupilot_commands`.
Wake-up events contain no command payload. After an empty response the bridge
waits one second before checking again. There is no dependency on the removed
Odoo 15 `/longpolling/poll` endpoint. OpenCode SSE reconnection, backfill and
busy-session reconciliation remain in the bridge.

## Odoo MCP identity

The session issues a signed, expiring token instead of creating an API-key row.
Validation rechecks session state, owner, active MCP flag and profile. Closing
the session invalidates its token. Personal MCP-only keys remain independent;
OduMCP validates their expiration as well as their scope and user.

MCP calls are constrained by both the actor's Odoo rights and the configured
MCP policies. Profile rules cannot expand ORM access. Optional specialized
agents require their target business models to be installed.

## Chatter questions

`odupilot.ask.wizard` checks access to a saved record and posts the user's
question as an internal note. A hidden `is_ask_session` conversation serves the
user without consuming the ordinary chat quota. Its owner membership is
removed before creating the session record. Each question receives a fresh
OpenCode context; service sessions use a files workspace and cannot request
interactive tool permissions.

Answers replace the question status and append sanitized answer HTML to the
same note. Reasoning and tool traces stay in the service conversation. Existing
messages update through `mail.record/insert`; a missing source note produces a
new note and a targeted `odupilot/chatter` event. The Chatter component reloads
messages without discarding edits to the form.

## Browser data and streaming

Odoo 19 `_to_store` serializes custom channel and message properties.
`Store.add_records_fields` is used inside overrides to avoid recursion.
`channel_info` is a guarded compatibility method; normal browser traffic uses
Discuss Store. `action_open_channel` supplies a numeric channel ID in the
Discuss action context and parameters.

The Owl frontend patches current Thread, Message, DiscussApp and Chatter
components/models. Decision requests render as Message cards even when their
underlying mail message is a notification. Both normal message-body layouts
include the permission/recovery card. Decisions call the corresponding
`action_reply` and disable buttons during submission; bus updates carry the
final state and actor.

`odupilot_stream/update` carries start snapshots, sequenced part deltas and
terminal states. Text is capped at 200000 characters and traces at 60 parts.
Gaps trigger the model-level `stream_snapshot(channel_id)` RPC, which checks
membership. A newly opened thread loads a snapshot. A newer event wins over
an outstanding snapshot response, including done/error events. The temporary
stream is removed when the saved answer arrives. Live text is escaped; saved
Markdown/HTML is sanitized. Record markers expand into Odoo form links.

Final answers and decision requests use `odupilot_assistant`; other bot steps
use `odupilot_step`. Steps do not raise reply notifications. Persistent reply
notifications are replaced per conversation and closed when the thread opens.
Worktree conversations bypass docked chat windows. Ordinary mute preferences
remain effective.

## Developer workflow and voice input

The developer menu captures the current action, record, view and URL in a
wizard. Worktree profiles configure repository credentials, base branch and
Oduflow environment tools. A triage marker can resolve a settings question or
assign a code request to the responsible administrator. Assignment adds that
user to the conversation and publishes `odupilot/assigned` to their partner.
Workspace creation, environment preparation, publication markers and cleanup
are implemented by the bridge and require configured external services.

The Owl text field includes a local MediaRecorder helper. It stops after 300
seconds and releases microphone tracks on completion or unmount. Server-side
transcription validates administrator access, duration, MIME type and a 25 MiB
limit. The provider uses the profile's credentials, the common AI URL and
`odupilot.transcription_model` (default `whisper-1`). Audio is not persisted in
Odoo; the returned text remains editable before submission.

## Recovery and retention

The watchdog runs every five minutes. It cancels queued work after a busy
request times out, enqueues an idempotent abort and records the interruption.
Without tool activity there is at most one automatic retry. Tool activity or a
failed replay requires a recovery decision. Retry and dismiss are audited;
a late final answer cancels unnecessary recovery commands.

Event and closed-session retention are configurable; zero means indefinite
retention. Cleanup preserves Discuss channels and messages. Runtime health and
error history are available through the monitoring models and views.

## Verification

Backend tests cover routing, policy gates, bridge lifecycle, worktrees,
permissions, recovery, retention, Markdown safety and Store serialization.
HTTP tests exercise the bridge route and the snapshot RPC. Hoot tests cover
stream delta assembly and gap detection. The bridge and MCP server retain
independent Python suites. Live provider credentials and external developer
environments require integration validation after configuration.
