# -*- coding: utf-8 -*-
from odoo import models, api, fields


PARAMETER_PREFIX = "odubook.user_language."


class ResUsers(models.Model):
    _inherit = "res.users"

    #: Настройка намеренно не хранится в res_users: код модуля должен
    #: безопасно загружаться до обновления схемы базы данных.
    odubook_lang_id = fields.Many2one(
        "res.lang",
        string="Book Language",
        compute="_compute_odubook_lang_id",
        inverse="_inverse_odubook_lang_id",
        help="Language the Book, Manuals and Changes open in. "
             "Leave it empty to follow the user interface language.",
    )

    @api.depends_context("uid")
    def _compute_odubook_lang_id(self):
        parameters = self.env["ir.config_parameter"].sudo()
        languages = self.env["res.lang"]
        for user in self:
            language_id = parameters.get_param(PARAMETER_PREFIX + str(user.id))
            try:
                language_id = int(language_id)
            except (TypeError, ValueError):
                language_id = False
            user.odubook_lang_id = languages.browse(language_id).exists()

    def _inverse_odubook_lang_id(self):
        parameters = self.env["ir.config_parameter"].sudo()
        for user in self:
            parameters.set_param(
                PARAMETER_PREFIX + str(user.id),
                user.odubook_lang_id.id or False,
            )

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ["odubook_lang_id"]

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ["odubook_lang_id"]
