import json
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


MODEL_NAME_RE = re.compile(r"^[a-zA-Z0-9_.]+$")
METHOD_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")
SENSITIVE_FIELD_NAME_RE = re.compile(
    r"(password|passwd|(?:^|_)pass(?:$|_)|secret|token|api.?key|private|credential"
    r"|authorization)",
    re.IGNORECASE,
)
# Never reachable through MCP: they hold the credentials the connector runs on
# or the audit trail that records what it did. Neither an explicit Model Policy
# nor the profile-wide fallback can name them.
BLOCKED_POLICY_MODELS = {
    "ir.config_parameter",
    "res.users.apikeys",
    "odumcp.profile",
    "odumcp.model.policy",
    "odumcp.method.policy",
    "odumcp.approval",
    "odumcp.audit.log",
    "odumcp.event.ticket",
}
# Readable through the profile-wide fallback, but never writable: reading a
# security setting only tells the connector what it is already subject to,
# while writing one enables code execution or privilege escalation past this
# policy layer. An explicit Model Policy with its field allowlists can still
# open them for writing deliberately.
GLOBAL_ACCESS_READONLY_MODELS = {
    "base.automation",
    "ir.actions.server",
    "ir.cron",
    "ir.mail_server",
    "ir.model.access",
    "ir.rule",
    "ir.ui.view",
    "res.groups",
    "res.users",
}
ACTIVITY_MODEL = "mail.activity"
# Активность читается целиком, но правится только по делу: res_model/res_id
# сменили бы запись-хозяина в обход её write-политики.
ACTIVITY_READ_FIELDS = {
    "id",
    "display_name",
    "res_model",
    "res_model_id",
    "res_id",
    "res_name",
    "activity_type_id",
    "activity_category",
    "summary",
    "note",
    "date_deadline",
    "state",
    "user_id",
    "create_uid",
    "create_date",
    "write_date",
    "automated",
}
ACTIVITY_WRITE_FIELDS = {
    "activity_type_id",
    "summary",
    "note",
    "date_deadline",
    "user_id",
}
WRITE_MAGIC_FIELDS = {
    "id",
    "create_uid",
    "create_date",
    "write_uid",
    "write_date",
    "__last_update",
    "display_name",
}


class GlobalModelPolicy:
    """Policy adapter for models covered by a profile-wide access mode."""

    def __init__(self, profile, model_id):
        self.profile_id = profile
        self.model_id = model_id
        self.max_records = 0
        self.allow_binary_read = False
        self.allow_binary_write = False
        writable = model_id.model not in GLOBAL_ACCESS_READONLY_MODELS
        self.allow_read = profile.default_model_access in {"read", "write"}
        self.allow_aggregate = self.allow_read and profile.allow_aggregate
        self.allow_create = profile.allow_global_create and writable
        self.allow_write = profile.default_model_access == "write" and writable
        self.allow_unlink = profile.allow_global_unlink and writable

    def _allows(self, operation):
        return bool(
            {
                "read": self.allow_read,
                "aggregate": self.allow_aggregate,
                "create": self.allow_create,
                "write": self.allow_write,
                "unlink": self.allow_unlink,
            }.get(operation, False)
        )

    def _operation_names(self):
        return [
            operation
            for operation in ("read", "create", "write", "unlink", "aggregate")
            if self._allows(operation)
        ]

    def _record_limit(self):
        return self.profile_id.max_records_per_call

    def _forced_domain(self):
        return []

    def _allowed_field_names(self, operation, model):
        descriptions = model.fields_get(
            attributes=[
                "type",
                "readonly",
                "required",
                "string",
                "relation",
                "selection",
                "help",
            ]
        )
        names = {
            name
            for name, description in descriptions.items()
            if not SENSITIVE_FIELD_NAME_RE.search(name)
            and description.get("type") != "binary"
        }
        if operation in {"create", "write"}:
            names = {
                name
                for name in names
                if name not in WRITE_MAGIC_FIELDS and not descriptions[name].get("readonly")
            }
        return names


