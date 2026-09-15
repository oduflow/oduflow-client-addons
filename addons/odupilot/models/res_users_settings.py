# -*- encoding: utf-8 -*-
from odoo import fields, models


class ResUsersSettings(models.Model):
    _inherit = 'res.users.settings'

    # Discuss хранит состояние каждой категории sidebar отдельным полем и
    # отдаёт их клиенту через _res_users_settings_format(); своей категории
    # нужен свой ключ, иначе она будет схлопываться вместе с Direct Messages.
    is_discuss_sidebar_category_ai_open = fields.Boolean(
        string='Is discuss sidebar category AI open?', default=True)
