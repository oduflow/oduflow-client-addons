# -*- coding: utf-8 -*-
from odoo import fields, models


class OduBookChangeRead(models.Model):
    """Отметка «прочитано» на одну запись летописи.

    Запись летописи -- это пара ``(модуль, дата)``, то есть один файл
    ``doc/changes/YYYY-MM-DD.md``. Отметки персональные: строка создаётся,
    когда пользователь увидел запись в правой панели, и больше не меняется.
    """

    _name = "odubook.change.read"
    _description = "Read Change Entry"

    user_id = fields.Many2one(
        "res.users",
        string="User",
        required=True,
        index=True,
        ondelete="cascade",
        default=lambda self: self.env.user,
    )
    module = fields.Char(string="Module", required=True, index=True)
    change_date = fields.Date(string="Change Date", required=True)

    _sql_constraints = [('odubook_change_read_uniq', 'unique(user_id, module, change_date)', 'A change entry can be marked as read only once per user.')]