class ActivityModelPolicy:
    """Policy adapter for the connector user's own activities.

    Mirrors Odoo's own `mail_activity_rule_user`: an activity belongs to the
    user who created it or to the user it is assigned to. Deletion is never
    offered — an activity is closed through `activity.done`, which leaves the
    feedback message in the record's chatter.
    """

    def __init__(self, profile, model_id, user_id):
        self.profile_id = profile
        self.model_id = model_id
        self.user_id = user_id
        self.max_records = 0
        self.allow_binary_read = False
        self.allow_binary_write = False
        self.allow_read = True
        self.allow_aggregate = profile.allow_aggregate
        # Создание идёт через activity.schedule: оно проверяет право записи на
        # модель-хозяина, а прямой create на mail.activity его обошёл бы.
        self.allow_create = False
        self.allow_write = True
        self.allow_unlink = False

    def _allows(self, operation):
        return bool(
            {
                "read": self.allow_read,
                "aggregate": self.allow_aggregate,
                "create": self.allow_create,
                "write": self.allow_write,
                "unlink": self.allow_unlink,
            }.get(operation, False)
        )

    def _operation_names(self):
        return [
            operation
            for operation in ("read", "create", "write", "unlink", "aggregate")
            if self._allows(operation)
        ]

    def _record_limit(self):
        return self.profile_id.max_records_per_call

    def _forced_domain(self):
        return fields.Domain.OR(
            [
                [("create_uid", "=", self.user_id)],
                [("user_id", "=", self.user_id)],
            ]
        )

    def _allowed_field_names(self, operation, model):
        names = (
            ACTIVITY_WRITE_FIELDS
            if operation in {"create", "write"}
            else ACTIVITY_READ_FIELDS
        )
        return {name for name in names if name in model._fields}


