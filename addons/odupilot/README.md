# OduPilot for Odoo 19

AI sessions in Discuss, questions about records, tool approvals and AI developer
workspaces. Ported from VelesAgro `ai_chat`; technical module name: `odupilot`.

Install from `addons` with `odumcp`. Install Python dependencies from
`.oduflow/requirements.txt` first. The AI runtime uses the bridge and OpenCode
stack in [deploy](deploy/README.md); provider credentials and profiles must be
configured before starting a conversation.

- [User guide](doc/user_guide.md)
- [Administrator guide](doc/admin_guide.md)
- [Technical specification](doc/tech_spec.md)

Odooist — OPL-1, as declared by the original module. This port does not migrate
an existing Odoo 15 database.
