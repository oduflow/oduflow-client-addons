from odoo import models
from odoo.http import request

from .session import ORIGIN_UID_KEY


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    def session_info(self):
        result = super().session_info()
        origin_uid = request.session.get(ORIGIN_UID_KEY) if request else None
        result.update(
            {
                "odulogin_can_switch": bool(request.session.uid and self.env.user._is_system())
                if request
                else False,
                "odulogin_is_switched": bool(origin_uid),
            }
        )
        if origin_uid:
            origin = self.env["res.users"].sudo().browse(origin_uid).exists()
            result["odulogin_origin_name"] = origin.name if origin else ""
        return result