class OduMcpProfile(models.Model):
    _name = "odumcp.profile"
    _description = "MCP Security Profile"
    _order = "name"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    active = fields.Boolean(default=True)
    description = fields.Text(translate=True)
    company_ids = fields.Many2many(
        "res.company",
        "odumcp_profile_company_rel",
        "profile_id",
        "company_id",
        string="Allowed Companies",
        help="Empty means all companies available to the connector user.",
    )
    max_records_per_call = fields.Integer(default=100, required=True)
    max_batch_size = fields.Integer(default=20, required=True)
    rate_limit_per_minute = fields.Integer(default=60, required=True)
    daily_quota = fields.Integer(
        default=0,
        help="Maximum requests per UTC day. Zero disables the separate daily quota.",
    )
    approval_ttl_minutes = fields.Integer(
        string="Approval TTL Minutes",
        default=30,
        required=True,
    )
    auto_approve_low_risk = fields.Boolean(
        default=False,
        help="Only low-risk collaboration actions may be auto-approved.",
    )
    allow_partial_field_reads = fields.Boolean(
        string="Partial Field Reads",
        help=(
            "Return the readable part of a read request instead of refusing it, and "
            "report the skipped field names in the response. Only plain field lists "
            "are trimmed: a denied field in a domain or in the sort order, and any "
            "write, still fail. Leave off when a client must not silently work with "
            "incomplete records."
        ),
    )
    allow_schema = fields.Boolean(default=True)
    allow_aggregate = fields.Boolean(default=True)
    allow_reports = fields.Boolean()
    allow_attachments = fields.Boolean()
    allow_chatter = fields.Boolean()
    allow_activities = fields.Boolean(
        help=(
            "Let the connector schedule, update and close the activities it owns: "
            "the ones it created and the ones assigned to its Odoo user. "
            "Activities are never deleted outright."
        ),
    )
    default_model_access = fields.Selection(
        [
            ("explicit", "Explicit policies only"),
            ("read", "Read any accessible model"),
            ("write", "Read and update any accessible model"),
        ],
        required=True,
        default="explicit",
        string="Default Model Access",
        help=(
            "Fallback for models without an explicit Model Policy. Odoo access rights, "
            "record rules, field security, and the MCP safety denylist still apply."
        ),
    )
    allow_global_create = fields.Boolean(
        string="Create on Any Accessible Model",
        help=(
            "Allow record creation on models without an explicit Model Policy when the "
            "assigned Odoo user has create access. Changes still require approval."
        ),
    )
    allow_global_unlink = fields.Boolean(
        string="Delete from Any Accessible Model",
        help=(
            "Allow record deletion on models without an explicit Model Policy when the "
            "assigned Odoo user has delete access. Deletes still require approval."
        ),
    )
    policy_ids = fields.One2many("odumcp.model.policy", "profile_id")
    method_policy_ids = fields.One2many("odumcp.method.policy", "profile_id")
    user_ids = fields.One2many("res.users", "mcp_profile_id", string="Users")
    assigned_user_ids = fields.Many2many(
        "res.users",
        string="Assigned Users",
        compute="_compute_assigned_user_ids",
        inverse="_inverse_assigned_user_ids",
    )

    _code_unique = models.Constraint('UNIQUE(code)', 'The MCP profile code must be unique.')
    _positive_limits = models.Constraint('CHECK(max_records_per_call > 0 AND max_records_per_call <= 1000 AND max_batch_size > 0 AND max_batch_size <= 100 AND rate_limit_per_minute > 0 AND rate_limit_per_minute <= 10000 AND daily_quota >= 0 AND approval_ttl_minutes > 0 AND approval_ttl_minutes <= 10080)', 'MCP limits are outside their allowed range.')

    @api.constrains("code")
    def _check_code(self):
        for profile in self:
            if not MODEL_NAME_RE.fullmatch(profile.code or ""):
                raise ValidationError(
                    _("Profile codes may contain only letters, numbers, dots, and underscores.")
                )

    @api.depends("user_ids")
    def _compute_assigned_user_ids(self):
        for profile in self:
            profile.assigned_user_ids = profile.user_ids

    def _inverse_assigned_user_ids(self):
        for profile in self:
            current_users = profile.user_ids
            selected_users = profile.assigned_user_ids
            # Профиль и галочка снимаются вместе: доступ без профиля запрещён
            # констрейнтом, а ключ пользователя живёт ровно до отзыва доступа.
            (current_users - selected_users).write({
                "mcp_profile_id": False,
                "mcp_active": False,
            })
            (selected_users - current_users).write({"mcp_profile_id": profile.id})

    def _get_policy(self, model_name, operation, *, required=True, user=None):
        self.ensure_one()
        if not MODEL_NAME_RE.fullmatch(model_name or ""):
            raise ValidationError(_("Invalid model name."))
        policy = self.policy_ids.filtered(
            lambda item: item.active and item.model_id.model == model_name
        )[:1]
        if policy:
            allowed = policy._allows(operation)
        else:
            model_id = self.env["ir.model"].sudo()._get(model_name)
            if not model_id or model_id.transient:
                policy = self.env["odumcp.model.policy"]
            elif self._has_activity_access(model_name, user):
                policy = ActivityModelPolicy(self, model_id, user.id)
            elif model_name not in BLOCKED_POLICY_MODELS:
                policy = GlobalModelPolicy(self, model_id)
            else:
                policy = self.env["odumcp.model.policy"]
            allowed = bool(policy and policy._allows(operation))
        if required and not allowed:
            raise ValidationError(
                _("Operation %(operation)s is not allowed on %(model)s.", operation=operation, model=model_name)
            )
        return policy if allowed else self.env["odumcp.model.policy"]

    def _has_activity_access(self, model_name, user):
        """Своя политика активностей нужна только при включённом флаге."""
        self.ensure_one()
        return bool(model_name == ACTIVITY_MODEL and self.allow_activities and user)

    def _has_global_model_access(self):
        self.ensure_one()
        return bool(
            self.default_model_access != "explicit"
            or self.allow_global_create
            or self.allow_global_unlink
        )

    def _allowed_company_ids(self, user):
        self.ensure_one()
        user_companies = user.company_ids
        companies = user_companies & self.company_ids if self.company_ids else user_companies
        if not companies:
            raise ValidationError(_("The MCP profile and connector user have no company in common."))
        return companies.ids

    def _capabilities(self):
        self.ensure_one()
        return {
            "profile": self.code,
            "limits": {
                "max_records_per_call": self.max_records_per_call,
                "max_batch_size": self.max_batch_size,
                "rate_limit_per_minute": self.rate_limit_per_minute,
                "daily_quota": self.daily_quota,
            },
            "features": {
                "schema": self.allow_schema,
                "aggregate": self.allow_aggregate,
                "reports": self.allow_reports,
                "attachments": self.allow_attachments,
                "chatter": self.allow_chatter,
                "activities": self.allow_activities,
                "activity_actions": (
                    ["activity.schedule", "activity.update", "activity.done"]
                    if self.allow_activities
                    else []
                ),
                "auto_approve_low_risk": self.auto_approve_low_risk,
                "partial_field_reads": self.allow_partial_field_reads,
                "default_model_access": self.default_model_access,
                "create_on_any_model": self.allow_global_create,
                "delete_from_any_model": self.allow_global_unlink,
            },
            "models": [
                {
                    "model": policy.model_id.model,
                    "name": policy.model_id.name,
                    "operations": policy._operation_names(),
                }
                for policy in self.policy_ids.filtered("active").sorted(
                    key=lambda item: item.model_id.model
                )
            ],
        }


