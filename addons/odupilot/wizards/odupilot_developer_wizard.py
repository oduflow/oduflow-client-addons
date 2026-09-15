# -*- encoding: utf-8 -*-
import base64
import binascii
import json
import logging
import os

import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

DEFAULT_TRANSCRIPTION_MODEL = 'whisper-1'
MAX_VOICE_DURATION = 5 * 60
MAX_VOICE_SIZE = 25 * 1024 * 1024
TRANSCRIPTION_MODEL_PARAM = 'odupilot.transcription_model'
VOICE_EXTENSIONS = ('.webm', '.ogg', '.oga', '.m4a', '.mp4', '.mp3', '.wav')
VOICE_MIMETYPES = ('audio/webm', 'audio/ogg', 'audio/mp4', 'audio/mpeg',
                   'audio/wav', 'audio/x-wav', 'audio/x-m4a', 'audio/mp3',
                   'video/webm', 'video/ogg', 'video/mp4')

from ..models.config_validation import validate_http_url


CONTEXT_SIZE_LIMIT = 60000
RECORD_LIMIT = 100


_logger = logging.getLogger(__name__)


class AiChatDeveloperWizard(models.TransientModel):
    _name = 'odupilot.developer.wizard'
    _description = 'Start AI Developer'

    source_context_json = fields.Text(
        string='Invocation context', required=True, readonly=True,
        default='{}')
    source_summary = fields.Text(
        string='Called from', compute='_compute_source_summary', readonly=True)
    prompt = fields.Text(string='Developer request', required=True)

    @api.model
    def transcribe_voice(self, audio_base64, filename, mimetype, duration):
        """Расшифровать запись без сохранения исходного аудио в Odoo."""
        if not self.env.user.has_group('base.group_system'):
            raise UserError(_(
                'Only Odoo administrators can use AI Developer.'))
        try:
            duration = int(duration or 0)
        except (TypeError, ValueError):
            duration = 0
        if duration < 1 or duration > MAX_VOICE_DURATION:
            raise UserError(_(
                'Voice recording must be between one second and five minutes.'))
        try:
            audio = base64.b64decode(audio_base64 or '', validate=True)
        except (binascii.Error, TypeError, ValueError):
            raise UserError(_('Voice recording data is invalid.'))
        if not audio:
            raise UserError(_('Voice recording is empty.'))
        if len(audio) > MAX_VOICE_SIZE:
            raise UserError(_('Voice recording is too large (25 MB max).'))
        mimetype = (mimetype or '').split(';', 1)[0].strip().lower()
        filename = os.path.basename(filename or 'voice.webm')[:200]
        extension = os.path.splitext(filename)[1].lower()
        if mimetype not in VOICE_MIMETYPES or extension not in VOICE_EXTENSIONS:
            raise UserError(_('This audio format is not supported.'))

        profile = self.env['odupilot.session']._configured_developers_profile()
        parameters = self.env['ir.config_parameter'].sudo()
        base_url = (
            os.getenv('ODUPILOT_AI_BASE_URL')
            or os.getenv('ODUPILOT_LITELLM_BASE_URL')
            or parameters.get_param('odupilot.ai_base_url')
            or parameters.get_param('odupilot.litellm_base_url')
        )
        try:
            base_url = validate_http_url(base_url, _('AI base URL'), env=self.env)
        except ValidationError:
            raise UserError(_(
                'Configure a valid AI base URL before recording voice.'))
        model = (
            parameters.get_param(TRANSCRIPTION_MODEL_PARAM)
            or DEFAULT_TRANSCRIPTION_MODEL)
        try:
            response = requests.post(
                '%s/audio/transcriptions' % base_url.rstrip('/'),
                headers={
                    'Authorization': 'Bearer %s' % profile.litellm_api_key,
                },
                files={'file': (filename, audio, mimetype)},
                data={'model': model, 'response_format': 'json'},
                timeout=(10, 120),
            )
        except requests.RequestException as error:
            _logger.warning('OduPilot: ошибка транскрибации голоса: %s', error)
            raise UserError(_(
                'Voice transcription service is temporarily unavailable. '
                'Try again.'))
        if response.status_code >= 400:
            _logger.warning(
                'OduPilot: транскрибация отклонена, HTTP %s: %s',
                response.status_code, response.text[:500])
            raise UserError(_(
                'Voice transcription failed. Try recording again or type the '
                'request.'))
        try:
            text = (response.json() or {}).get('text') or ''
        except ValueError:
            text = ''
        text = text.strip()
        if not text:
            raise UserError(_(
                'No speech was recognized. Try recording again or type the '
                'request.'))
        return text

    @api.depends('source_context_json')
    def _compute_source_summary(self):
        for wizard in self:
            try:
                context = json.loads(wizard.source_context_json or '{}')
            except (TypeError, ValueError):
                context = {}
            action = context.get('action') or {}
            controller = context.get('controller') or {}
            router = context.get('router') or {}
            parts = []
            action_name = action.get('name') or action.get('display_name')
            model = (
                controller.get('res_model') or action.get('res_model')
                or router.get('model'))
            view_type = controller.get('view_type') or router.get('view_type')
            res_id = controller.get('res_id') or router.get('id')
            for value in (action_name, model, view_type):
                if value:
                    parts.append(str(value))
            if res_id:
                parts.append(_('record %s', res_id))
            wizard.source_summary = ' · '.join(parts) or _(
                'Current Odoo screen')

    def _client_context(self):
        self.ensure_one()
        source = self.source_context_json or '{}'
        if len(source) > CONTEXT_SIZE_LIMIT:
            raise UserError(_(
                'Developer invocation context is too large.'))
        try:
            context = json.loads(source)
        except (TypeError, ValueError):
            raise UserError(_('Developer invocation context is invalid.'))
        if not isinstance(context, dict):
            raise UserError(_('Developer invocation context is invalid.'))
        return context

    def _record_external_id(self, record):
        return record.get_external_id().get(record.id) or ''

    def _server_context(self, client_context):
        """Дополнить клиентские ids именами и XML IDs из текущей базы."""
        action_data = client_context.get('action') or {}
        action_context = action_data.get('context') or {}
        controller = client_context.get('controller') or {}
        router = client_context.get('router') or {}
        result = {
            'user': {
                'id': self.env.user.id,
                'name': self.env.user.name,
                'language': self.env.user.lang,
                'timezone': self.env.user.tz or '',
            },
            'company': {
                'id': self.env.company.id,
                'name': self.env.company.name,
            },
        }
        action_model = action_data.get('type')
        if (not isinstance(action_model, str)
                or not action_model.startswith('ir.actions.')
                or action_model not in self.env):
            action_model = 'ir.actions.actions'
        references = (
            ('action', action_model, action_data.get('id')),
            ('view', 'ir.ui.view',
             controller.get('view_id') or router.get('view_id')),
            ('menu', 'ir.ui.menu', router.get('menu_id')),
        )
        for key, model_name, value in references:
            try:
                record_id = int(value)
            except (TypeError, ValueError):
                continue
            record = self.env[model_name].browse(record_id).exists()
            if record:
                result[key] = {
                    'id': record.id,
                    'name': record.display_name,
                    'xml_id': self._record_external_id(record),
                }

        model_name = (
            controller.get('res_model') or action_data.get('res_model')
            or router.get('model'))
        ids = controller.get('res_ids') or action_context.get('active_ids') or []
        res_id = (
            controller.get('res_id') or router.get('id')
            or action_context.get('active_id'))
        if res_id:
            ids = [res_id] + list(ids if isinstance(ids, list) else [])
        normalized_ids = []
        for value in ids:
            try:
                value = int(value)
            except (TypeError, ValueError):
                continue
            if value and value not in normalized_ids:
                normalized_ids.append(value)
            if len(normalized_ids) >= RECORD_LIMIT:
                break
        if model_name and model_name in self.env:
            model = self.env[model_name]
            model.check_access('read')
            records = model.browse(normalized_ids).exists()
            if records:
                records.check_access('read')
            result['records'] = {
                'model': model_name,
                'ids': records.ids,
                'names': [
                    {'id': record.id, 'name': record.display_name}
                    for record in records[:20]
                ],
            }
        return result

    def action_send(self):
        self.ensure_one()
        client_context = self._client_context()
        developer_context = {
            'client': client_context,
            'server': self._server_context(client_context),
        }
        return self.env['odupilot.session'].action_new_developer_chat(
            self.prompt, developer_context)
