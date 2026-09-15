# -*- encoding: utf-8 -*-
import re

from werkzeug.datastructures import WWWAuthenticate
from werkzeug.exceptions import Unauthorized

from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _auth_method_mcp(cls):
        header = request.httprequest.headers.get('Authorization', '')
        match = re.fullmatch(r'Bearer\s+(.+)', header, re.IGNORECASE)
        token = match.group(1) if match else ''
        if not token.startswith('ais.'):
            return super()._auth_method_mcp()

        session = request.env['odupilot.session'].sudo()._check_ai_session_token(
            token)
        if not session:
            raise Unauthorized(
                'The AI session token is invalid or expired.',
                www_authenticate=WWWAuthenticate('Bearer'),
            )
        if request.session.uid and request.session.uid != session.user_id.id:
            raise Unauthorized(
                'The current session does not match the AI session token.',
                www_authenticate=WWWAuthenticate('Bearer'),
            )

        request.update_env(user=session.user_id.id)
        context = dict(request.env['res.users'].context_get())
        context.update({
            'odupilot_session_id': session.id,
            'odupilot_agent_id': session.agent_id.id,
        })
        request.update_context(**context)

    def session_info(self):
        result = super().session_info()
        # Кнопка «Ask AI» есть в чаттере каждой записи, поэтому её видимость
        # решается один раз при загрузке клиента, а не запросом на форму.
        # Профиль — админское поле, читать его через sudo() безопасно: наружу
        # уходит только признак доступности.
        if request and request.session.uid:
            user = request.env.user
            result['odupilot_available'] = bool(
                not user.share and user.sudo().odupilot_profile_id)
        return result