class OduMcpModelPolicy(models.Model):
    _name = "odumcp.model.policy"
    _description = "MCP Model Policy"
    _order = "profile_id, model_id"

    active = fields.Boolean(default=True)
    profile_id = fields.Many2one(
        "odumcp.profile",
        required=True,
        ondelete="cascade",
        index=True,
    )
    model_id = fields.Many2one(
        "ir.model",
        required=True,
        ondelete="cascade",
        domain=[("transient", "=", False)],
    )
    model_name = fields.Char(
        related="model_id.model",
        string="Technical Model Name",
        store=True,
        index=True,
    )
    allow_read = fields.Boolean(default=True)
    allow_create = fields.Boolean()
    allow_write = fields.Boolean()
    allow_unlink = fields.Boolean()
    allow_aggregate = fields.Boolean(default=True)
    allow_binary_read = fields.Boolean()
    allow_binary_write = fields.Boolean()
    max_records = fields.Integer(
        default=0,
        help="Zero inherits the profile limit.",
    )
    forced_domain_json = fields.Text(
        default="[]",
        required=True,
        help="JSON Odoo domain that is always AND-ed with the client domain.",
    )
    # Домен держим на самом поле, а не только во вьюхе: политика редактируется в
    # диалоге поверх o2m, и датапоинт записи остаётся с viewType="list". Диалог
    # "Search More" читает домен без указания viewType, не находит его в описании
    # tree-вьюхи (там этих полей нет) и откатывается на домен самого поля. Без
    # него окно показывало все поля всех моделей Odoo.
    _FIELD_POLICY_DOMAIN = "[('model_id', '=', model_id)]"

    read_field_ids = fields.Many2many(
        "ir.model.fields",
        "odumcp_policy_read_field_rel",
        "policy_id",
        "field_id",
        string="Readable Fields",
        domain=_FIELD_POLICY_DOMAIN,
    )
    write_field_ids = fields.Many2many(
        "ir.model.fields",
        "odumcp_policy_write_field_rel",
        "policy_id",
        "field_id",
        string="Writable Fields",
        domain=_FIELD_POLICY_DOMAIN,
    )

    _profile_model_unique = models.Constraint('UNIQUE(profile_id, model_id)', 'A model can occur only once in an MCP profile.')
    _max_records_range = models.Constraint('CHECK(max_records >= 0 AND max_records <= 1000)', 'The per-model record limit must be between 0 and 1000.')

    @api.constrains("model_id")
    def _check_model_kind(self):
        for policy in self:
            if policy.model_id.transient:
                raise ValidationError(_("Transient models cannot be exposed through MCP."))
            if policy.model_id.model in BLOCKED_POLICY_MODELS:
                raise ValidationError(_("This security-sensitive model cannot be exposed through MCP."))

    @api.constrains("read_field_ids", "write_field_ids", "model_id")
    def _check_field_models(self):
        for policy in self:
            invalid = (policy.read_field_ids | policy.write_field_ids).filtered(
                lambda field: field.model_id != policy.model_id
            )
            if invalid:
                raise ValidationError(_("Every selected field must belong to the policy model."))

    @api.constrains("forced_domain_json")
    def _check_forced_domain_json(self):
        for policy in self:
            try:
                value = json.loads(policy.forced_domain_json or "[]")
                if not isinstance(value, list):
                    raise ValueError
                list(fields.Domain(value))
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValidationError(_("Forced domain must be a valid JSON Odoo domain.")) from exc

    def _forced_domain(self):
        self.ensure_one()
        return list(fields.Domain(json.loads(self.forced_domain_json or "[]")))

    def _allows(self, operation):
        self.ensure_one()
        mapping = {
            "read": self.allow_read,
            "create": self.allow_create,
            "write": self.allow_write,
            "unlink": self.allow_unlink,
            "aggregate": self.allow_aggregate and self.profile_id.allow_aggregate,
        }
        return bool(mapping.get(operation, False))

    def _operation_names(self):
        self.ensure_one()
        return [
            operation
            for operation in ("read", "create", "write", "unlink", "aggregate")
            if self._allows(operation)
        ]

    def _record_limit(self):
        self.ensure_one()
        return min(
            self.max_records or self.profile_id.max_records_per_call,
            self.profile_id.max_records_per_call,
        )

    def _allowed_field_names(self, operation, model):
        self.ensure_one()
        configured = (
            self.write_field_ids.mapped("name")
            if operation in {"create", "write"}
            else self.read_field_ids.mapped("name")
        )
        names = set(configured)
        if operation == "read":
            names.update({"id", "display_name"})
        fields_description = model.fields_get(
            allfields=list(names),
            attributes=["type", "readonly", "required", "string", "relation", "selection", "help"],
        )
        names &= set(fields_description)
        if not self.allow_binary_read and operation == "read":
            names = {
                name
                for name in names
                if fields_description.get(name, {}).get("type") != "binary"
            }
        if not self.allow_binary_write and operation in {"create", "write"}:
            names = {
                name
                for name in names
                if fields_description.get(name, {}).get("type") != "binary"
            }
        return names


