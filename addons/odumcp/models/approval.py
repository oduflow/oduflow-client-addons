import hashlib
import json
import uuid

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .yaml_preview import json_to_yaml_html


class OduMcpApproval(models.Model):
    _name = "odumcp.approval"
    _description = "MCP Change Approval"
    _order = "create_date desc"
    _rec_name = "request_uid"

    request_uid = fields.Char(required=True, default=lambda self: str(uuid.uuid4()), readonly=True, index=True)
    user_id = fields.Many2one(
        "res.users",
        required=True,
        ondelete="restrict",
        readonly=True,
        index=True,
    )
    profile_id = fields.Many2one(
        "odumcp.profile",
        required=True,
        ondelete="restrict",
        readonly=True,
        index=True,
    )
    action = fields.Selection(
        [
            ("record.create", "Create Records"),
            ("record.update", "Update Records"),
            ("record.delete", "Delete Records"),
            ("message.post", "Post Message"),
            ("activity.schedule", "Schedule Activity"),
            ("activity.update", "Update Activity"),
            ("activity.done", "Close Activity"),
            ("attachment.create", "Create Attachment"),
            ("method.call", "Call Allowed Method"),
        ],
        required=True,
        readonly=True,
        index=True,
    )
    model_name = fields.Char(required=True, readonly=True, index=True)
    payload_json = fields.Text(required=True, readonly=True, groups="odumcp.group_mcp_manager")
    payload_hash = fields.Char(required=True, readonly=True, index=True)
    idempotency_key = fields.Char(required=True, readonly=True)
    request_ref = fields.Char(
        string="Request",
        readonly=True,
        index=True,
        help="Identifier of the MCP request that produced this plan. "
             "Plans created by one request share it, so they can be approved together.",
    )
    request_key = fields.Char(
        string="Request Key",
        readonly=True,
        index=True,
        help="Internal grouping key: the batch key sent by the client, or an automatic one.",
    )
    risk_level = fields.Selection(
        [("low", "Low"), ("medium", "Medium"), ("high", "High"), ("critical", "Critical")],
        required=True,
        readonly=True,
        index=True,
    )
    summary = fields.Char(required=True, readonly=True)
    target_count = fields.Integer(readonly=True)
    diff_json = fields.Text(readonly=True)
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("executing", "Executing"),
            ("executed", "Executed"),
            ("expired", "Expired"),
            ("failed", "Failed"),
        ],
        required=True,
        default="pending",
        readonly=True,
        index=True,
    )
    expires_at = fields.Datetime(required=True, readonly=True, index=True)
    approved_by = fields.Many2one("res.users", readonly=True)
    approved_at = fields.Datetime(readonly=True)
    rejected_by = fields.Many2one("res.users", readonly=True)
    rejected_at = fields.Datetime(readonly=True)
    executed_at = fields.Datetime(readonly=True)
    result_json = fields.Text(readonly=True)
    error_message = fields.Text(readonly=True)
    diff_yaml = fields.Html(
        string="Redacted Diff",
        compute="_compute_snapshot_yaml",
        sanitize=False,
    )
    result_yaml = fields.Html(
        string="Result",
        compute="_compute_snapshot_yaml",
        sanitize=False,
    )
    payload_yaml = fields.Html(
        string="Payload",
        compute="_compute_payload_yaml",
        sanitize=False,
        groups="odumcp.group_mcp_manager",
    )

    _sql_constraints = [('request_uid_unique', 'UNIQUE(request_uid)', 'The approval request identifier must be unique.'), ('idempotency_unique', 'UNIQUE(user_id, idempotency_key)', 'The idempotency key has already been used by this MCP user.')]

    @api.depends("diff_json", "result_json")
    def _compute_snapshot_yaml(self):
        for approval in self:
            approval.diff_yaml = json_to_yaml_html(approval.diff_json)
            approval.result_yaml = json_to_yaml_html(approval.result_json)

    @api.depends("payload_json")
    def _compute_payload_yaml(self):
        for approval in self:
            approval.payload_yaml = json_to_yaml_html(approval.payload_json)

    @api.model
    def _request_window_minutes(self):
        # Окно склейки планов, пришедших без явного ключа запроса.
        value = self.env["ir.config_parameter"].sudo().get_param(
            "odumcp.request_window_minutes", "10"
        )
        try:
            minutes = int(value)
        except (TypeError, ValueError):
            minutes = 10
        return max(0, minutes)

    @api.model
    def _next_request_ref(self):
        reference = self.env["ir.sequence"].sudo().next_by_code("odumcp.request")
        return reference or "MCP/%s" % uuid.uuid4().hex[:10].upper()

    @api.model
    def _assign_request(self, user, profile, batch_key=None):
        """Вернуть (ключ, метку) запроса, к которому относится новый план.

        Клиент может прислать batch_key и сам склеить планы одного задания.
        Без него планы одного пользователя и профиля объединяются, пока между
        ними проходит меньше настроенного окна.
        """
        Approval = self.sudo()
        existing = Approval.browse()
        if batch_key:
            key = "key:%s" % batch_key
            existing = Approval.search(
                [("user_id", "=", user.id), ("request_key", "=", key)],
                order="create_date desc, id desc",
                limit=1,
            )
        else:
            key = "auto:%s" % uuid.uuid4()
            window = self._request_window_minutes()
            if window:
                cutoff = fields.Datetime.subtract(fields.Datetime.now(), minutes=window)
                existing = Approval.search(
                    [
                        ("user_id", "=", user.id),
                        ("profile_id", "=", profile.id),
                        ("request_key", "=like", "auto:%"),
                        ("create_date", ">=", cutoff),
                    ],
                    order="create_date desc, id desc",
                    limit=1,
                )
        if existing and existing.request_key and existing.request_ref:
            return existing.request_key, existing.request_ref
        return key, self._next_request_ref()

    def _lock_for_update(self):
        self.ensure_one()
        self.env.cr.execute(
            "SELECT id FROM odumcp_approval WHERE id = %s FOR UPDATE",
            [self.id],
        )
        self.invalidate_recordset()
        return self

    def action_approve(self):
        if not self.env.user._has_group("odumcp.group_mcp_manager"):
            raise AccessError(_("Only MCP managers can approve change plans."))
        for approval in self:
            approval._lock_for_update()
            if approval.state != "pending":
                raise UserError(_("Only pending plans can be approved."))
            if approval.expires_at <= fields.Datetime.now():
                approval._system_write({"state": "expired"})
                raise UserError(_("This change plan has expired."))
            approval._system_write(
                {
                    "state": "approved",
                    "approved_by": self.env.user.id,
                    "approved_at": fields.Datetime.now(),
                }
            )

    def action_reject(self):
        if not self.env.user._has_group("odumcp.group_mcp_manager"):
            raise AccessError(_("Only MCP managers can reject change plans."))
        for approval in self:
            approval._lock_for_update()
            if approval.state not in {"pending", "approved"}:
                raise UserError(_("Only pending or approved plans can be rejected."))
            approval._system_write(
                {
                    "state": "rejected",
                    "rejected_by": self.env.user.id,
                    "rejected_at": fields.Datetime.now(),
                }
            )

    def action_mass_approve(self):
        return self._open_mass_wizard("approve")

    def action_mass_reject(self):
        return self._open_mass_wizard("reject")

    def action_mass_delete_expired(self):
        return self._open_mass_wizard("delete")

    def _open_mass_wizard(self, mode):
        # Кнопки в шапке списка в Odoo 15 не поддерживают confirm=, поэтому
        # подтверждение групповой операции идёт через транзиентный визард.
        if not self.env.user._has_group("odumcp.group_mcp_manager"):
            raise AccessError(_("Only MCP managers can approve or reject change plans."))
        now = fields.Datetime.now()
        if mode == "approve":
            eligible = self.filtered(
                lambda approval: approval.state == "pending" and approval.expires_at > now
            )
        elif mode == "reject":
            eligible = self.filtered(
                lambda approval: approval.state in ("pending", "approved")
            )
        else:
            eligible = self.filtered(lambda approval: approval.state == "expired")
        if not eligible:
            raise UserError(_("None of the selected change plans can be processed by this action."))
        titles = {
            "approve": _("Approve Change Plans"),
            "reject": _("Reject Change Plans"),
            "delete": _("Delete Expired Change Plans"),
        }
        return {
            "type": "ir.actions.act_window",
            "name": titles[mode],
            "res_model": "odumcp.approval.mass",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_mode": mode,
                "default_approval_ids": [(6, 0, eligible.ids)],
                "default_skipped_count": len(self) - len(eligible),
            },
        }

    def _mass_moderate(self, mode):
        # Терпимая пакетная обработка: состояние могло измениться между
        # открытием визарда и подтверждением, неподходящие записи пропускаем.
        processed = self.browse()
        for approval in self:
            approval._lock_for_update()
            if mode == "approve":
                if approval.state != "pending":
                    continue
                if approval.expires_at <= fields.Datetime.now():
                    approval._system_write({"state": "expired"})
                    continue
                approval._system_write(
                    {
                        "state": "approved",
                        "approved_by": self.env.user.id,
                        "approved_at": fields.Datetime.now(),
                    }
                )
            elif mode == "reject":
                if approval.state not in ("pending", "approved"):
                    continue
                approval._system_write(
                    {
                        "state": "rejected",
                        "rejected_by": self.env.user.id,
                        "rejected_at": fields.Datetime.now(),
                    }
                )
            else:
                # Удаление доступно только для истёкших планов; обходим защиту
                # unlink тем же путём, что и retention-очистка.
                if approval.state != "expired":
                    continue
                approval.sudo().with_context(mcp_retention_cleanup=True).unlink()
                continue
            processed |= approval
        return processed

    def _system_write(self, values):
        result = super(OduMcpApproval, self.with_context(mcp_approval_system_write=True)).write(
            values
        )
        if "state" in values:
            for approval in self:
                approval.user_id._publish_mcp_resource_update(
                    f"odoo://approval/{approval.request_uid}"
                )
        return result

    def write(self, values):
        if self.env.context.get("mcp_approval_system_write"):
            return super().write(values)
        protected = set(self._fields) - {"display_name"}
        if protected & set(values):
            raise AccessError(_("MCP change plans are immutable. Use the approval actions."))
        return super().write(values)

    def unlink(self):
        if not self.env.context.get("mcp_retention_cleanup") or not self.env.is_system():
            raise AccessError(_("MCP change plans can only be removed by retention cleanup."))
        return super().unlink()

    @classmethod
    def _canonical_payload(cls, payload):
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def _payload_digest(cls, payload_json):
        return hashlib.sha256(payload_json.encode()).hexdigest()

    @classmethod
    def _json_result(cls, value):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def _public_dict(self):
        self.ensure_one()
        result = json.loads(self.result_json) if self.result_json else None
        diff = json.loads(self.diff_json) if self.diff_json else []
        return {
            "approval_id": self.request_uid,
            "request": self.request_ref or None,
            "state": self.state,
            "action": self.action,
            "model": self.model_name,
            "risk_level": self.risk_level,
            "summary": self.summary,
            "target_count": self.target_count,
            "diff": diff,
            "expires_at": fields.Datetime.to_string(self.expires_at),
            "result": result,
            "error": self.error_message or None,
            "next_step": (
                "Approve this plan in Odoo, then call odoo_execute_approved_change."
                if self.state == "pending"
                else None
            ),
        }

    @api.autovacuum
    def _gc_approvals(self):
        now = fields.Datetime.now()
        expired = self.sudo().search(
            [("state", "in", ["pending", "approved"]), ("expires_at", "<", now)],
            limit=5000,
        )
        expired._system_write({"state": "expired"})
        retention_days = int(
            self.env["ir.config_parameter"].sudo().get_param(
                "odumcp.approval_retention_days", "30"
            )
        )
        cutoff = fields.Datetime.subtract(now, days=max(1, retention_days))
        old = self.sudo().search(
            [
                ("state", "in", ["executed", "rejected", "expired", "failed"]),
                ("create_date", "<", cutoff),
            ],
            limit=5000,
        )
        old.with_context(mcp_retention_cleanup=True).unlink()
