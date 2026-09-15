# OduPilot User Guide

## Start a conversation

Open Discuss → **AI Agent Chat**, select an available agent and click **Start Chat**. Your administrator must first assign an OduPilot profile with a model and credentials. Each conversation has its own history and workspace. The status above the messages shows initialization, readiness, work, approval, errors or closure.

Conversations appear under **OduPilot** in the Discuss sidebar. The section remembers whether it is expanded. A new title contains the agent name and your initials. The first answer can replace the agent name with a short topic; a name you set yourself takes priority. Edit the title in the conversation header.

## Ask about a record

Click **Ask AI** in the chatter of a saved record, enter a question and confirm. The question appears immediately as an internal note. The answer and its status update that same note. If the note was deleted, the answer is posted as a new note. The form keeps unsaved edits.

Questions use a hidden service conversation and a fresh AI context for each question. They do not consume the quota for ordinary chats. The service cannot ask for interactive tool permissions. You need the normal access rights to the record; AI access does not grant additional Odoo permissions.

## Messages and files

Type a message and send it. In a conversation with only you and the bot, messages go to AI automatically. In a conversation with several internal users, mention the AI bot to address it. Send `/abort` through the same routing to stop a request.

Attach files through the normal Discuss composer. The bridge copies allowed attachments into the session workspace and converts supported documents locally. Unsupported formats remain subject to the configured limits. The live answer shows text and collapsible tool or reasoning steps; the saved answer supports Markdown, tables and links. Generated HTML is sanitized.

## Decisions and recovery

A permission card describes the operation and requested access. **Allow once**, **Always** or **Reject** sends your decision to the bridge. The card shows who answered and its delivery status. Decisions are recorded in the audit history.

After an interrupted request, a recovery card can offer **Retry** or **Dismiss**. Read the tool activity notice before retrying: an external operation may already have happened. A request interrupted before any tool activity can be retried automatically once.

## Other participants and notifications

The owner or an administrator can invite active internal users. Guests cannot join. Only administrators can join developer worktree conversations. The owner and AI bot are protected from removal while a conversation is active. Leaving your own conversation closes its AI session; another participant can leave without closing it.

An answer or decision request can show a persistent notification when its conversation is not displayed. **Open conversation** opens the relevant thread. Service steps do not raise these notifications. Developer conversations open in Discuss.

## AI Developer

Administrators can open **AI Developer** from the developer tools menu. Enter the request; **Dictate** is available when the browser permits microphone recording in a secure context. Stop recording to receive editable transcription. Recording is limited to five minutes. Audio is sent for transcription without being saved as an Odoo attachment.

The request includes the current screen context. The configured developer profile creates an isolated Git worktree. AI can first classify the issue as a settings question or a code change; a code change can be assigned to the responsible developer. Environment and publication links appear when the connected services provide them. These operations require the corresponding profile and external infrastructure.

## Access and troubleshooting

For Odoo tools, your administrator enables **MCP Active** and selects an MCP profile. OduPilot creates a signed token for each session; it does not need a personal permanent API key. Tool calls follow your Odoo access rights and MCP policies.

If a session stays in initialization, ask an administrator to check the bridge. For errors, review the status and recovery card. Closing a session revokes its AI access and queues workspace cleanup while preserving the Discuss history. Optional agents, such as payment reconciliation, require their corresponding business modules and configured policies.