class OduMcpMethodPolicy(models.Model):
    _name = "odumcp.method.policy"
    _description = "MCP Method Policy"
    _order = "profile_id, model_id, method_name"

    active = fields.Boolean(default=True)
    profile_id = fields.Many2one(
        "odumcp.profile",
        required=True,
        ondelete="cascade",
        index=True,
    )
    model_id = fields.Many2one("ir.model", required=True, ondelete="cascade")
    method_name = fields.Char(required=True)
    risk_level = fields.Selection(
        [
            ("low", "Low"),
            ("medium", "Medium"),
            ("high", "High"),
            ("critical", "Critical"),
        ],
        required=True,
        default="high",
    )
    requires_approval = fields.Boolean(
        string="Require Human Approval",
        default=True,
        help=(
            "When disabled, a valid method call plan is approved automatically. "
            "It still uses idempotent execution and is fully audited."
        ),
    )
    max_record_count = fields.Integer(default=1, required=True)
    allow_model_method = fields.Boolean(
        default=False,
        help="Allow calling the method without record IDs.",
    )
    allow_positional_arguments = fields.Boolean(
        default=False,
        help="Allow positional arguments after the recordset.",
    )
    allowed_keyword_arguments = fields.Char(
        help="Comma-separated exact keyword argument names. Empty forbids kwargs.",
    )
    max_argument_bytes = fields.Integer(
        default=8192,
        required=True,
        help="Maximum canonical JSON size of args and kwargs.",
    )

    _profile_model_method_unique = models.Constraint('UNIQUE(profile_id, model_id, method_name)', 'A method can occur only once per model and MCP profile.')
    _positive_max_record_count = models.Constraint('CHECK(max_record_count > 0 AND max_record_count <= 100 AND max_argument_bytes >= 256 AND max_argument_bytes <= 65536)', 'Method record or argument limits are outside their allowed range.')

    @api.constrains("method_name")
    def _check_method_name(self):
        for policy in self:
            if (
                not METHOD_NAME_RE.fullmatch(policy.method_name or "")
                or policy.method_name.startswith("_")
            ):
                raise ValidationError(_("Only explicit public method names may be allowed."))

    @api.constrains("allowed_keyword_arguments")
    def _check_allowed_keyword_arguments(self):
        for policy in self:
            invalid = [
                name
                for name in policy._allowed_keyword_names()
                if not METHOD_NAME_RE.fullmatch(name)
            ]
            if invalid:
                raise ValidationError(
                    _("Allowed keyword arguments must be valid Python identifiers.")
                )

    def _allowed_keyword_names(self):
        self.ensure_one()
        return {
            name.strip()
            for name in (self.allowed_keyword_arguments or "").split(",")
            if name.strip()
        }
