# OduPilot Administrator Guide

## Install on Odoo 17

Install `odupilot` from this repository's `addons` directory. Its dependencies include `mail`, `auth_totp` and `odumcp`. Install the Python packages listed in `.oduflow/requirements.txt` before loading the module. The Odoo 15 modules `ai_chat`, `streams` and `bus_actions` are not required.

This is a port for installation on Odoo 17. It does not migrate an existing Odoo 15 database or rename installed database records. Imported change entries describe the source module's history.

## Infrastructure

Build and deploy `addons/odupilot/deploy/docker-compose.yml`. Copy its `.env.example` into your secret store and configure Odoo credentials, OpenCode Basic Auth, volume names and numeric UID/GID. OpenCode and the bridge share a private network and a persistent `/workspace` volume. Odoo stores paths and configuration; it need not mount this volume. Keep OpenCode port `4096` private.

The compose file builds the local bridge and the pinned OpenCode image. It includes local document conversion through AnyDoc. No renamed image has to exist in a registry. Use the deployment README for image builds, workspace setup and smoke checks. Developer profiles additionally need Git credentials and the configured Oduflow environment tooling.

The bridge authenticates to Odoo with a dedicated internal user in **OduPilot Bridge Service**. Grant that group through the technical user/group settings. It exposes service RPC methods that return deployment credentials, so assign it only to the bridge account. Administrator access alone does not satisfy this check. Installation does not reassign existing users' groups.

## Profiles and agents

Under Settings → **OduPilot**, configure profiles, agents and MCP servers. A profile selects the model, LiteLLM key, workspace type, session limit, agent availability and developer settings. Configure the common AI base URL in OduPilot settings. Assign a profile on the user's security page.

An agent supplies instructions, tool rules and MCP servers. Only agents available to the user's profile can start ordinary conversations. MCP-only agents are exposed through MCP rather than the chat selector. Optional payment reconciliation requires the relevant accounting and payment business modules.

For Odoo tools, enable **MCP Active** and assign an MCP profile to the user. Configure an MCP server with the session token placeholder in its headers. Each session receives a signed token bound to its owner and profile. Revocation and policy changes are checked on subsequent calls. Personal MCP API keys are independent; keys with an expiration date are rejected after that date.

Developer worktree profiles need the repository URL, base branch, GitHub token and environment configuration. Set the **Developers Profile** used by the developer menu and, optionally, the **Responsible Developer**. A request classified as development adds that administrator to the conversation and sends a persistent OduPilot notification.

## Dictation

Dictation uses the profile's LiteLLM credentials and the common AI base URL. Set the transcription model through the system parameter `odupilot.transcription_model`; the default is `whisper-1`. The browser needs a secure context and microphone permission. Limits are five minutes and 25 MiB per recording. Audio is not stored as an attachment. Transcription returns text for editing before the request is submitted.

## Connectivity and monitoring

The bridge polls `/odupilot/bridge/poll` over the ordinary Odoo HTTP endpoint. Only its service account can call it; callers cannot select arbitrary bus channels. Empty polls wait one second in the bridge. The durable XML-RPC command queue remains the source of truth. No Odoo 15 long-polling route is used. Configure the standard Odoo 17 WebSocket endpoint for browser Discuss events.

The OduMCP server polls `/odumcp/v1/events` with a short-lived event ticket and waits one second after an empty response. Requests observe only the ticket owner's private channel. Deploy the accompanying MCP server version together with this addon.

Use **Monitoring** for bridge/OpenCode health and recent runtime errors, and **Sessions**, **Commands** and the agent action log to inspect work. The bridge reconnects to the OpenCode event stream and backfills completed messages with duplicate suppression. It also reconciles sessions after reconnecting. Commands use ordered delivery and idempotency identifiers.

## Recovery and retention

Set the busy-session timeout, event retention and closed-session retention in OduPilot settings. A five-minute cron checks overdue requests. It queues an abort and can automatically retry once when there was no tool activity. Otherwise a participant must choose **Retry** or **Dismiss**. Late answers resolve outstanding recovery records and cancel unnecessary retries.

Closing a session revokes its token and queues workspace cleanup. Retention removes technical records according to policy while preserving Discuss channels and messages. Zero retention days means indefinite retention. The bridge needs to remain available to process cleanup commands.

## Validation

Run Odoo tests for `/odupilot,/odumcp`, the bridge unit tests in `addons/odupilot/deploy`, and the MCP server tests in `addons/odumcp/deploy/odumcp_server`. Browser tests use an isolated Odoo database. A live provider, external Git repository and developer environment require separately configured services; local fixtures do not validate their credentials.

## Odoo 17 compatibility

Use branch `17.0` for a fresh installation on Odoo 17. Install the module from `addons` together with its declared dependencies. This branch does not downgrade an existing Odoo database.
