# -*- encoding: utf-8 -*-
import json
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError


class AiChatCommand(models.Model):
    _name = 'odupilot.command'
    _description = 'OduPilot Outbox Command'
    _order = 'id'

    # Команда close переживает удаление своей сессии: иначе каталог сессии
    # остаётся на volume навсегда. Её данные берутся из снимка в payload.
    session_id = fields.Many2one(
        'odupilot.session', ondelete='set null', index=True)
    user_id = fields.Many2one(
        'res.users', string='Actual actor', required=True,
        ondelete='restrict', index=True)
    command_type = fields.Selection([
        ('init', 'Initialize session'),
        ('reset', 'Reset conversation'),
        ('prompt', 'Prompt'),
        ('abort', 'Abort'),
        ('permission', 'Permission response'),
        ('publish', 'Publish developer branch'),
        ('close', 'Close Session'),
    ], required=True, index=True)
    source_message_id = fields.Many2one(
        'mail.message', ondelete='set null', index=True)
    recovery_id = fields.Many2one(
        'odupilot.recovery', ondelete='set null', index=True, readonly=True)
    # Вопрос из чаттера возвращается заметкой в свою запись, а ответ приходит
    # отдельным событием моста: адрес ответа переживает всю очередь.
    origin_model = fields.Char(
        string='Origin model', readonly=True, index=True)
    origin_res_id = fields.Integer(
        string='Origin record ID', readonly=True, index=True)
    payload = fields.Text(required=True, default='{}')
    external_id = fields.Char(required=True, index=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('done', 'Done'),
        ('error', 'Error'),
    ], required=True, default='pending', index=True)
    attempts = fields.Integer(default=0)
    next_attempt_at = fields.Datetime(index=True)
    processing_started_at = fields.Datetime(index=True)
    completed_at = fields.Datetime(
        string='Completed at', readonly=True, index=True)
    duration_seconds = fields.Float(
        string='Duration (seconds)',
        compute='_compute_duration_seconds', store=True, readonly=True)
    error = fields.Text()

    _sql_constraints = [('odupilot_command_external_unique', 'unique(external_id)', 'This AI chat command already exists.'), ('odupilot_command_source_unique', 'unique(source_message_id)', 'This Discuss message was already routed to AI.')]

    BRIDGE_CHANNEL = 'odupilot_commands'

    @api.depends('create_date', 'completed_at')
    def _compute_duration_seconds(self):
        for command in self:
            if command.create_date and command.completed_at:
                command.duration_seconds = max(
                    0, (command.completed_at - command.create_date).total_seconds())
            else:
                command.duration_seconds = 0

    def write(self, vals):
        vals = dict(vals)
        state = vals.get('state')
        if state in ('done', 'error') and 'completed_at' not in vals:
            vals['completed_at'] = fields.Datetime.now()
        elif state in ('pending', 'processing'):
            vals.setdefault('completed_at', False)
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        commands = super().create(vals_list)
        if commands:
            # Bus служит только сигналом: payload и секреты bridge забирает
            # атомарно через bridge_claim() после commit текущей транзакции.
            self.env['bus.bus']._sendone(
                self.BRIDGE_CHANNEL,
                'odupilot.command.available',
                {},
            )
        return commands

    @api.model
    def _check_bridge_access(self):
        # Гейт держится на выделенной группе, а не на group_system: эти методы
        # читают очередь всех пользователей и отдают секреты деплоя, поэтому
        # сервисной записи моста не нужны права администратора Odoo.
        if not self.env.user.has_group('odupilot.group_bridge'):
            raise AccessError(_(
                'Only the AI chat bridge service account may run the AI chat bridge.'))

    @api.model
    def bridge_claim(self, limit=10):
        self._check_bridge_access()
        limit = max(1, min(int(limit or 10), 50))
        self.flush_model([
            'state', 'next_attempt_at', 'processing_started_at',
        ])
        self.env['odupilot.session'].flush_model(['state'])
        stale_before = fields.Datetime.now() - timedelta(minutes=10)
        stale = self.sudo().search([
            ('state', '=', 'processing'),
            ('processing_started_at', '<', stale_before),
        ])
        stale_closed = stale.filtered(
            lambda command: command.session_id.state == 'closed'
            and command.command_type != 'close')
        stale_closed.write({
            'state': 'error',
            'processing_started_at': False,
            'next_attempt_at': False,
            'error': _('Cancelled because the AI chat was closed.'),
        })
        (stale - stale_closed).write({
            'state': 'pending',
            'processing_started_at': False,
            'next_attempt_at': fields.Datetime.now(),
            'error': _('The bridge claim expired and was returned to the outbox.'),
        })

        self.env.cr.execute("""
            SELECT command.id
              FROM odupilot_command command
              LEFT JOIN odupilot_session session
                ON session.id = command.session_id
             WHERE command.state = 'pending'
               AND (command.next_attempt_at IS NULL
                    OR command.next_attempt_at <= NOW())
               AND (command.session_id IS NOT NULL
                    OR command.command_type = 'close')
               AND (
                    command.command_type IN ('init', 'abort', 'close')
                    OR (command.command_type = 'prompt'
                        AND session.state = 'ready')
                    -- Сброс разговора обрывает ход модели, поэтому он ждёт
                    -- завершения предыдущего вопроса: иначе ответ на него
                    -- потерялся бы вместе со старым разговором OpenCode.
                    OR (command.command_type = 'reset'
                        AND session.state = 'ready')
                    OR (command.command_type = 'publish'
                        AND session.state = 'ready')
                    OR (command.command_type = 'permission'
                        AND session.state = 'waiting_approval')
               )
               AND NOT EXISTS (
                    SELECT 1
                      FROM odupilot_command earlier
                     WHERE earlier.session_id = command.session_id
                       AND earlier.id < command.id
                       AND earlier.state IN ('pending', 'processing')
               )
             ORDER BY command.id
             FOR UPDATE OF command SKIP LOCKED
             LIMIT %s
        """, [limit])
        commands = self.sudo().browse(
            [row[0] for row in self.env.cr.fetchall()]).exists()
        if not commands:
            return []
        commands.write({
            'state': 'processing',
            'processing_started_at': fields.Datetime.now(),
        })
        for command in commands:
            command.attempts += 1
        return [command._bridge_values() for command in commands]

    def _bridge_values(self):
        self.ensure_one()
        try:
            payload = json.loads(self.payload or '{}')
        except (TypeError, ValueError):
            payload = {}
        session = self.session_id.sudo()
        if not session:
            return self._orphan_bridge_values(payload)
        snapshot = session._workspace_snapshot()
        workspace = snapshot['workspace']
        if (self.command_type in ('init', 'publish')
                and session._workspace_type() == 'worktree'):
            repo_url, github_pat, base_branch = session._developer_settings()
            workspace.update({
                'repo_url': repo_url,
                'github_pat': github_pat,
                'base_branch': base_branch,
            })
        values = {
            'id': self.id,
            'attempts': self.attempts,
            'command_type': self.command_type,
            'directory': snapshot['directory'],
            'title': snapshot['title'],
            'opencode_session_id': snapshot['opencode_session_id'],
            'model': snapshot['model'],
            'payload': payload,
            'workspace': workspace,
        }
        if self.command_type in ('init', 'prompt'):
            values['opencode_config'] = session._opencode_config()
            values['opencode_environment'] = (
                session._opencode_environment())
        return values

    def _orphan_bridge_values(self, payload):
        # Сессия уже удалена; мост убирает её каталог по снимку, записанному
        # в payload перед удалением.
        self.ensure_one()
        snapshot = payload.get('session_snapshot') or {}
        return {
            'id': self.id,
            'attempts': self.attempts,
            'command_type': self.command_type,
            'directory': snapshot.get('directory') or '',
            'title': snapshot.get('title') or '',
            'opencode_session_id': snapshot.get('opencode_session_id') or '',
            'model': snapshot.get('model') or '',
            'payload': payload,
            'workspace': snapshot.get('workspace') or {},
        }

    @api.model
    def bridge_ack(self, command_id, success, result=None, error=''):
        self._check_bridge_access()
        command = self.sudo().browse(int(command_id)).exists()
        if not command:
            raise UserError(_('The AI chat command no longer exists.'))
        if command.state == 'done' and success:
            return {'retry_after': 0}
        if command.state != 'processing':
            raise UserError(_(
                'The AI chat command is not currently claimed by the bridge.'))
        result = result or {}
        if success:
            command.write({
                'state': 'done',
                'processing_started_at': False,
                'next_attempt_at': False,
                'error': False,
            })
            if command.command_type in ('init', 'reset'):
                session_id = result.get('id')
                if not session_id:
                    raise UserError(_(
                        'OpenCode did not return a session identifier.'))
                values = {'opencode_session_id': session_id}
                # Сброс выполняется в готовой сессии и её состояние не меняет:
                # ready ставит только первичная инициализация.
                if (command.command_type == 'init'
                        and command.session_id.state != 'closed'):
                    values['state'] = 'ready'
                command.session_id.write(values)
            elif command.command_type == 'prompt':
                if command.session_id.state != 'closed':
                    already_admitted = result.get('already_admitted')
                    session_busy = result.get('session_busy')
                    if not already_admitted or session_busy:
                        values = {
                            'state': 'busy',
                            'busy_since': fields.Datetime.now(),
                            'error': False,
                            'active_prompt_command_id': command.id,
                        }
                        if (command.session_id.active_prompt_command_id
                                != command):
                            values['active_prompt_has_tool_activity'] = False
                        command.session_id.write(values)
                    elif command.session_id.state != 'error':
                        command.session_id.write({
                            'state': 'ready',
                            'busy_since': False,
                            'error': False,
                            'active_prompt_command_id': False,
                            'active_prompt_has_tool_activity': False,
                        })
            elif command.command_type == 'abort':
                if command.session_id.state != 'closed':
                    command.session_id._clear_stream('done')
                    pending_recovery = self.env[
                        'odupilot.recovery'].sudo().search([
                            ('abort_command_id', '=', command.id),
                            ('status', '=', 'pending'),
                        ], limit=1)
                    command.session_id.write({
                        'state': 'error' if pending_recovery else 'ready',
                        'busy_since': False,
                        'error': (
                            _('A recovery decision is required.')
                            if pending_recovery else False),
                    })
            elif command.command_type == 'permission':
                try:
                    payload = json.loads(command.payload or '{}')
                except (TypeError, ValueError):
                    payload = {}
                permission = self.env['odupilot.permission'].sudo().search([
                    ('session_id', '=', command.session_id.id),
                    ('request_id', '=', payload.get('permission_id')),
                ], limit=1)
                if permission:
                    permission._mark_replied(
                        payload.get('response'), command.user_id)
                if command.session_id.state != 'closed':
                    command.session_id.write({
                        'state': 'busy',
                        'busy_since': fields.Datetime.now(),
                        'error': False,
                    })
            elif command.command_type == 'publish':
                pull_request_url = result.get('pull_request_url') or ''
                branch_url = result.get('branch_url') or ''
                command.session_id.write({
                    'pull_request_url': pull_request_url or False,
                    'error': False,
                })
                command.session_id._audit_event(
                    'developer.published',
                    {
                        'branch': command.session_id.branch,
                        'branch_url': branch_url,
                        'pull_request_url': pull_request_url,
                    },
                    command.user_id,
                    'developer:published:%s' % command.id,
                )
                target_url = pull_request_url or branch_url
                message = (
                    _('Developer branch published: %s', target_url)
                    if target_url else
                    _('Developer branch published.')
                )
                bot = self.env.ref('odupilot.partner_ai_bot')
                command.session_id.channel_id.with_context(
                    odupilot_skip_enqueue=True).sudo().message_post(
                        author_id=bot.id,
                        body=message,
                        message_type='notification',
                        subtype_xmlid='mail.mt_comment',

                    )
            elif command.command_type == 'close':
                command.session_id._finalize_close()
            return {'retry_after': 0}

        if (command.session_id.state == 'closed'
                and command.command_type != 'close'):
            command.write({
                'state': 'error',
                'processing_started_at': False,
                'next_attempt_at': False,
                'error': error or _(
                    'Cancelled because the AI chat was closed.'),
            })
            return {'retry_after': 0}

        if command.attempts >= 5:
            command.write({
                'state': 'error',
                'processing_started_at': False,
                'error': error or _('Unknown bridge error.'),
            })
            if (command.session_id.is_ask_session
                    and command.command_type == 'prompt'):
                command.session_id._fail_ask_prompt(command, error)
            elif (command.session_id.is_ask_session
                    and command.command_type in ('init', 'reset')):
                command.session_id._fail_waiting_ask_prompts(command, error)
            if command.command_type == 'publish':
                message = _(
                    'Developer branch publication failed: %s',
                    error or _('Unknown bridge error.'),
                )
                command.session_id.write({
                    'state': 'ready',
                    'busy_since': False,
                    'error': message,
                })
                command.session_id._audit_event(
                    'developer.publish.failed',
                    {'error': error or _('Unknown bridge error.')},
                    command.user_id,
                    'developer:publish:failed:%s' % command.id,
                )
                bot = self.env.ref('odupilot.partner_ai_bot')
                command.session_id.channel_id.with_context(
                    odupilot_skip_enqueue=True).sudo().message_post(
                        author_id=bot.id,
                        body=message,
                        message_type='notification',
                        subtype_xmlid='mail.mt_comment',

                    )
            elif command.command_type == 'close':
                command.session_id.error = (
                    error or _('Unknown bridge error.'))
            else:
                command.session_id.write({
                    'state': 'error',
                    'error': error or _('Unknown bridge error.'),
                })
            retry_after = 0
        else:
            delay = min(2 ** command.attempts, 60)
            command.write({
                'state': 'pending',
                'processing_started_at': False,
                'next_attempt_at': fields.Datetime.now() + timedelta(seconds=delay),
                'error': error or _('Unknown bridge error.'),
            })
            retry_after = delay
        return {'retry_after': retry_after}
