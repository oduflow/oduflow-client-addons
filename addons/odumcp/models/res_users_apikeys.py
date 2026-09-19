from odoo import models, api, fields
from odoo.addons.base.models.res_users import INDEX_SIZE, KEY_CRYPT_CONTEXT


class ResUsersApikeysDescription(models.TransientModel):
    _inherit = "res.users.apikeys.description"

    scope_mode = fields.Selection(
        [
            ("mcp", "MCP only"),
            ("global", "All APIs"),
        ],
        required=True,
        default="mcp",
        string="Access",
        help=(
            "MCP-only keys can authenticate only to the MCP control API. "
            "All APIs creates a standard unrestricted Odoo API key."
        ),
    )

    def make_key(self):
        context = dict(self.env.context)
        if self.scope_mode == "mcp":
            context["odumcp_api_key_scope"] = "mcp"
        return super(ResUsersApikeysDescription, self.with_context(context)).make_key()


class ResUsersApikeys(models.Model):
    _inherit = "res.users.apikeys"

    expiration_date = fields.Datetime("Expiration Date", readonly=True)

    def init(self):
        super().init()
        # Odoo 16/17 create this table manually because its key column is secret.
        self.env.cr.execute("ALTER TABLE res_users_apikeys ADD COLUMN IF NOT EXISTS expiration_date timestamp without time zone")

    @api.model
    def _find_for_token(self, user, key):
        """Вернуть конкретный API key пользователя без изменения его scope."""
        self.env.cr.execute(
            """
            SELECT id, key
              FROM res_users_apikeys
             WHERE user_id = %s
               AND index = %s
               AND (expiration_date IS NULL OR expiration_date >= now() at time zone 'utc')
            """,
            [user.id, key[:INDEX_SIZE]],
        )
        for record_id, stored_key in self.env.cr.fetchall():
            if KEY_CRYPT_CONTEXT.verify(key, stored_key):
                return self.sudo().browse(record_id)
        return self.browse()

    @api.model
    def _check_mcp_credentials(self, key):
        """Authenticate only an exact MCP-scoped key, excluding global keys."""
        if not isinstance(key, str) or not (INDEX_SIZE <= len(key) <= 512):
            return False
        self.env.cr.execute(
            """
            SELECT api_key.user_id, api_key.key
              FROM res_users_apikeys AS api_key
              JOIN res_users AS users ON users.id = api_key.user_id
             WHERE users.active
               AND api_key.scope = 'mcp'
               AND (api_key.expiration_date IS NULL OR api_key.expiration_date >= now() at time zone 'utc')
               AND api_key.index = %s
            """,
            [key[:INDEX_SIZE]],
        )
        for user_id, stored_key in self.env.cr.fetchall():
            if KEY_CRYPT_CONTEXT.verify(key, stored_key):
                return user_id
        return False

    def _generate(self, scope, name, expiration_date=None):
        scope = scope or self.env.context.get("odumcp_api_key_scope")
        key = super()._generate(scope, name)
        if expiration_date:
            self.env.cr.execute(
                "UPDATE res_users_apikeys SET expiration_date = %s WHERE user_id = %s AND index = %s",
                [expiration_date, self.env.uid, key[:INDEX_SIZE]],
            )
        return key

    def _check_credentials(self, *, scope, key):
        user_id = super()._check_credentials(scope=scope, key=key)
        if user_id and self._find_for_token(self.env['res.users'].browse(user_id), key):
            return user_id
        return False
