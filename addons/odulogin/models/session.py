from odoo import _, api, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request


ORIGIN_UID_KEY = "odulogin_origin_uid"


class OduLoginSession(models.AbstractModel):
    _name = "odulogin.session"
    _description = "OduLogin Session Service"

    @api.model
    def _start(self, target_user):
        """Switch the current web session to ``target_user``."""
        self._require_web_session()
        origin_user = self.env.user
        if not origin_user._is_system():
            raise AccessError(_("Only settings administrators can switch users."))
        if request.session.get(ORIGIN_UID_KEY):
            raise UserError(_("Return to your administrator account before switching again."))

        target_user = target_user.exists()
        if not target_user or len(target_user) != 1:
            raise ValidationError(_("Select an existing user."))
        if target_user == origin_user:
            raise ValidationError(_("Select a user other than yourself."))
        if target_user.id == self.env.ref("base.user_root").id:
            raise ValidationError(_("The technical superuser cannot be selected."))
        if not target_user.active or not target_user._is_internal():
            raise ValidationError(_("Only active internal users can be selected."))

        request.session[ORIGIN_UID_KEY] = origin_user.id
        self._set_session_user(target_user)
        return {"type": "ir.actions.client", "tag": "reload"}

    @api.model
    def switch_back(self):
        """Restore the administrator saved by :meth:`_start`."""
        self._require_web_session()
        origin_uid = request.session.get(ORIGIN_UID_KEY)
        if not origin_uid:
            raise UserError(_("This session is not switched to another user."))

        origin_user = self.env["res.users"].sudo().browse(origin_uid).exists()
        if not origin_user or not origin_user.active:
            raise UserError(_("The original administrator account is no longer active."))

        request.session.pop(ORIGIN_UID_KEY, None)
        self._set_session_user(origin_user)
        return True

    @api.model
    def _require_web_session(self):
        if not request or not request.session or not request.session.uid:
            raise UserError(_("User switching is only available in an authenticated web session."))

    @api.model
    def _set_session_user(self, user):
        """Apply a complete authenticated identity to the current request."""
        user_env = self.env(user=user.id, su=False)
        context = dict(user_env["res.users"].context_get())
        request.session.update(
            {
                "uid": user.id,
                "login": user.login,
                "context": context,
                "session_token": user._compute_session_token(request.session.sid),
            }
        )
        request.session.should_rotate = True
        request.update_env(user=user.id, context=context, su=False)
