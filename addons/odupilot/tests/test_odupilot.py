# -*- encoding: utf-8 -*-
import base64
import json
import os
import shutil
import tempfile
from datetime import datetime, timedelta
from unittest import mock
from markupsafe import Markup

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from odoo.addons.odupilot.models.message_renderer import (
    render_assistant_message,
)
from odoo.addons.odupilot.models import odupilot_session
from odoo.addons.odupilot.wizards import odupilot_developer_wizard


@tagged('post_install', '-at_install')
class TestAiChat(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.workspace = tempfile.mkdtemp(prefix='odoo-odupilot-')
        cls.workspace_root_patch = mock.patch.object(
            odupilot_session, 'WORKSPACE_ROOT', cls.workspace)
        cls.workspace_root_patch.start()
        parameters = cls.env['ir.config_parameter'].sudo()
        parameters.set_param(
            'odupilot.ai_base_url', 'http://litellm:4000/v1')
        cls.mcp_server = cls.env['odupilot.mcp.server'].sudo().create({
            'name': 'Company tools',
            'code': 'company-tools',
            'server_type': 'remote',
            'url': 'https://mcp.example.com/mcp',
            'headers_json': json.dumps({
                'Authorization': 'Bearer {env:ODOO_MCP_TOKEN}',
            }),
            'oauth_json': 'false',
            'timeout': 15000,
        })
        cls.profile = cls.env['odupilot.profile'].sudo().create({
            'name': 'Employee',
            'code': 'employee',
            'workspace_type': 'files',
            'model': 'test-model',
            'litellm_api_key': 'profile-litellm-key',
            'max_sessions': 5,
        })
        cls.agent = cls.env['odupilot.agent'].sudo().create({
            'name': 'Odoo Assistant',
            'code': 'odoo_assistant_test',
            'ruleset_json': json.dumps({
                'read': 'allow',
                'edit': 'ask',
            }),
            'system_prompt': 'Answer concisely.',
            'mcp_server_ids': [Command.set([cls.mcp_server.id])],
            'profile_ids': [Command.set([cls.profile.id])],
        })
        cls.profile.default_agent_id = cls.agent
        group_user = cls.env.ref('base.group_user')
        cls.bridge_group = cls.env.ref('odupilot.group_bridge')
        # Сервисная запись моста: только техническая группа, без group_system.
        cls.bridge = cls.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': 'OduPilot Bridge',
                'login': 'odupilot_bridge',
                'groups_id': [Command.set([cls.bridge_group.id])],
            })
        # Остальные тесты вызывают bridge_* от лица тестового окружения, поэтому
        # выдаём ту же группу и ему; запись откатится вместе с транзакцией.
        cls.env.user.sudo().write({
            'groups_id': [Command.link(cls.bridge_group.id)],
        })
        cls.owner = cls.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': 'OduPilot Owner',
                'login': 'odupilot_owner',
                'email': 'odupilot-owner@example.com',
                'groups_id': [Command.set([group_user.id])],
                'odupilot_profile_id': cls.profile.id,
            })
        cls.invited = cls.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': 'OduPilot Invited',
                'login': 'odupilot_invited',
                'email': 'odupilot-invited@example.com',
                'groups_id': [Command.set([group_user.id])],
            })
        cls.outsider = cls.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': 'OduPilot Outsider',
                'login': 'odupilot_outsider',
                'email': 'odupilot-outsider@example.com',
                'groups_id': [Command.set([group_user.id])],
            })

    @classmethod
    def tearDownClass(cls):
        cls.workspace_root_patch.stop()
        shutil.rmtree(cls.workspace, ignore_errors=True)
        super().tearDownClass()

    def _new_session(self):
        self.env['odupilot.session'].with_user(
            self.owner).action_new_chat()
        return self.env['odupilot.session'].sudo().search([
            ('user_id', '=', self.owner.id),
        ], order='id desc', limit=1)

    def test_open_channel_overrides_list_button_context(self):
        """active_id кнопки списка не должен перебивать канал нового чата."""
        session = self._new_session()
        action = session.with_user(self.owner).action_open_channel()
        active_id = session.channel_id.id
        self.assertEqual(action['context'], {'active_id': active_id})
        self.assertEqual(action['params']['default_active_id'], active_id)

    def _post(self, channel, user, body, partner_ids=None):
        return channel.with_user(user).message_post(
            body=Markup(body),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
            partner_ids=partner_ids or [],
        )

    def _ask_from_chatter(self, record, question, user=None):
        user = user or self.owner
        # Вопрос ложится заметкой в запись, поэтому спрашивающему нужны те же
        # права, что и для обычной заметки чаттера.
        user.sudo().write({'groups_id': [
            Command.link(self.env.ref('base.group_partner_manager').id)]})
        wizard = self.env['odupilot.ask.wizard'].with_user(user).create({
            'res_model': record._name,
            'res_id': record.id,
            'question': question,
        })
        wizard.action_ask()
        return self.env['odupilot.session'].sudo().search([
            ('user_id', '=', user.id),
            ('is_ask_session', '=', True),
        ], order='id desc', limit=1)

    def _last_prompt(self, session):
        return self.env['odupilot.command'].sudo().search([
            ('session_id', '=', session.id),
            ('command_type', '=', 'prompt'),
        ], order='id desc', limit=1)

    def _bus_marker(self):
        self.env.cr.precommit.run()
        return self.env['bus.bus'].sudo().search(
            [], order='id desc', limit=1).id or 0

    def _bus_notifications(self, marker):
        """Пары (канал без имени базы, тип) уведомлений после `marker`."""
        notifications = []
        self.env.cr.precommit.run()
        for record in self.env['bus.bus'].sudo().search(
                [('id', '>', marker)], order='id'):
            channel = json.loads(record.channel)
            message = json.loads(record.message)
            notifications.append((tuple(channel[1:]), message['type']))
        return notifications

    def _answer_ask_session(self, session, text='There are three orders.'):
        """Довести ответ моста до заметки записи."""
        self.env['odupilot.session'].ingest_events([{
            'opencode_session_id': session.opencode_session_id,
            'event_type': 'bridge.backfill.message',
            'external_id': 'message:msg_%s' % session.id,
            'payload': {
                'info': {
                    'id': 'msg_%s' % session.id,
                    'role': 'assistant',
                    'time': {'completed': 2},
                },
                'parts': [{
                    'id': 'prt_%s' % session.id,
                    'type': 'text',
                    'text': text,
                }],
            },
        }])

    def _developer_profile(self, code='developer-menu-test'):
        profile = self.env['odupilot.profile'].sudo().create({
            'name': 'Developer menu',
            'code': code,
            'workspace_type': 'worktree',
            'model': 'test-model',
            'litellm_api_key': 'developer-litellm-key',
            'max_sessions': 3,
            'developer_repo_url': 'https://github.com/example/developers.git',
            'developer_github_pat': 'github-test-pat',
            'developer_base_branch': 'prod',
            'developer_environment_mcp_server_id': self.mcp_server.id,
            'developer_environment_template_name': 'prod',
            'developer_environment_odoo_image': 'odoo15_veles',
        })
        self._attach_agent(
            profile, code, ruleset_json='{"bash": "allow"}')
        return profile

    def _attach_agent(self, profile, code, ruleset_json='{}',
                      mcp_servers=None, name=None):
        agent = self.env['odupilot.agent'].sudo().create({
            'name': name or profile.name,
            'code': 'agent_%s' % code.replace('-', '_'),
            'ruleset_json': ruleset_json,
            'mcp_server_ids': [Command.set(
                (mcp_servers or self.mcp_server).ids)],
            'profile_ids': [Command.set([profile.id])],
        })
        profile.default_agent_id = agent
        return agent

    def test_chatter_question_logs_a_note_and_reuses_one_service_session(self):
        record = self.owner.partner_id
        session = self._ask_from_chatter(record, 'Who is this partner?')

        self.assertTrue(session.is_ask_session)
        command = self._last_prompt(session)
        self.assertEqual(command.origin_model, 'res.partner')
        self.assertEqual(command.origin_res_id, record.id)
        payload = json.loads(command.payload)
        self.assertEqual(payload['text'], 'Who is this partner?')
        # Модель находит запись только по модели и ID из системной части.
        self.assertIn('res.partner', payload['system'])
        self.assertIn(str(record.id), payload['system'])

        note = command.source_message_id
        self.assertEqual(note.model, 'res.partner')
        self.assertEqual(note.res_id, record.id)
        self.assertEqual(note.subtype_id, self.env.ref('mail.mt_note'))
        self.assertEqual(note.author_id, self.owner.partner_id)
        self.assertIn('Question to AI', note.body)
        self.assertIn('AI is thinking', note.body)
        self.assertIn('o_AiChatQuestionStatus--pending', note.body)

        # Служебный разговор не дублирует вопрос и не показывается владельцу
        # в сайдбаре Discuss: вся переписка живёт в заметке записи.
        self.assertFalse(session.channel_id.message_ids.filtered(
            lambda message: 'Who is this partner?' in (message.body or '')))
        self.assertNotIn(
            self.owner.partner_id, session.channel_id.channel_partner_ids)

        followup = self._ask_from_chatter(record, 'And its address?')
        self.assertEqual(followup, session)
        self.assertEqual(self.env['odupilot.session'].sudo().search_count([
            ('user_id', '=', self.owner.id),
            ('is_ask_session', '=', True),
        ]), 1)

    def test_each_chatter_question_starts_a_clean_conversation(self):
        record = self.owner.partner_id
        session = self._ask_from_chatter(record, 'Who is this partner?')
        commands = self.env['odupilot.command'].sudo()

        # Разговора ещё нет: первый вопрос сбрасывать нечего.
        self.assertFalse(commands.search_count([
            ('session_id', '=', session.id),
            ('command_type', '=', 'reset'),
        ]))
        init = commands.search([
            ('session_id', '=', session.id),
            ('command_type', '=', 'init'),
        ])
        first_prompt = self._last_prompt(session)
        commands.bridge_claim(10)
        commands.bridge_ack(init.id, True, {'id': 'ses_ask_first'}, '')
        self.assertEqual(session.state, 'ready')
        commands.bridge_claim(10)
        commands.bridge_ack(first_prompt.id, True, {}, '')
        self.assertEqual(session.state, 'busy')

        second = self._ask_from_chatter(record, 'And what about the other one?')
        self.assertEqual(second, session)
        reset = commands.search([
            ('session_id', '=', session.id),
            ('command_type', '=', 'reset'),
        ])
        self.assertEqual(len(reset), 1)
        second_prompt = self._last_prompt(session)
        self.assertNotEqual(second_prompt, first_prompt)
        # Сброс встаёт перед вопросом, поэтому вопрос уходит уже в новый
        # разговор: очередь моста выдаётся строго по возрастанию id.
        self.assertLess(reset.id, second_prompt.id)

        # Пока предыдущий вопрос считается, сброс не выдаётся: он оборвал бы
        # ход модели вместе с ответом на тот вопрос.
        self.assertNotIn(
            reset.id, [item['id'] for item in commands.bridge_claim(10)])
        self.assertEqual(reset.state, 'pending')

        session.write({'state': 'ready', 'busy_since': False})
        claimed = commands.bridge_claim(10)
        self.assertIn(reset.id, [item['id'] for item in claimed])
        # Вопрос ждёт своей очереди за сбросом.
        self.assertNotIn(second_prompt.id, [item['id'] for item in claimed])
        self.assertEqual(
            [item['opencode_session_id']
             for item in claimed if item['id'] == reset.id],
            ['ses_ask_first'])
        commands.bridge_ack(reset.id, True, {'id': 'ses_ask_second'}, '')

        self.assertEqual(session.opencode_session_id, 'ses_ask_second')
        # Сессия и так готова: сброс её состояние не трогает.
        self.assertEqual(session.state, 'ready')
        self.assertFalse(session.last_message_id)
        self.assertFalse(session.trace_message_id)
        self.assertIn(
            second_prompt.id,
            [item['id'] for item in commands.bridge_claim(10)])

    def test_service_session_does_not_consume_the_chat_quota(self):
        self.profile.sudo().max_sessions = 1
        self._ask_from_chatter(self.owner.partner_id, 'Who is this partner?')

        # Служебная сессия чаттера не должна отнимать разговор у пользователя.
        self.env['odupilot.session'].with_user(self.owner).action_new_chat()
        self.assertEqual(self.env['odupilot.session'].sudo().search_count([
            ('user_id', '=', self.owner.id),
            ('is_ask_session', '=', False),
            ('state', '!=', 'closed'),
        ]), 1)

    def test_chatter_answer_is_appended_to_the_question_note(self):
        record = self.owner.partner_id
        session = self._ask_from_chatter(record, 'How many orders do we have?')
        command = self._last_prompt(session)
        session.write({
            'opencode_session_id': 'ses_ask_note',
            'state': 'busy',
            'active_prompt_command_id': command.id,
        })

        self.env['odupilot.session'].ingest_events([{
            'opencode_session_id': session.opencode_session_id,
            'event_type': 'bridge.backfill.message',
            'external_id': 'message:msg_ask_answer',
            'payload': {
                'info': {
                    'id': 'msg_ask_answer',
                    'role': 'assistant',
                    'time': {'completed': 2},
                },
                'parts': [
                    {
                        'id': 'prt_ask_reasoning',
                        'type': 'reasoning',
                        'text': 'I should count the orders first.',
                    },
                    {
                        'id': 'prt_ask_answer',
                        'type': 'text',
                        'text': 'There are **three** open orders.',
                    },
                ],
            },
        }])

        # Второй заметки нет: ответ подшит в ту, где задан вопрос.
        self.assertFalse(self.env['mail.message'].sudo().search([
            ('model', '=', 'res.partner'),
            ('res_id', '=', record.id),
            ('author_id', '=', self.env.ref('odupilot.partner_ai_bot').id),
        ]))
        note = command.source_message_id
        self.assertEqual(note.subtype_id, self.env.ref('mail.mt_note'))
        self.assertIn('How many orders do we have?', note.body)
        self.assertIn('<strong>three</strong>', note.body)
        self.assertIn('o_AiChatQuestionStatus--answered', note.body)
        self.assertIn('Answered', note.body)
        self.assertNotIn('o_AiChatQuestionStatus--pending', note.body)
        # Рассуждение остаётся в разговоре и в чаттер записи не едет.
        self.assertNotIn('count the orders first', note.body)
        self.assertIn(
            'count the orders first',
            ''.join(session.channel_id.message_ids.mapped('body')))
        self.assertEqual(session.state, 'ready')

    def test_answered_note_updates_in_place_without_a_broadcast_reload(self):
        record = self.owner.partner_id
        session = self._ask_from_chatter(record, 'How many orders do we have?')
        command = self._last_prompt(session)
        session.write({
            'opencode_session_id': 'ses_ask_bus',
            'state': 'busy',
            'active_prompt_command_id': command.id,
        })
        marker = self._bus_marker()

        self._answer_ask_session(session)

        notifications = self._bus_notifications(marker)
        # Тело заметки обновляется адресно у автора вопроса.
        self.assertIn(
            (('res.partner', self.owner.partner_id.id),
             'mail.record/insert'),
            notifications)
        updates = [json.loads(event.message)['payload']
                   for event in self.env['bus.bus'].sudo().search([('id', '>', marker)])
                   if json.loads(event.message)['type'] == 'mail.record/insert']
        note_bodies = [message['body'] for update in updates
                       for message in update.get('mail.message', [])
                       if message['id'] == command.source_message_id.id and 'body' in message]
        self.assertTrue(note_bodies)
        self.assertEqual(note_bodies[-1][0], 'markup')
        self.assertIn('three orders', note_bodies[-1][1])
        # Общий канал перезагрузил бы форму этой модели у всех, кто держит
        # её открытой, вместе с чужими несохранёнными правками.
        self.assertNotIn(
            'bus_actions', [channel[0] for channel, _type in notifications])

    def test_answer_without_its_note_reloads_only_for_the_asking_user(self):
        record = self.owner.partner_id
        session = self._ask_from_chatter(record, 'How many orders do we have?')
        command = self._last_prompt(session)
        session.write({
            'opencode_session_id': 'ses_ask_no_note',
            'state': 'busy',
            'active_prompt_command_id': command.id,
        })
        # Заметку с вопросом удалили: ответ приезжает новым сообщением, и
        # уведомить о нём открытый чаттер ядру нечем — получателей нет.
        command.source_message_id.sudo().unlink()
        marker = self._bus_marker()

        self._answer_ask_session(session)

        notifications = self._bus_notifications(marker)
        self.assertIn(
            (('res.partner', self.owner.partner_id.id), 'odupilot/chatter'),
            notifications)
        self.assertNotIn(
            'bus_actions', [channel[0] for channel, _type in notifications])
        self.assertTrue(self.env['mail.message'].sudo().search([
            ('model', '=', 'res.partner'),
            ('res_id', '=', record.id),
            ('author_id', '=', self.env.ref('odupilot.partner_ai_bot').id),
        ]))

    def test_failed_chatter_request_reports_itself_in_the_record(self):
        record = self.owner.partner_id
        session = self._ask_from_chatter(record, 'How many orders do we have?')
        command = self._last_prompt(session)
        session.write({
            'opencode_session_id': 'ses_ask_error',
            'state': 'busy',
            'active_prompt_command_id': command.id,
        })

        self.env['odupilot.session'].ingest_events([{
            'opencode_session_id': session.opencode_session_id,
            'event_type': 'bridge.backfill.message',
            'external_id': 'message:msg_ask_error',
            'payload': {
                'info': {
                    'id': 'msg_ask_error',
                    'role': 'assistant',
                    'time': {'completed': 2},
                    'error': {'name': 'ProviderError'},
                },
                'parts': [],
            },
        }])

        self.assertIn('ProviderError', command.source_message_id.body)
        self.assertIn(
            'o_AiChatQuestionStatus--failed', command.source_message_id.body)
        self.assertIn('Failed', command.source_message_id.body)
        self.assertEqual(session.state, 'error')

    def test_failed_reset_reports_error_in_every_waiting_question(self):
        record = self.owner.partner_id
        session = self._ask_from_chatter(record, 'First question')
        commands = self.env['odupilot.command'].sudo()
        init = commands.search([
            ('session_id', '=', session.id),
            ('command_type', '=', 'init'),
        ])
        first_prompt = self._last_prompt(session)
        commands.bridge_claim(10)
        commands.bridge_ack(init.id, True, {'id': 'ses_before_reset'}, '')
        commands.bridge_claim(10)
        commands.bridge_ack(first_prompt.id, True, {}, '')
        session.write({'state': 'ready', 'busy_since': False})

        self._ask_from_chatter(record, 'Question behind reset')
        reset = commands.search([
            ('session_id', '=', session.id),
            ('command_type', '=', 'reset'),
        ], order='id desc', limit=1)
        waiting_prompt = self._last_prompt(session)
        claimed = commands.bridge_claim(10)
        self.assertIn(reset.id, [item['id'] for item in claimed])
        reset.attempts = 5

        commands.bridge_ack(
            reset.id, False, {}, 'Unsupported command type: reset')

        self.assertEqual(reset.state, 'error')
        self.assertEqual(waiting_prompt.state, 'error')
        self.assertIn(
            'Unsupported command type: reset',
            waiting_prompt.source_message_id.body,
        )
        self.assertIn(
            'o_AiChatQuestionStatus--failed',
            waiting_prompt.source_message_id.body,
        )
        self.assertEqual(session.state, 'error')

    def test_failed_prompt_bridge_command_reports_error_in_question(self):
        record = self.owner.partner_id
        session = self._ask_from_chatter(record, 'Question for bridge')
        commands = self.env['odupilot.command'].sudo()
        init = commands.search([
            ('session_id', '=', session.id),
            ('command_type', '=', 'init'),
        ])
        prompt = self._last_prompt(session)
        commands.bridge_claim(10)
        commands.bridge_ack(init.id, True, {'id': 'ses_prompt_error'}, '')
        commands.bridge_claim(10)
        prompt.attempts = 5

        commands.bridge_ack(prompt.id, False, {}, 'Bridge rejected prompt')

        self.assertEqual(prompt.state, 'error')
        self.assertIn('Bridge rejected prompt', prompt.source_message_id.body)
        self.assertIn(
            'o_AiChatQuestionStatus--failed', prompt.source_message_id.body)
        self.assertEqual(session.state, 'error')

    def test_reinitialized_ask_session_keeps_its_queued_question(self):
        record = self.owner.partner_id
        session = self._ask_from_chatter(record, 'First question')
        commands = self.env['odupilot.command'].sudo()
        init = commands.search([
            ('session_id', '=', session.id),
            ('command_type', '=', 'init'),
        ])
        prompt = self._last_prompt(session)
        init.write({
            'state': 'error',
            'error': 'Unsupported command type: init',
        })

        self.assertEqual(session._stranded_ask_prerequisite(), init)

        # Сессия переинициализировалась после аварии: очередь снова поедет,
        # и гасить стоящий в ней вопрос нельзя.
        commands.create({
            'session_id': session.id,
            'user_id': self.owner.id,
            'command_type': 'init',
            'payload': '{}',
            'external_id': 'init:recovered:%s' % session.id,
            'state': 'done',
        })

        self.assertFalse(session._stranded_ask_prerequisite())
        self.assertEqual(prompt.state, 'pending')
        self.assertNotIn('o_AiChatQuestionStatus--failed',
                         prompt.source_message_id.body)

    def test_failed_reset_leaves_the_close_command_claimable(self):
        record = self.owner.partner_id
        session = self._ask_from_chatter(record, 'First question')
        commands = self.env['odupilot.command'].sudo()
        reset = commands.create({
            'session_id': session.id,
            'user_id': self.owner.id,
            'command_type': 'reset',
            'payload': '{}',
            'external_id': 'reset:manual:%s' % session.id,
            'state': 'error',
        })
        close = commands.create({
            'session_id': session.id,
            'user_id': self.owner.id,
            'command_type': 'close',
            'payload': '{}',
            'external_id': 'close:manual:%s' % session.id,
        })

        session._fail_waiting_ask_prompts(
            reset, 'Unsupported command type: reset')

        # Закрытие сессии мост забирает и при мёртвом разговоре — иначе её
        # каталог остался бы на volume навсегда.
        self.assertEqual(close.state, 'pending')

    def test_service_session_never_asks_for_permission(self):
        session = self._ask_from_chatter(
            self.owner.partner_id, 'Who is this partner?')

        rules = session._permission_rules()

        # Одобрять запрос разрешения в скрытом разговоре некому, поэтому
        # «спросить» превращается в «разрешить», а защита opencode.json
        # остаётся запретом.
        self.assertEqual(rules['edit']['*'], 'allow')
        self.assertEqual(rules['edit']['opencode.json'], 'deny')
        self.assertEqual(rules['bash'], 'deny')
        # Обычный разговор пользователя спрашивает по-прежнему.
        self.assertEqual(self._new_session()._permission_rules()['edit']['*'],
                         'ask')

    def test_developer_profile_ask_session_uses_files_workspace(self):
        developer_mcp = self.env['odupilot.mcp.server'].sudo().create({
            'name': 'Developer environment',
            'code': 'developer-environment',
            'server_type': 'remote',
            'url': 'https://developer-mcp.example.com/mcp',
            'oauth_json': 'false',
        })
        profile = self.env['odupilot.profile'].sudo().create({
            'name': 'Developer Ask AI',
            'code': 'developer-ask-ai',
            'workspace_type': 'worktree',
            'model': 'test-model',
            'litellm_api_key': 'developer-litellm-key',
            'max_sessions': 2,
            'developer_repo_url': 'https://github.com/example/developers.git',
            'developer_github_pat': 'github-test-pat',
            'developer_base_branch': 'prod',
            'developer_environment_mcp_server_id': developer_mcp.id,
        })
        self._attach_agent(
            profile,
            'developer-ask-ai',
            ruleset_json='{"bash": "allow", "edit": "ask"}',
        )
        developer = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': 'OduPilot Ask Developer',
                'login': 'odupilot_ask_developer',
                'email': 'odupilot-ask-developer@example.com',
                'groups_id': [Command.set([
                    self.env.ref('base.group_system').id,
                ])],
                'odupilot_profile_id': profile.id,
            })

        session = self._ask_from_chatter(
            developer.partner_id, 'Who is this partner?', user=developer)

        self.assertEqual(session._workspace_type(), 'files')
        self.assertFalse(session.branch)
        self.assertFalse(session.repository_directory)
        self.assertEqual(
            session.directory,
            os.path.join(
                self.workspace, 'users',
                'odupilot_ask_developer_%s' % developer.id,
                'chat_%s' % session.id,
            ),
        )
        self.assertTrue(session._is_safe_session_directory(session.directory))
        self.assertFalse(session._format_status_for_client()['discuss_only'])
        self.assertEqual(session._permission_rules()['bash'], 'deny')

        init = self.env['odupilot.command'].sudo().search([
            ('session_id', '=', session.id),
            ('command_type', '=', 'init'),
        ], limit=1)
        bridge_values = init._bridge_values()
        self.assertEqual(bridge_values['workspace']['type'], 'files')
        self.assertNotIn('repo_url', bridge_values['workspace'])
        self.assertNotIn('github_pat', bridge_values['workspace'])
        self.assertNotIn('base_branch', bridge_values['workspace'])
        self.assertIn('company-tools', bridge_values['opencode_config']['mcp'])
        self.assertNotIn(
            'developer-environment', bridge_values['opencode_config']['mcp'])

        prompt_payload = json.loads(self._last_prompt(session).payload)
        self.assertNotIn('Developer workflow:', prompt_payload['system'])
        marker_text = (
            'Answer.\n'
            'ODUPILOT_ENVIRONMENT_URL=https://developer.example.com\n'
            'ODUPILOT_PUBLISH_REQUEST={"title":"Unexpected","body":"No"}'
        )
        self.assertEqual(
            session._consume_developer_markers(marker_text, 'ask-answer'),
            marker_text,
        )
        self.assertFalse(session.env_url)
        self.assertFalse(self.env['odupilot.command'].sudo().search([
            ('session_id', '=', session.id),
            ('command_type', '=', 'publish'),
        ]))

    def test_developers_profile_setting_rejects_files_profile(self):
        with self.assertRaises(ValidationError):
            self.env['res.config.settings'].create({
                'odupilot_developers_profile_id': self.profile.id,
            })

    def test_responsible_developer_setting_rejects_regular_user(self):
        with self.assertRaises(ValidationError):
            self.env['res.config.settings'].create({
                'odupilot_responsible_developer_id': self.owner.id,
            })

    def test_developer_chat_requires_responsible_developer(self):
        profile = self._developer_profile('developer-no-responsible-test')
        parameters = self.env['ir.config_parameter'].sudo()
        parameters.set_param('odupilot.developers_profile_id', profile.id)
        parameters.set_param('odupilot.responsible_developer_id', '')

        with self.assertRaises(UserError):
            self.env['odupilot.session'].action_new_developer_chat(
                'Fix it.', {})

    def test_developer_chat_rejects_disabled_environment_mcp(self):
        profile = self._developer_profile('developer-disabled-mcp-test')
        self.env['ir.config_parameter'].sudo().set_param(
            'odupilot.developers_profile_id', profile.id)
        self.mcp_server.enabled = False

        with self.assertRaises(UserError):
            self.env['odupilot.session'].action_new_developer_chat(
                'Fix it.', {})

    def test_developer_wizard_starts_worktree_chat_with_screen_context(self):
        profile = self._developer_profile()
        developer = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': 'Developer menu administrator',
                'login': 'developer_menu_administrator',
                'groups_id': [Command.set([
                    self.env.ref('base.group_system').id,
                ])],
            })
        self.env['res.config.settings'].create({
            'odupilot_developers_profile_id': profile.id,
            'odupilot_responsible_developer_id': developer.id,
        }).set_values()
        action_record = self.env.ref('base.action_res_users')
        view = self.env.ref('base.view_users_form')
        menu = self.env.ref('base.menu_users')
        client_context = {
            'url': 'https://odoo.example.com/web#model=res.users&id=%s'
                   % self.owner.id,
            'document_title': 'Users - Odoo',
            'router': {
                'action': action_record.id,
                'menu_id': menu.id,
                'model': 'res.users',
                'id': self.owner.id,
                'view_type': 'form',
                'view_id': view.id,
            },
            'action': {
                'id': action_record.id,
                'name': 'Users',
                'type': 'ir.actions.act_window',
                'res_model': 'res.users',
                'context': {'active_id': self.owner.id},
                'domain': [],
                'views': [[view.id, 'form']],
            },
            'controller': {
                'view_type': 'form',
                'view_id': view.id,
                'res_model': 'res.users',
                'res_id': self.owner.id,
                'res_ids': [self.owner.id],
            },
        }
        wizard = self.env['odupilot.developer.wizard'].with_user(
            developer).create({
            'source_context_json': json.dumps(client_context),
            'prompt': 'Investigate why this user cannot open the report.',
        })

        action = wizard.action_send()

        session = self.env['odupilot.session'].sudo().search([
            ('user_id', '=', developer.id),
            ('profile_id', '=', profile.id),
        ], order='id desc', limit=1)
        self.assertTrue(session)
        self.assertRegex(session.branch, r'^[a-z]+-[a-z]+$')
        self.assertEqual(
            action['params']['default_active_id'],
            session.channel_id.id,
        )
        bootstrap = session.command_ids.filtered(
            lambda command: command.external_id == 'bootstrap:%s' % session.id)
        self.assertTrue(bootstrap)
        prompt = self._last_prompt(session)
        payload = json.loads(prompt.payload)
        self.assertEqual(
            payload['text'],
            'Investigate why this user cannot open the report.',
        )
        self.assertIn('AI Developer invocation context', payload['system'])
        self.assertIn(client_context['url'], payload['system'])
        self.assertIn('base.action_res_users', payload['system'])
        self.assertIn('base.view_users_form', payload['system'])
        self.assertIn('base.menu_users', payload['system'])
        self.assertIn(self.owner.display_name, payload['system'])
        self.assertIn('AI Developer triage', payload['system'])
        self.assertIn(
            'ODUPILOT_TRIAGE={"decision":"development"}',
            payload['system'])
        self.assertEqual(session.developer_triage_state, 'pending')
        self.assertEqual(session._permission_rules()['bash'], 'deny')
        self.assertEqual(session._permission_rules()['edit']['*'], 'deny')
        self.assertNotIn(
            client_context['url'], prompt.source_message_id.body)

    def test_developer_triage_resolves_without_assignment(self):
        profile = self._developer_profile('developer-resolved-test')
        parameters = self.env['ir.config_parameter'].sudo()
        parameters.set_param('odupilot.developers_profile_id', profile.id)
        parameters.set_param(
            'odupilot.responsible_developer_id', self.env.user.id)
        session = self.env['odupilot.session']._create_session(
            self.env.user, profile, developer_triage_state='pending')

        answer = session._consume_developer_markers(
            'Change the setting and try again. Can I help with anything else?\n'
            'ODUPILOT_TRIAGE={"decision":"resolved"}',
            'triage-resolved',
        )

        self.assertNotIn('ODUPILOT_TRIAGE', answer)
        self.assertIn('Change the setting', answer)
        self.assertEqual(session.developer_triage_state, 'resolved')
        self.assertFalse(session.responsible_developer_id)

    def test_code_problem_assigns_thread_and_notifies_developer(self):
        profile = self._developer_profile('developer-assigned-test')
        responsible = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': 'Responsible AI Developer',
                'login': 'responsible_ai_developer',
                'groups_id': [Command.set([
                    self.env.ref('base.group_system').id,
                ])],
            })
        parameters = self.env['ir.config_parameter'].sudo()
        parameters.set_param('odupilot.developers_profile_id', profile.id)
        parameters.set_param(
            'odupilot.responsible_developer_id', responsible.id)
        session = self.env['odupilot.session']._create_session(
            self.env.user, profile, developer_triage_state='pending')

        answer = session._consume_developer_markers(
            'The request has been accepted for development.\n'
            'ODUPILOT_TRIAGE={"decision":"development"}',
            'triage-development',
        )

        self.assertNotIn('ODUPILOT_TRIAGE', answer)
        self.assertIn(responsible.display_name, answer)
        self.assertEqual(session.developer_triage_state, 'development')
        self.assertEqual(session.responsible_developer_id, responsible)
        self.assertIn(
            responsible.partner_id,
            session.channel_id.with_context(
                active_test=False).channel_partner_ids,
        )
        self.env.cr.precommit.run()
        notifications = self.env['bus.bus'].sudo().search([])
        self.assertTrue(any(
            json.loads(event.message).get('type') == 'odupilot/assigned'
            and json.loads(event.channel) == [self.env.cr.dbname, 'res.partner', responsible.partner_id.id]
            for event in notifications))
        # Следующий ход уже является разработкой и получает обычные права.
        self.assertEqual(session._permission_rules()['bash'], 'allow')

    def test_developer_voice_is_transcribed_through_litellm(self):
        profile = self._developer_profile('developer-voice-test')
        parameters = self.env['ir.config_parameter'].sudo()
        parameters.set_param('odupilot.developers_profile_id', profile.id)
        parameters.set_param('odupilot.transcription_model', 'whisper-test')
        response = mock.Mock(status_code=200, text='')
        response.json.return_value = {'text': 'The invoice cannot be posted.'}

        with mock.patch.object(
                odupilot_developer_wizard.requests, 'post',
                return_value=response) as post:
            text = self.env['odupilot.developer.wizard'].transcribe_voice(
                base64.b64encode(b'fake-audio').decode(),
                'voice.webm', 'audio/webm;codecs=opus', 4)

        self.assertEqual(text, 'The invoice cannot be posted.')
        self.assertEqual(
            post.call_args.args[0],
            'http://litellm:4000/v1/audio/transcriptions')
        self.assertEqual(
            post.call_args.kwargs['data']['model'], 'whisper-test')
        self.assertEqual(
            post.call_args.kwargs['headers']['Authorization'],
            'Bearer developer-litellm-key')

    def test_regular_user_cannot_transcribe_developer_voice(self):
        with self.assertRaises(UserError):
            self.env['odupilot.developer.wizard'].with_user(
                self.owner).transcribe_voice(
                    base64.b64encode(b'fake-audio').decode(),
                    'voice.webm', 'audio/webm', 4)

    def test_only_administrator_can_start_configured_developer_chat(self):
        profile = self._developer_profile('developer-menu-access-test')
        self.env['ir.config_parameter'].sudo().set_param(
            'odupilot.developers_profile_id', profile.id)

        with self.assertRaises(AccessError):
            self.env['odupilot.session'].with_user(
                self.owner).action_new_developer_chat('Fix it.', {})

    def test_chatter_question_needs_an_odupilot_profile(self):
        self.outsider.sudo().write({'groups_id': [
            Command.link(self.env.ref('base.group_partner_manager').id)]})
        wizard = self.env['odupilot.ask.wizard'].with_user(self.outsider).create({
            'res_model': 'res.partner',
            'res_id': self.outsider.partner_id.id,
            'question': 'Who is this partner?',
        })

        with self.assertRaises(UserError):
            wizard.action_ask()

    def test_internal_user_can_start_selected_agent_chat(self):
        result = self.agent.with_user(self.owner).action_start_chat()

        session = self.env['odupilot.session'].sudo().search([
            ('user_id', '=', self.owner.id),
        ], order='id desc', limit=1)
        self.assertEqual(result['type'], 'ir.actions.client')
        self.assertTrue(session)
        self.assertEqual(session.user_id, self.owner)

    def test_workspace_root_is_fixed(self):
        parameters = self.env['ir.config_parameter'].sudo()
        parameters.set_param('odupilot.workspace_root', '/custom-workspace')
        with mock.patch.dict(os.environ, {
                'ODUPILOT_WORKSPACE_ROOT': '/environment-workspace'}):
            root = self.env['odupilot.session']._workspace_root()

        self.assertEqual(root, self.workspace)

    def test_bridge_init_contains_workspace_config_and_secret_file_rules(self):
        session = self._new_session()
        claimed = self.env['odupilot.command'].bridge_claim(10)
        config = claimed[0]['opencode_config']

        self.assertEqual(config['model'], 'litellm/test-model')
        self.assertEqual(
            config['provider']['litellm']['options']['apiKey'],
            'profile-litellm-key')
        self.assertEqual(config['provider']['litellm']['options']['baseURL'],
                         'http://litellm:4000/v1')
        self.assertEqual(config['mcp']['company-tools'], {
            'type': 'remote',
            'enabled': True,
            'timeout': 15000,
            'url': 'https://mcp.example.com/mcp',
            'headers': {
                'Authorization': 'Bearer {env:ODOO_MCP_TOKEN}',
            },
            'oauth': False,
        })
        self.assertEqual(config['permission']['bash'], 'deny')
        self.assertEqual(
            config['permission']['read']['**/opencode.json'], 'deny')
        self.assertEqual(
            config['permission']['edit']['opencode.json'], 'deny')
        self.assertFalse(os.path.exists(session.directory))
        self.assertEqual(claimed[0]['workspace']['root'], self.workspace)

    def test_profile_thinking_effort_reaches_the_opencode_model_options(self):
        session = self._new_session()
        config = self.env['odupilot.command'].bridge_claim(10)[0][
            'opencode_config']

        # Профиль по умолчанию просит максимальное усилие рассуждений.
        self.assertEqual(
            config['provider']['litellm']['models']['test-model']['options'],
            {'reasoningEffort': 'high'})

        self.profile.sudo().reasoning_effort = 'low'
        config = session._opencode_config()
        self.assertEqual(
            config['provider']['litellm']['models']['test-model']['options'],
            {'reasoningEffort': 'low'})

        # Provider default ничего не подмешивает: модели без thinking ломались
        # бы на неизвестном параметре.
        self.profile.sudo().reasoning_effort = 'default'
        config = session._opencode_config()
        self.assertEqual(
            config['provider']['litellm']['models']['test-model'],
            {'name': 'test-model'})

    def test_active_mcp_access_issues_signed_session_token_for_opencode(self):
        api_keys = self.env['res.users.apikeys']
        mcp_profile = self.env['odumcp.profile'].create({
            'name': 'OduPilot MCP Profile',
            'code': 'odupilot_test',
        })
        self.owner.write({
            'mcp_active': True,
            'mcp_profile_id': mcp_profile.id,
        })
        self.assertFalse(api_keys.sudo().search([
            ('user_id', '=', self.owner.id),
        ]))

        session = self._new_session()
        claimed = self.env['odupilot.command'].bridge_claim(10)
        session_token = claimed[0]['opencode_environment']['ODOO_MCP_TOKEN']

        self.assertEqual(
            self.env['odupilot.session']._check_ai_session_token(session_token),
            session)
        self.assertFalse(api_keys.sudo().search([
            ('user_id', '=', self.owner.id),
        ]))

        session.with_user(self.owner).action_close()
        self.assertFalse(
            self.env['odupilot.session']._check_ai_session_token(session_token))

    def test_inactive_mcp_access_exposes_no_session_token(self):
        session = self._new_session()

        self.assertEqual(session._opencode_environment(), {})

    def test_chat_is_bound_to_selected_agent(self):
        second_agent = self.env['odupilot.agent'].sudo().create({
            'name': 'Accounting Assistant',
            'code': 'accounting_assistant_test',
            'profile_ids': [Command.set([self.profile.id])],
            'mcp_server_ids': [Command.set([self.mcp_server.id])],
        })

        self.env['odupilot.session'].with_user(self.owner).action_new_chat(
            second_agent.id)
        session = self.env['odupilot.session'].sudo().search([
            ('user_id', '=', self.owner.id),
        ], order='id desc', limit=1)

        self.assertEqual(session.agent_id, second_agent)
        self.assertIn(second_agent.name, session.channel_id.name)
        self.assertIn(
            'agent record model odupilot.agent, ID %s' % second_agent.id,
            session._agent_identity_instructions(),
        )

    def test_agent_action_log_is_generic_correlated_and_immutable(self):
        session = self._new_session()
        Log = self.env['odupilot.agent.log'].with_user(self.owner).with_context(
            odupilot_session_id=session.id,
            odupilot_agent_id=session.agent_id.id,
            odumcp_request_id='00000000-0000-4000-8000-00000000a111',
        )

        log = Log._record_agent_action(
            session.agent_id,
            'test.operation',
            {'record_ids': [1]},
            {'ok': True},
            [{'field': 'state', 'old': 'draft', 'new': 'done'}],
        )

        self.assertEqual(log.user_id, self.owner)
        self.assertEqual(log.session_id, session)
        self.assertEqual(log.agent_id, session.agent_id)
        self.assertIn('record_ids', log.input_text)
        self.assertIn('draft', log.changes_text)
        with self.assertRaises(AccessError):
            log.write({'operation': 'changed'})

    def test_payment_agent_methods_require_its_signed_session_context(self):
        payment_agent = self.env.ref('odupilot.agent_payment_reconciliation')

        with self.assertRaises(AccessError):
            payment_agent.with_user(
                self.owner).payment_reconciliation_preview([1])

    def test_configure_mcp_methods_reports_what_it_did(self):
        # Object-кнопка без action молчит в UI: метод обязан вернуть toast,
        # иначе нажатие выглядит как «ничего не произошло».
        payment_agent = self.env.ref('odupilot.agent_payment_reconciliation')
        profile = self.env['odumcp.profile'].sudo().create({
            'name': 'Reconciliation profile',
            'code': 'reconciliation_profile',
        })

        action = payment_agent.action_configure_mcp_methods()

        self.assertEqual(action['tag'], 'display_notification')
        self.assertEqual(action['params']['type'], 'success')
        agent_model = self.env['ir.model'].sudo()._get('odupilot.agent')
        methods = self.env['odumcp.method.policy'].sudo().search([
            ('profile_id', '=', profile.id),
            ('model_id', '=', agent_model.id),
            ('method_name', 'in', [
                'payment_reconciliation_preview',
                'payment_reconciliation_apply',
            ]),
        ])
        self.assertEqual(set(methods.mapped('method_name')), {
            'payment_reconciliation_preview',
            'payment_reconciliation_apply',
        })

    def test_configure_mcp_methods_warns_without_any_profile(self):
        payment_agent = self.env.ref('odupilot.agent_payment_reconciliation')
        self.env['odumcp.profile'].sudo().search([]).write(
            {'active': False})

        action = payment_agent.action_configure_mcp_methods()

        self.assertEqual(action['tag'], 'display_notification')
        self.assertEqual(action['params']['type'], 'warning')

    def test_command_creation_notifies_bridge_without_payload(self):
        self._new_session()
        channel = json.dumps(
            (self.env.cr.dbname, 'odupilot_commands'), separators=(',', ':'))
        self.env.cr.precommit.run()
        notification = self.env['bus.bus'].sudo().search([
            ('channel', '=', channel),
        ], order='id desc', limit=1)

        self.assertTrue(notification)
        self.assertEqual(json.loads(notification.message), {
            'type': 'odupilot.command.available',
            'payload': {},
        })

    def test_chat_channel_is_marked_for_the_ai_sidebar_category(self):
        # Категория AI в sidebar Discuss опирается только на этот признак:
        # сессию можно закрыть, а канал остаётся в своей группе.
        session = self._new_session()

        self.assertTrue(session.channel_id.is_odupilot)
        self.assertEqual(
            session.channel_id.image_128,
            self.env['discuss.channel']._odupilot_default_avatar(),
        )
        channel_info = session.channel_id.with_user(
            self.owner).channel_info()[0]
        self.assertTrue(channel_info['is_odupilot'])

        session.action_close()
        self.assertTrue(session.channel_id.is_odupilot)

    def test_discuss_channel_info_and_live_session_status(self):
        session = self._new_session()

        channel_info = session.channel_id.with_user(
            self.owner).channel_info()[0]
        self.assertEqual(channel_info['odupilot_session'], {
            'channel_id': session.channel_id.id,
            'session_id': session.id,
            'agent_id': session.agent_id.id,
            'agent_name': session.agent_id.name,
            'state': 'init',
            'discuss_only': False,
            'error': '',
        })
        # Обычный чат живёт и в докированном окне: fold-state канала остаётся
        # тем, что записал сам пользователь.
        self.assertFalse(channel_info['odupilot_session']['discuss_only'])

        session.write({
            'state': 'error',
            'error': 'The model endpoint is unavailable.',
        })
        notifications = []
        self.env.cr.precommit.run()
        for bus_event in self.env['bus.bus'].sudo().search([]):
            message = json.loads(bus_event.message)
            if (message.get('type') == 'odupilot.session/status'
                    and message['payload']['session_id'] == session.id):
                notifications.append(message['payload'])

        self.assertTrue(notifications)
        self.assertEqual(notifications[-1], {
            'channel_id': session.channel_id.id,
            'session_id': session.id,
            'agent_id': session.agent_id.id,
            'agent_name': session.agent_id.name,
            'state': 'error',
            'discuss_only': False,
            'error': 'The model endpoint is unavailable.',
        })

    def test_mcp_configuration_validation(self):
        with self.assertRaises(ValidationError):
            self.env['odupilot.mcp.server'].create({
                'name': 'Invalid remote',
                'code': 'invalid remote',
                'server_type': 'remote',
                'url': 'not-a-url',
            })
        with self.assertRaises(ValidationError):
            self.env['odupilot.mcp.server'].create({
                'name': 'Invalid headers',
                'code': 'invalid-headers',
                'server_type': 'remote',
                'url': 'https://mcp.example.com/mcp',
                'headers_json': '{"Authorization": 123}',
            })
        with self.assertRaises(ValidationError):
            self.env['odupilot.mcp.server'].create({
                'name': 'Invalid local',
                'code': 'invalid-local',
                'server_type': 'local',
                'command_json': '[]',
            })

        local = self.env['odupilot.mcp.server'].create({
            'name': 'Local tools',
            'code': 'local-tools',
            'server_type': 'local',
            'command_json': '["npx", "-y", "mcp-package"]',
            'cwd': 'tools',
            'environment_json': '{"LOG_LEVEL": "info"}',
        })
        self.assertEqual(local._opencode_config(), {
            'type': 'local',
            'enabled': True,
            'timeout': 5000,
            'command': ['npx', '-y', 'mcp-package'],
            'cwd': 'tools',
            'environment': {'LOG_LEVEL': 'info'},
        })

    def test_developer_session_creates_random_worktree(self):
        profile = self.env['odupilot.profile'].sudo().create({
            'name': 'Developer',
            'code': 'developer-test',
            'workspace_type': 'worktree',
            'model': 'test-model',
            'litellm_api_key': 'developer-litellm-key',
            'max_sessions': 2,
            'developer_repo_url': 'https://github.com/example/developers.git',
            'developer_github_pat': 'github-test-pat',
            'developer_base_branch': 'prod',
            'developer_environment_mcp_server_id': self.mcp_server.id,
            'developer_environment_template_name': 'prod',
            'developer_environment_odoo_image': 'odoo15_veles',
            'developer_bootstrap_prompt': 'Use the isolated test slot.',
        })
        self._attach_agent(
            profile, 'developer-test', ruleset_json='{"bash": "allow"}')
        developer = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': 'OduPilot Developer',
                'login': 'odupilot_developer',
                'email': 'odupilot-developer@example.com',
                'groups_id': [Command.set([
                    self.env.ref('base.group_system').id,
                ])],
                'odupilot_profile_id': profile.id,
            })
        self.env['odupilot.session'].with_user(
            developer).action_new_chat()

        session = self.env['odupilot.session'].sudo().search([
            ('user_id', '=', developer.id),
        ], order='id desc', limit=1)
        self.assertRegex(session.branch, r'^[a-z]+-[a-z]+$')
        # Ветка разработческого чата видна прямо в названии разговора.
        self.assertEqual(
            session.channel_id.name, 'Developer - OD (%s)' % session.branch)
        self.assertEqual(
            session.directory,
            os.path.join(self.workspace, 'worktrees', session.branch),
        )
        self.assertEqual(
            session.repository_directory,
            os.path.join(self.workspace, 'repo', 'profile_%s' % profile.id),
        )
        self.assertFalse(os.path.exists(session.directory))
        claimed = self.env['odupilot.command'].bridge_claim(10)
        workspace = claimed[0]['workspace']
        self.assertEqual(workspace['repo_url'], profile.developer_repo_url)
        self.assertEqual(workspace['github_pat'], 'github-test-pat')
        self.assertEqual(workspace['base_branch'], 'prod')
        bootstrap = self.env['odupilot.command'].sudo().search([
            ('session_id', '=', session.id),
            ('external_id', '=', 'bootstrap:%s' % session.id),
        ])
        self.assertEqual(bootstrap.command_type, 'prompt')
        bootstrap_payload = json.loads(bootstrap.payload)
        self.assertIn('company-tools', bootstrap_payload['system'])
        self.assertIn('odoo15_veles', bootstrap_payload['system'])
        self.assertIn(session.branch, bootstrap_payload['system'])
        self.assertIn('Use the isolated test slot.', bootstrap_payload['system'])

        self.env['odupilot.command'].bridge_ack(
            claimed[0]['id'], True, {'id': 'ses_developer'}, '')
        bootstrap_claim = self.env['odupilot.command'].bridge_claim(10)[0]
        self.assertEqual(bootstrap_claim['id'], bootstrap.id)
        self.assertIn('company-tools', bootstrap_claim['opencode_config']['mcp'])
        self.env['odupilot.command'].bridge_ack(
            bootstrap.id, True, {}, '')

        event = self.env['odupilot.event'].sudo().create({
            'session_id': session.id,
            'event_type': 'bridge.backfill.message',
            'payload': '{}',
            'external_id': 'message:developer-ready',
            'execution_user_id': developer.id,
        })
        session._post_assistant_message(event, {
            'info': {'id': 'msg_developer_ready', 'role': 'assistant'},
            'parts': [{
                'type': 'text',
                'text': (
                    'Environment ready.\n'
                    'ODUPILOT_ENVIRONMENT_URL=https://test-slot.example.com\n'
                    'Implementation complete.\n'
                    'ODUPILOT_PUBLISH_REQUEST={"title":"Test change",'
                    '"body":"Verified developer workflow."}'),
            }],
        })
        self.assertEqual(
            session.env_url, 'https://test-slot.example.com')
        self.assertNotIn(
            'ODUPILOT_ENVIRONMENT_URL', event.mail_message_id.body)
        self.assertNotIn(
            'ODUPILOT_PUBLISH_REQUEST', event.mail_message_id.body)
        publish = self.env['odupilot.command'].sudo().search([
            ('session_id', '=', session.id),
            ('command_type', '=', 'publish'),
        ])
        self.assertEqual(json.loads(publish.payload), {
            'title': 'Test change',
            'body': 'Verified developer workflow.',
        })
        publish_claim = self.env['odupilot.command'].bridge_claim(10)[0]
        self.assertEqual(publish_claim['id'], publish.id)
        self.assertEqual(
            publish_claim['workspace']['github_pat'], 'github-test-pat')
        self.env['odupilot.command'].bridge_ack(publish.id, True, {
            'branch_url': 'https://github.com/example/developers/tree/test',
            'pull_request_url': 'https://github.com/example/developers/pull/1',
        }, '')
        self.assertEqual(
            session.pull_request_url,
            'https://github.com/example/developers/pull/1')

    def test_developer_chat_is_kept_out_of_docked_windows(self):
        profile = self.env['odupilot.profile'].sudo().create({
            'name': 'Developer windows',
            'code': 'developer-windows',
            'workspace_type': 'worktree',
            'model': 'test-model',
            'litellm_api_key': 'developer-litellm-key',
            'max_sessions': 2,
            'developer_repo_url': 'https://github.com/example/developers.git',
            'developer_github_pat': 'github-test-pat',
            'developer_base_branch': 'prod',
        })
        self._attach_agent(
            profile, 'developer-windows',
            ruleset_json='{"bash": "allow"}')
        developer = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': 'OduPilot Windows Developer',
                'login': 'odupilot_windows_developer',
                'email': 'odupilot-windows-developer@example.com',
                'groups_id': [Command.set([
                    self.env.ref('base.group_system').id,
                ])],
                'odupilot_profile_id': profile.id,
            })
        self.env['odupilot.session'].with_user(developer).action_new_chat()
        session = self.env['odupilot.session'].sudo().search([
            ('user_id', '=', developer.id),
        ], order='id desc', limit=1)

        # Разработчик мог свернуть окно ещё до перевода профиля в worktree.
        channel_info = session.channel_id.with_user(
            developer).channel_info()[0]

        self.assertTrue(channel_info['odupilot_session']['discuss_only'])
        self.assertFalse(channel_info['is_minimized'])
        self.assertEqual(channel_info['state'], 'closed')

    def test_developer_profile_configuration_validation(self):
        values = {
            'name': 'Invalid developer',
            'code': 'invalid-developer',
            'workspace_type': 'worktree',
            'model': 'test-model',
        }
        with self.assertRaises(ValidationError):
            self.env['odupilot.profile'].sudo().create(dict(
                values, developer_repo_url='http://example.com/repository.git'))
        with self.assertRaises(ValidationError):
            self.env['odupilot.profile'].sudo().create(dict(
                values, developer_base_branch='invalid branch'))
        with self.assertRaises(ValidationError):
            self.env['odupilot.profile'].sudo().create(dict(
                values, developer_github_pat='invalid\ntoken'))
        with self.assertRaises(ValidationError):
            self.env['odupilot.profile'].sudo().create(dict(
                values,
                workspace_type='files',
                developer_environment_mcp_server_id=self.mcp_server.id,
            ))

    def test_single_human_routes_every_message(self):
        session = self._new_session()

        message = self._post(
            session.channel_id, self.owner, '<p>Check this order.</p>')

        command = self.env['odupilot.command'].sudo().search([
            ('source_message_id', '=', message.id),
        ])
        self.assertEqual(len(command), 1)
        self.assertEqual(command.user_id, self.owner)
        payload = json.loads(command.payload)
        self.assertEqual(payload['actor_user_id'], self.owner.id)
        self.assertEqual(payload['owner_user_id'], self.owner.id)

    def test_attachment_content_is_transferred_in_prompt_command(self):
        session = self._new_session()
        attachment = self.env['ir.attachment'].with_user(self.owner).create({
            'name': 'report 2026.txt',
            'type': 'binary',
            'datas': base64.b64encode(b'report body'),
            'res_model': 'discuss.channel',
            'res_id': session.channel_id.id,
        })

        message = session.channel_id.with_user(self.owner).message_post(
            body='<p>Read the report.</p>',
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
            attachment_ids=[attachment.id],
        )

        command = self.env['odupilot.command'].sudo().search([
            ('source_message_id', '=', message.id),
        ])
        payload = json.loads(command.payload)
        self.assertEqual(len(payload['attachments']), 1)
        self.assertEqual(
            payload['attachments'][0]['path'],
            'attachments/message_%s/report_2026.txt' % message.id,
        )
        self.assertEqual(
            base64.b64decode(payload['attachments'][0]['data']),
            b'report body',
        )
        self.assertIn('AnyDoc', payload['system'])

    def test_prompt_without_attachment_omits_anydoc_instructions(self):
        session = self._new_session()

        message = self._post(
            session.channel_id, self.owner, '<p>Plain question.</p>')

        command = self.env['odupilot.command'].sudo().search([
            ('source_message_id', '=', message.id),
        ])
        payload = json.loads(command.payload)
        self.assertNotIn('AnyDoc', payload['system'])

    def test_group_allows_human_messages_but_only_owner_can_invoke_agent(self):
        session = self._new_session()
        bot = self.env.ref('odupilot.partner_ai_bot')
        session.channel_id.with_user(self.owner).add_members(
            partner_ids=[self.invited.partner_id.id])

        ignored = self._post(
            session.channel_id, self.invited, '<p>Human-only message.</p>')
        with self.assertRaises(AccessError):
            self._post(
                session.channel_id,
                self.invited,
                '<p><a data-oe-id="%s" data-oe-model="res.partner">@AI</a> check it.</p>' % bot.id,
                partner_ids=[bot.id],
            )

        self.assertFalse(self.env['odupilot.command'].sudo().search([
            ('source_message_id', '=', ignored.id),
        ]))
        self.assertFalse(self.env['odupilot.command'].sudo().search([
            ('session_id', '=', session.id),
            ('user_id', '=', self.invited.id),
        ]))

    def test_invited_user_cannot_reshare_chat(self):
        session = self._new_session()
        session.channel_id.with_user(self.owner).add_members(
            partner_ids=[self.invited.partner_id.id])

        with self.assertRaises(AccessError):
            session.channel_id.with_user(self.invited).add_members(
                partner_ids=[self.outsider.partner_id.id])

    def test_revoked_profile_key_blocks_owner_prompt(self):
        session = self._new_session()
        bot = self.env.ref('odupilot.partner_ai_bot')
        session.channel_id.with_user(self.owner).add_members(
            partner_ids=[self.invited.partner_id.id])
        self.profile.sudo().litellm_api_key = False

        message = self._post(
            session.channel_id,
            self.owner,
            '<p>@AI should fail.</p>',
            partner_ids=[bot.id],
        )

        self.assertFalse(self.env['odupilot.command'].sudo().search([
            ('source_message_id', '=', message.id),
        ]))
        self.assertEqual(session.state, 'error')

    def test_owner_leave_closes_session_and_enqueues_cleanup(self):
        session = self._new_session()
        directory = session.directory

        session.channel_id.with_user(self.owner).action_unfollow()

        self.assertEqual(session.state, 'closed')
        self.assertNotIn(
            self.owner.partner_id,
            session.channel_id.with_context(active_test=False).channel_partner_ids)
        close_command = self.env['odupilot.command'].sudo().search([
            ('session_id', '=', session.id),
            ('command_type', '=', 'close'),
        ])
        self.assertEqual(len(close_command), 1)
        self.assertFalse(os.path.exists(directory))
        claimed = self.env['odupilot.command'].bridge_claim(10)
        self.assertEqual(claimed[0]['command_type'], 'close')
        self.env['odupilot.command'].bridge_ack(
            close_command.id, True, {}, '')
        self.assertFalse(os.path.exists(directory))

        message = self._post(
            session.channel_id, self.env.user, '<p>Closed chat note.</p>')
        self.assertFalse(self.env['odupilot.command'].sudo().search([
            ('source_message_id', '=', message.id),
        ]))

    def test_invited_user_can_leave_without_closing_session(self):
        session = self._new_session()
        session.channel_id.with_user(self.owner).add_members(
            partner_ids=[self.invited.partner_id.id])

        session.channel_id.with_user(self.invited).action_unfollow()

        self.assertNotEqual(session.state, 'closed')
        self.assertNotIn(
            self.invited.partner_id,
            session.channel_id.with_context(active_test=False).channel_partner_ids)

    def test_bot_cannot_leave_active_session(self):
        session = self._new_session()
        bot = self.env.ref('odupilot.partner_ai_bot')

        with self.assertRaises(ValidationError):
            session.channel_id.sudo()._action_unfollow(bot)

    def test_outsider_cannot_read_session(self):
        session = self._new_session()

        with self.assertRaises(AccessError):
            session.with_user(self.outsider).read(['state'])

    def test_bridge_claim_is_fifo_and_uses_async_prompt_data(self):
        session = self._new_session()
        message = self._post(
            session.channel_id, self.owner, '<p>First prompt.</p>')

        claimed_init = self.env['odupilot.command'].bridge_claim(10)
        self.assertEqual(len(claimed_init), 1)
        self.assertEqual(claimed_init[0]['command_type'], 'init')
        self.assertEqual(claimed_init[0]['attempts'], 1)
        self.env['odupilot.command'].bridge_ack(
            claimed_init[0]['id'], True, {'id': 'ses_test'}, '')
        claimed_prompt = self.env['odupilot.command'].bridge_claim(10)

        self.assertEqual(len(claimed_prompt), 1)
        self.assertEqual(claimed_prompt[0]['command_type'], 'prompt')
        self.assertEqual(claimed_prompt[0]['model'], 'test-model')
        self.assertEqual(
            claimed_prompt[0]['payload']['actor_user_id'], self.owner.id)
        self.assertEqual(
            claimed_prompt[0]['payload']['message_id'],
            json.loads(self.env['odupilot.command'].sudo().search([
                ('source_message_id', '=', message.id),
            ]).payload)['message_id'])

    def test_deleted_session_still_asks_the_bridge_to_remove_its_files(self):
        session = self._new_session()
        directory = session.directory
        init = self.env['odupilot.command'].bridge_claim(10)[0]
        self.env['odupilot.command'].bridge_ack(
            init['id'], True, {'id': 'ses_removed'}, '')
        self._post(session.channel_id, self.owner, '<p>Prompt.</p>')

        session.sudo().unlink()

        commands = self.env['odupilot.command'].sudo().search([
            ('session_id', '=', False),
        ])
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands.command_type, 'close')
        claimed = self.env['odupilot.command'].bridge_claim(10)
        self.assertEqual(len(claimed), 1)
        self.assertEqual(claimed[0]['command_type'], 'close')
        self.assertEqual(claimed[0]['directory'], directory)
        self.assertEqual(claimed[0]['opencode_session_id'], 'ses_removed')
        self.assertEqual(claimed[0]['workspace']['directory'], directory)
        self.assertEqual(claimed[0]['workspace']['type'], 'files')
        self.env['odupilot.command'].bridge_ack(claimed[0]['id'], True, {}, '')
        self.assertEqual(commands.state, 'done')

    def test_closed_session_is_not_cleaned_up_twice_on_delete(self):
        session = self._new_session()
        init = self.env['odupilot.command'].bridge_claim(10)[0]
        self.env['odupilot.command'].bridge_ack(
            init['id'], True, {'id': 'ses_closed'}, '')
        session.with_user(self.owner).action_close()
        close = self.env['odupilot.command'].bridge_claim(10)[0]
        self.env['odupilot.command'].bridge_ack(close['id'], True, {}, '')

        session.sudo().unlink()

        remaining = self.env['odupilot.command'].sudo().search([
            ('session_id', '=', False),
        ])
        self.assertEqual(remaining.ids, [close['id']])
        self.assertEqual(remaining.state, 'done')
        self.assertFalse(self.env['odupilot.command'].bridge_claim(10))

    def test_retention_removes_finished_orphan_commands(self):
        session = self._new_session()
        self.env['odupilot.command'].bridge_claim(10)
        session.sudo().unlink()
        orphan = self.env['odupilot.command'].sudo().search([
            ('session_id', '=', False),
        ])
        orphan.write({'state': 'done'})
        self.env.cr.execute(
            'UPDATE odupilot_command SET create_date = %s WHERE id = %s',
            (fields.Datetime.now() - timedelta(days=200), orphan.id))
        orphan.invalidate_recordset(['create_date'])

        result = self.env['odupilot.session'].sudo()._cron_apply_retention()

        self.assertEqual(result['commands'], 1)
        self.assertFalse(orphan.exists())

    def test_failed_bridge_ack_returns_retry_deadline(self):
        self._new_session()
        command = self.env['odupilot.command'].bridge_claim(10)[0]

        acknowledgement = self.env['odupilot.command'].bridge_ack(
            command['id'], False, {}, 'Temporary failure')

        record = self.env['odupilot.command'].sudo().browse(command['id'])
        self.assertEqual(acknowledgement, {'retry_after': 2})
        self.assertEqual(record.state, 'pending')
        self.assertTrue(record.next_attempt_at)

    def test_bridge_sessions_expose_busy_since_for_reconciliation(self):
        session = self._new_session()
        init = self.env['odupilot.command'].bridge_claim(10)[0]
        self.env['odupilot.command'].bridge_ack(
            init['id'], True, {'id': 'ses_reconcile'}, '')
        self._post(session.channel_id, self.owner, '<p>Long prompt.</p>')
        prompt = self.env['odupilot.command'].bridge_claim(10)[0]
        self.env['odupilot.command'].bridge_ack(prompt['id'], True, {}, '')

        published = [
            item for item in self.env['odupilot.session'].bridge_sessions()
            if item['opencode_session_id'] == 'ses_reconcile'
        ]

        self.assertEqual(len(published), 1)
        self.assertEqual(published[0]['state'], 'busy')
        self.assertEqual(
            published[0]['busy_since'],
            fields.Datetime.to_string(session.busy_since))

    def test_bridge_endpoints_reject_administrators_without_the_group(self):
        administrator = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': 'OduPilot Administrator',
                'login': 'odupilot_administrator',
                'groups_id': [Command.set([
                    self.env.ref('base.group_system').id])],
            })
        self._new_session()

        with self.assertRaises(AccessError):
            self.env['odupilot.command'].with_user(
                administrator).bridge_claim(10)
        with self.assertRaises(AccessError):
            self.env['odupilot.session'].with_user(
                administrator).bridge_sessions()
        with self.assertRaises(AccessError):
            self.env['odupilot.runtime'].with_user(
                administrator).bridge_heartbeat({})

    def test_bridge_service_account_needs_no_administrator_rights(self):
        session = self._new_session()
        self.assertFalse(self.bridge.has_group('base.group_system'))

        commands = self.env['odupilot.command'].with_user(self.bridge)
        init = commands.bridge_claim(10)[0]
        commands.bridge_ack(init['id'], True, {'id': 'ses_service'}, '')
        self._post(session.channel_id, self.owner, '<p>Service prompt.</p>')
        prompt = commands.bridge_claim(10)[0]
        commands.bridge_ack(prompt['id'], True, {}, '')
        created = self.env['odupilot.session'].with_user(
            self.bridge).ingest_events([{
                'opencode_session_id': 'ses_service',
                'event_type': 'session.idle',
                'external_id': 'bridge.service.idle:ses_service',
                'payload': {
                    'type': 'session.idle',
                    'properties': {'sessionID': 'ses_service'},
                },
            }])
        heartbeat = self.env['odupilot.runtime'].with_user(
            self.bridge).bridge_heartbeat({'opencode_healthy': True})
        published = self.env['odupilot.session'].with_user(
            self.bridge).bridge_sessions()

        # Секреты деплоя мост получает через sudo внутри метода, а не правами
        # своей записи: PAT и ключ LiteLLM закрыты полями group_system.
        self.assertEqual(
            init['opencode_config']['provider']['litellm'][
                'options']['apiKey'], 'profile-litellm-key')
        self.assertEqual(created, 1)
        self.assertTrue(heartbeat['heartbeat_at'])
        self.assertIn('ses_service', [
            item['opencode_session_id'] for item in published])
        self.assertEqual(session.state, 'ready')

    def test_reconciled_idle_event_releases_a_stuck_busy_session(self):
        session = self._new_session()
        init = self.env['odupilot.command'].bridge_claim(10)[0]
        self.env['odupilot.command'].bridge_ack(
            init['id'], True, {'id': 'ses_stuck'}, '')
        self._post(session.channel_id, self.owner, '<p>Lost answer.</p>')
        prompt = self.env['odupilot.command'].bridge_claim(10)[0]
        self.env['odupilot.command'].bridge_ack(prompt['id'], True, {}, '')
        self.assertEqual(session.state, 'busy')

        # Мост шлёт такой конверт, когда SSE переподключился, а OpenCode эту
        # сессию уже не выполняет.
        self.env['odupilot.session'].ingest_events([{
            'opencode_session_id': 'ses_stuck',
            'event_type': 'session.idle',
            'external_id': 'bridge.reconcile.idle:ses_stuck:%s' % (
                fields.Datetime.to_string(session.busy_since)),
            'payload': {
                'type': 'session.idle',
                'properties': {'sessionID': 'ses_stuck'},
                'bridge_reconciled': True,
            },
        }])

        self.assertEqual(session.state, 'ready')
        self.assertFalse(session.busy_since)

    def test_retried_admitted_prompt_keeps_completed_session_ready(self):
        session = self._new_session()
        init = self.env['odupilot.command'].bridge_claim(10)[0]
        self.env['odupilot.command'].bridge_ack(
            init['id'], True, {'id': 'ses_retry_test'}, '')
        self._post(session.channel_id, self.owner, '<p>Accepted prompt.</p>')
        prompt = self.env['odupilot.command'].bridge_claim(10)[0]

        self.env['odupilot.command'].bridge_ack(prompt['id'], True, {
            'already_admitted': True,
            'session_busy': False,
        }, '')

        self.assertEqual(session.state, 'ready')
        self.assertFalse(session.busy_since)

    def test_retried_admitted_prompt_tracks_active_session_as_busy(self):
        session = self._new_session()
        init = self.env['odupilot.command'].bridge_claim(10)[0]
        self.env['odupilot.command'].bridge_ack(
            init['id'], True, {'id': 'ses_active_retry_test'}, '')
        self._post(session.channel_id, self.owner, '<p>Active prompt.</p>')
        prompt = self.env['odupilot.command'].bridge_claim(10)[0]

        self.env['odupilot.command'].bridge_ack(prompt['id'], True, {
            'already_admitted': True,
            'session_busy': True,
        }, '')

        self.assertEqual(session.state, 'busy')
        self.assertTrue(session.busy_since)

    def test_busy_watchdog_auto_retries_request_without_tool_activity(self):
        session = self._new_session()
        init = self.env['odupilot.command'].bridge_claim(10)[0]
        self.env['odupilot.command'].bridge_ack(
            init['id'], True, {'id': 'ses_watchdog'}, '')
        self._post(session.channel_id, self.owner, '<p>Long request.</p>')
        prompt = self.env['odupilot.command'].bridge_claim(10)[0]
        self.env['odupilot.command'].bridge_ack(
            prompt['id'], True, {}, '')
        queued_message = self._post(
            session.channel_id, self.owner, '<p>Queued request.</p>')
        session.busy_since = fields.Datetime.now() - timedelta(minutes=31)

        recovered = self.env['odupilot.session']._cron_watchdog_busy_sessions()

        queued = self.env['odupilot.command'].sudo().search([
            ('source_message_id', '=', queued_message.id),
        ])
        abort = self.env['odupilot.command'].sudo().search([
            ('session_id', '=', session.id),
            ('command_type', '=', 'abort'),
        ])
        event = self.env['odupilot.event'].sudo().search([
            ('session_id', '=', session.id),
            ('event_type', '=', 'session.watchdog.timeout'),
        ])
        self.assertEqual(recovered, 1)
        self.assertEqual(session.state, 'error')
        self.assertFalse(session.busy_since)
        self.assertEqual(queued.state, 'error')
        self.assertIn('previous AI request timed out', queued.error)
        self.assertEqual(len(abort), 1)
        self.assertEqual(abort.state, 'pending')
        self.assertEqual(len(event), 1)
        recovery = self.env['odupilot.recovery'].sudo().search([
            ('failed_command_id', '=', prompt['id']),
        ])
        self.assertEqual(len(recovery), 1)
        self.assertEqual(recovery.status, 'auto_retrying')
        self.assertFalse(recovery.had_tool_activity)
        self.assertFalse(recovery.mail_message_id)
        self.assertTrue(recovery.retry_command_id)
        self.assertEqual(recovery.retry_command_id.state, 'pending')

        claimed_abort = self.env['odupilot.command'].bridge_claim(10)[0]
        self.assertEqual(claimed_abort['command_type'], 'abort')
        self.env['odupilot.command'].bridge_ack(
            claimed_abort['id'], True, {}, '')
        claimed_retry = self.env['odupilot.command'].bridge_claim(10)[0]
        self.assertEqual(claimed_retry['command_type'], 'prompt')
        self.assertEqual(claimed_retry['payload']['text'], 'Long request.')
        self.assertNotEqual(
            claimed_retry['payload']['message_id'],
            prompt['payload']['message_id'],
        )

    def test_busy_watchdog_requires_decision_after_tool_activity(self):
        session = self._new_session()
        init = self.env['odupilot.command'].bridge_claim(10)[0]
        self.env['odupilot.command'].bridge_ack(
            init['id'], True, {'id': 'ses_watchdog_tool'}, '')
        self._post(session.channel_id, self.owner, '<p>Change data.</p>')
        prompt = self.env['odupilot.command'].bridge_claim(10)[0]
        self.env['odupilot.command'].bridge_ack(prompt['id'], True, {}, '')
        self.env['odupilot.session'].ingest_events([{
            'opencode_session_id': session.opencode_session_id,
            'event_type': 'message.part.updated',
            'external_id': 'watchdog:tool:part',
            'payload': {
                'payload': {
                    'type': 'message.part.updated',
                    'properties': {
                        'sessionID': session.opencode_session_id,
                        'part': {
                            'id': 'prt_tool',
                            'messageID': 'msg_assistant_tool',
                            'type': 'tool',
                            'tool': 'edit',
                        },
                    },
                },
            },
        }])
        session.busy_since = fields.Datetime.now() - timedelta(minutes=31)

        self.env['odupilot.session']._cron_watchdog_busy_sessions()

        recovery = self.env['odupilot.recovery'].sudo().search([
            ('failed_command_id', '=', prompt['id']),
        ])
        self.assertEqual(recovery.status, 'pending')
        self.assertTrue(recovery.had_tool_activity)
        self.assertTrue(recovery.mail_message_id)
        self.assertFalse(recovery.retry_command_id)
        formatted = recovery.mail_message_id.with_user(
            self.owner).message_format()[0]
        self.assertEqual(
            formatted['odupilot_recovery']['status'], 'pending')
        abort = self.env['odupilot.command'].bridge_claim(10)[0]
        self.assertEqual(abort['command_type'], 'abort')
        self.env['odupilot.command'].bridge_ack(abort['id'], True, {}, '')
        self.assertEqual(session.state, 'error')

        result = recovery.with_user(self.owner).action_reply('retry')

        self.assertEqual(result['status'], 'retrying')
        self.assertTrue(recovery.retry_command_id)
        self.assertEqual(recovery.resolved_by_id, self.owner)
        self.assertEqual(session.state, 'ready')
        retry = self.env['odupilot.command'].bridge_claim(10)[0]
        self.assertEqual(retry['id'], recovery.retry_command_id.id)

    def test_recovery_can_be_dismissed_without_replaying_prompt(self):
        session = self._new_session()
        init = self.env['odupilot.command'].bridge_claim(10)[0]
        self.env['odupilot.command'].bridge_ack(
            init['id'], True, {'id': 'ses_watchdog_dismiss'}, '')
        self._post(session.channel_id, self.owner, '<p>Risky request.</p>')
        prompt = self.env['odupilot.command'].bridge_claim(10)[0]
        self.env['odupilot.command'].bridge_ack(prompt['id'], True, {}, '')
        session.write({
            'active_prompt_has_tool_activity': True,
            'busy_since': fields.Datetime.now() - timedelta(minutes=31),
        })
        self.env['odupilot.session']._cron_watchdog_busy_sessions()
        recovery = self.env['odupilot.recovery'].sudo().search([
            ('failed_command_id', '=', prompt['id']),
        ])
        abort = self.env['odupilot.command'].bridge_claim(10)[0]
        self.env['odupilot.command'].bridge_ack(abort['id'], True, {}, '')
        self.assertEqual(session.state, 'error')

        result = recovery.with_user(self.owner).action_reply('dismiss')

        self.assertEqual(result['status'], 'dismissed')
        self.assertFalse(recovery.retry_command_id)
        self.assertEqual(recovery.resolved_by_id, self.owner)
        self.assertEqual(session.state, 'ready')

    def test_late_final_answer_cancels_pending_recovery_commands(self):
        session = self._new_session()
        init = self.env['odupilot.command'].bridge_claim(10)[0]
        self.env['odupilot.command'].bridge_ack(
            init['id'], True, {'id': 'ses_watchdog_late_final'}, '')
        self._post(session.channel_id, self.owner, '<p>Slow request.</p>')
        prompt = self.env['odupilot.command'].bridge_claim(10)[0]
        self.env['odupilot.command'].bridge_ack(prompt['id'], True, {}, '')
        session.busy_since = fields.Datetime.now() - timedelta(minutes=31)
        self.env['odupilot.session']._cron_watchdog_busy_sessions()
        recovery = self.env['odupilot.recovery'].sudo().search([
            ('failed_command_id', '=', prompt['id']),
        ])

        self.env['odupilot.session'].ingest_events([{
            'opencode_session_id': session.opencode_session_id,
            'event_type': 'bridge.backfill.message',
            'external_id': 'message:msg_late_recovered',
            'payload': {
                'info': {
                    'id': 'msg_late_recovered',
                    'role': 'assistant',
                    'time': {'completed': 1},
                },
                'parts': [{
                    'type': 'text',
                    'text': 'Late answer arrived exactly once.',
                }],
            },
        }])

        self.assertEqual(recovery.status, 'completed')
        self.assertEqual(recovery.abort_command_id.state, 'error')
        self.assertEqual(recovery.retry_command_id.state, 'error')
        self.assertEqual(session.state, 'ready')
        messages = session.channel_id.message_ids.filtered(
            lambda message: 'Late answer arrived exactly once.' in
            (message.body or ''))
        self.assertEqual(len(messages), 1)

    def test_interrupted_retry_never_loops_automatic_recovery(self):
        session = self._new_session()
        init = self.env['odupilot.command'].bridge_claim(10)[0]
        self.env['odupilot.command'].bridge_ack(
            init['id'], True, {'id': 'ses_watchdog_retry_limit'}, '')
        self._post(session.channel_id, self.owner, '<p>Unstable request.</p>')
        prompt = self.env['odupilot.command'].bridge_claim(10)[0]
        self.env['odupilot.command'].bridge_ack(prompt['id'], True, {}, '')
        session.busy_since = fields.Datetime.now() - timedelta(minutes=31)
        self.env['odupilot.session']._cron_watchdog_busy_sessions()
        first = self.env['odupilot.recovery'].sudo().search([
            ('failed_command_id', '=', prompt['id']),
        ])
        abort = self.env['odupilot.command'].bridge_claim(10)[0]
        self.env['odupilot.command'].bridge_ack(abort['id'], True, {}, '')
        retry = self.env['odupilot.command'].bridge_claim(10)[0]
        self.env['odupilot.command'].bridge_ack(retry['id'], True, {}, '')
        session.busy_since = fields.Datetime.now() - timedelta(minutes=31)

        self.env['odupilot.session']._cron_watchdog_busy_sessions()

        second = self.env['odupilot.recovery'].sudo().search([
            ('failed_command_id', '=', retry['id']),
        ])
        self.assertEqual(first.status, 'auto_retrying')
        self.assertEqual(second.status, 'pending')
        self.assertFalse(second.had_tool_activity)
        self.assertTrue(second.mail_message_id)
        self.assertFalse(second.retry_command_id)

    def test_busy_timeout_must_be_positive(self):
        with self.assertRaises(ValidationError):
            self.env['res.config.settings'].create({
                'odupilot_busy_timeout_minutes': 0,
            })

    def test_ingest_events_is_idempotent(self):
        session = self._new_session()
        session.write({
            'opencode_session_id': 'ses_ingest_test',
            'state': 'busy',
        })
        values = [{
            'opencode_session_id': session.opencode_session_id,
            'event_type': 'bridge.backfill.message',
            'external_id': 'message:msg_assistant_test',
            'payload': {
                'info': {
                    'id': 'msg_assistant_test',
                    'role': 'assistant',
                    'time': {'completed': 1},
                },
                'parts': [{'type': 'text', 'text': 'Finished answer.'}],
            },
        }]

        first = self.env['odupilot.session'].ingest_events(values)
        second = self.env['odupilot.session'].ingest_events(values)

        self.assertEqual(first, 1)
        self.assertEqual(second, 0)
        event = self.env['odupilot.event'].sudo().search([
            ('session_id', '=', session.id),
            ('external_id', '=', 'message:msg_assistant_test'),
        ])
        self.assertEqual(len(event), 1)
        self.assertTrue(event.mail_message_id)
        self.assertEqual(session.state, 'ready')

    def test_provider_retry_is_reported_in_the_channel_once(self):
        session = self._new_session()
        session.write({
            'opencode_session_id': 'ses_retry_test',
            'state': 'busy',
        })

        def retry_event(external_id, message):
            return {
                'opencode_session_id': session.opencode_session_id,
                'event_type': 'session.status',
                'external_id': external_id,
                'payload': {
                    'payload': {
                        'type': 'session.status',
                        'properties': {
                            'sessionID': session.opencode_session_id,
                            'status': {
                                'type': 'retry',
                                'attempt': 1,
                                'message': message,
                            },
                        },
                    },
                },
            }

        limit_reached = (
            'litellm.RateLimitError: The usage limit has been reached\n'
            'Received Model Group=test-model'
        )
        self.env['odupilot.session'].ingest_events([
            retry_event('session.status:retry-1', limit_reached),
            retry_event('session.status:retry-2', limit_reached),
        ])

        notices = session.channel_id.message_ids.filtered(
            lambda message: 'being retried' in (message.body or ''))
        self.assertEqual(len(notices), 1)
        self.assertIn('The usage limit has been reached', notices.body)
        # Многострочный текст провайдера обрезается до первой строки.
        self.assertNotIn('Received Model Group', notices.body)

        # Одна и та же причина приезжает с меняющимися числами — моментом
        # сброса лимита и остатком секунд. Это по-прежнему одна причина.
        self.env['res.lang']._activate_lang('en_US')
        self.owner.write({'lang': 'en_US', 'tz': 'Europe/Warsaw'})
        usage_limit = (
            'litellm.RateLimitError: ChatgptException - '
            '{"error":{"type":"usage_limit_reached",'
            '"message":"The usage limit has been reached",'
            '"plan_type":"pro","resets_at":%s,'
            '"resets_in_seconds":%s}}. Received Model Group=test-model'
        )
        self.env['odupilot.session'].ingest_events([
            retry_event(
                'session.status:retry-3',
                usage_limit % (1787197124, 152161)),
            retry_event(
                'session.status:retry-4',
                usage_limit % (1787197123, 152152)),
            retry_event(
                'session.status:retry-5',
                usage_limit % (1787197124, 152142)),
        ])
        notices = session.channel_id.message_ids.filtered(
            lambda message: 'being retried' in (message.body or ''))
        self.assertEqual(len(notices), 1)
        usage_notices = session.channel_id.message_ids.filtered(
            lambda message: 'The AI usage limit has been reached' in (
                message.body or ''))
        self.assertEqual(len(usage_notices), 1)
        notice_body = usage_notices.body.replace('\u202f', ' ')
        language = self.env['res.lang']._lang_get('en_US')
        expected = datetime(2026, 8, 20, 5, 38, 44).strftime(
            language.date_format + ' ' + language.time_format)
        self.assertIn(expected, notice_body)
        self.assertIn('Europe/Warsaw', usage_notices.body)
        self.assertNotIn('resets_at', usage_notices.body)
        self.assertNotIn('RateLimitError', usage_notices.body)

        # Причина изменилась — пользователь должен узнать и об этом.
        self.env['odupilot.session'].ingest_events([
            retry_event('session.status:retry-6', 'Connection reset by peer'),
        ])
        notices = session.channel_id.message_ids.filtered(
            lambda message: 'being retried' in (message.body or ''))
        self.assertEqual(len(notices), 2)

        self.env['odupilot.session'].ingest_events([{
            'opencode_session_id': session.opencode_session_id,
            'event_type': 'session.idle',
            'external_id': 'session.idle:retry-test',
            'payload': {
                'payload': {
                    'type': 'session.idle',
                    'properties': {
                        'sessionID': session.opencode_session_id,
                    },
                },
            },
        }])

        self.assertEqual(session.state, 'ready')
        self.assertFalse(session.retry_notice)

    def test_usage_limit_retry_without_reset_is_human_readable(self):
        session = self._new_session()
        reason = (
            'litellm.RateLimitError: ChatgptException - '
            '{"error":{"type":"usage_limit_reached",'
            '"message":"The usage limit has been reached"}}'
        )

        notice = session._format_retry_notice({'message': reason})

        self.assertEqual(
            notice,
            'The AI usage limit has been reached. The provider will retry '
            'automatically.',
        )
        self.assertNotIn('RateLimitError', notice)

    def test_permission_event_creates_discuss_card_and_outbox_reply(self):
        session = self._new_session()
        init = self.env['odupilot.command'].bridge_claim(10)[0]
        self.env['odupilot.command'].bridge_ack(
            init['id'], True, {'id': 'ses_permission_test'}, '')
        session.channel_id.with_user(self.owner).add_members(
            partner_ids=[self.invited.partner_id.id])

        created = self.env['odupilot.session'].ingest_events([{
            'opencode_session_id': session.opencode_session_id,
            'event_type': 'permission.asked',
            'external_id': 'permission:asked:per_test',
            'payload': {
                'payload': {
                    'type': 'permission.asked',
                    'properties': {
                        'id': 'per_test',
                        'sessionID': session.opencode_session_id,
                        'permission': 'bash',
                        'patterns': ['git status', 'git diff --check'],
                        'metadata': {'command': 'git status'},
                    },
                },
            },
        }])

        permission = self.env['odupilot.permission'].sudo().search([
            ('session_id', '=', session.id),
            ('request_id', '=', 'per_test'),
        ])
        self.assertEqual(created, 1)
        self.assertEqual(len(permission), 1)
        self.assertEqual(permission.status, 'pending')
        self.assertTrue(permission.mail_message_id)
        self.assertEqual(session.state, 'waiting_approval')
        formatted = permission.mail_message_id.with_user(
            self.invited).message_format()[0]['odupilot_permission']
        self.assertEqual(formatted['permission'], 'bash')
        self.assertEqual(
            formatted['patterns'], ['git status', 'git diff --check'])

        with self.assertRaises(AccessError):
            permission.with_user(self.invited).action_reply('once')
        result = permission.with_user(self.owner).action_reply('once')
        self.assertEqual(result['status'], 'submitting')
        command = self.env['odupilot.command'].sudo().search([
            ('session_id', '=', session.id),
            ('command_type', '=', 'permission'),
        ])
        self.assertEqual(len(command), 1)
        self.assertEqual(command.user_id, self.owner)
        self.assertEqual(json.loads(command.payload), {
            'permission_id': 'per_test',
            'response': 'once',
        })
        claimed = self.env['odupilot.command'].bridge_claim(10)
        self.assertEqual(claimed[0]['command_type'], 'permission')
        self.env['odupilot.command'].bridge_ack(
            claimed[0]['id'], True, {}, '')
        self.assertEqual(permission.status, 'once')
        self.assertEqual(permission.resolved_by_id, self.owner)
        self.assertEqual(session.state, 'busy')
        self.assertTrue(session.busy_since)
        self.assertEqual(
            permission.with_user(self.owner).action_reply('once')['status'],
            'once',
        )
        with self.assertRaises(UserError):
            permission.with_user(self.invited).action_reply('reject')

    def test_permission_reply_event_resolves_card_and_idle_expires_stale(self):
        session = self._new_session()
        init = self.env['odupilot.command'].bridge_claim(10)[0]
        self.env['odupilot.command'].bridge_ack(
            init['id'], True, {'id': 'ses_permission_events'}, '')
        self.env['odupilot.session'].ingest_events([{
            'opencode_session_id': session.opencode_session_id,
            'event_type': 'permission.asked',
            'external_id': 'permission:asked:per_resolved',
            'payload': {
                'payload': {
                    'type': 'permission.asked',
                    'properties': {
                        'id': 'per_resolved',
                        'sessionID': session.opencode_session_id,
                        'permission': 'edit',
                        'patterns': ['addons_veles/**'],
                    },
                },
            },
        }])
        permission = session.permission_ids

        self.env['odupilot.session'].ingest_events([{
            'opencode_session_id': session.opencode_session_id,
            'event_type': 'permission.replied',
            'external_id': 'permission:replied:per_resolved',
            'payload': {
                'payload': {
                    'type': 'permission.replied',
                    'properties': {
                        'requestID': 'per_resolved',
                        'sessionID': session.opencode_session_id,
                        'reply': 'always',
                    },
                },
            },
        }])
        self.assertEqual(permission.status, 'always')
        self.assertEqual(session.state, 'busy')

        permission.status = 'pending'
        self.env['odupilot.session'].ingest_events([{
            'opencode_session_id': session.opencode_session_id,
            'event_type': 'session.idle',
            'external_id': 'session:idle:permission-test',
            'payload': {
                'payload': {
                    'type': 'session.idle',
                    'properties': {
                        'sessionID': session.opencode_session_id,
                    },
                },
            },
        }])
        self.assertEqual(permission.status, 'expired')
        self.assertEqual(session.state, 'ready')

    def _stream_notifications(self, message_id=None, user=None):
        """Уведомления живого следа, как их видит одна вкладка.

        Каждое уведомление уходит всем участникам разговора, поэтому в шине
        оно лежит по разу на партнёра. Клиент собирает ответ из своей копии,
        и порядок номеров проверяется тоже по ней.
        """
        partner = (user or self.owner).partner_id
        payloads = []
        self.env.cr.precommit.run()
        for bus_event in self.env['bus.bus'].sudo().search([]):
            message = json.loads(bus_event.message)
            if message.get('type') != 'odupilot_stream/update':
                continue
            channel = json.loads(bus_event.channel)
            if not isinstance(channel, list) or len(channel) != 3:
                continue
            if channel[1] != 'res.partner' or channel[2] != partner.id:
                continue
            payload = message['payload']
            if message_id and payload['message_id'] != message_id:
                continue
            payloads.append(payload)
        return payloads

    def _assembled_stream(self, payloads):
        """Собрать состояние следа так же, как это делает браузер.

        Проверка протокола заодно: снимок приходит только на границах хода,
        всё остальное клиент обязан собрать из приращений.
        """
        state = {'parts': [], 'seq': 0, 'text': ''}
        for payload in payloads:
            if 'parts' in payload:
                state = {
                    'parts': [dict(part) for part in payload['parts']],
                    'seq': payload.get('seq') or 0,
                    'text': payload.get('text') or '',
                }
                continue
            self.assertEqual(
                payload.get('seq'), state['seq'] + 1,
                'номера уведомлений идут подряд, иначе клиент не соберёт ответ')
            for delta in payload.get('parts_delta') or []:
                existing = next(
                    (part for part in state['parts']
                     if part.get('id') == delta.get('id')), None)
                if 'append' in delta:
                    self.assertIsNotNone(
                        existing, 'приращение пришло на неизвестную часть')
                    existing['text'] = (existing.get('text') or '') + delta['append']
                elif existing:
                    existing.update(delta)
                else:
                    state['parts'].append(dict(delta))
            state['text'] = '\n\n'.join(
                part.get('text') or ''
                for part in state['parts']
                if part.get('type') == 'text')
            state['seq'] = payload['seq']
        return state

    def test_assistant_parts_stream_over_bus_until_final_message(self):
        session = self._new_session()
        session.write({
            'opencode_session_id': 'ses_stream_test',
            'state': 'busy',
        })
        envelopes = [
            {
                'event_type': 'message.updated',
                'external_id': 'stream:message:start',
                'properties': {
                    'sessionID': session.opencode_session_id,
                    'info': {
                        'id': 'msg_stream_test',
                        'sessionID': session.opencode_session_id,
                        'role': 'assistant',
                        'time': {'created': 1},
                    },
                },
            },
            {
                'event_type': 'message.part.updated',
                'external_id': 'stream:part:start',
                'properties': {
                    'sessionID': session.opencode_session_id,
                    'part': {
                        'id': 'prt_stream_test',
                        'messageID': 'msg_stream_test',
                        'sessionID': session.opencode_session_id,
                        'type': 'text',
                        'text': '',
                    },
                },
            },
            {
                'event_type': 'message.part.delta',
                'external_id': 'stream:delta:1',
                'properties': {
                    'sessionID': session.opencode_session_id,
                    'messageID': 'msg_stream_test',
                    'partID': 'prt_stream_test',
                    'field': 'text',
                    'delta': 'Hello <script>',
                },
            },
            {
                'event_type': 'message.part.delta',
                'external_id': 'stream:delta:2',
                'properties': {
                    'sessionID': session.opencode_session_id,
                    'messageID': 'msg_stream_test',
                    'partID': 'prt_stream_test',
                    'field': 'text',
                    'delta': ' world.',
                },
            },
        ]
        self.env['odupilot.session'].ingest_events([{
            'opencode_session_id': session.opencode_session_id,
            'event_type': envelope['event_type'],
            'external_id': envelope['external_id'],
            'payload': {
                'payload': {
                    'type': envelope['event_type'],
                    'properties': envelope['properties'],
                },
            },
        } for envelope in envelopes])

        self.assertEqual(session.stream_message_id, 'msg_stream_test')
        self.assertEqual(session.stream_part_id, 'prt_stream_test')
        self.assertEqual(session.stream_text, 'Hello <script> world.')
        stream_notifications = self._stream_notifications('msg_stream_test')
        self.assertIn('start', [item['state'] for item in stream_notifications])
        updates = [
            item for item in stream_notifications if item['state'] == 'update']
        self.assertTrue(updates)
        for update in updates:
            self.assertNotIn(
                'text', update,
                'накопленный ответ в каждом уведомлении раздувает шину')
            self.assertNotIn('parts', update)
        self.assertEqual(
            self._assembled_stream(stream_notifications)['text'],
            'Hello <script> world.')

        self.env['odupilot.session'].ingest_events([{
            'opencode_session_id': session.opencode_session_id,
            'event_type': 'message.updated',
            'external_id': 'stream:message:completed',
            'payload': {
                'payload': {
                    'type': 'message.updated',
                    'properties': {
                        'info': {
                            'id': 'msg_stream_test',
                            'role': 'assistant',
                            'time': {'completed': 2},
                        },
                    },
                },
            },
        }])

        # Ход может продолжиться следующим шагом, поэтому завершение
        # сообщения само по себе живой след не гасит.
        self.assertEqual(session.stream_message_id, 'msg_stream_test')
        self.assertEqual(session.stream_text, 'Hello <script> world.')

        self.env['odupilot.session'].ingest_events([{
            'opencode_session_id': session.opencode_session_id,
            'event_type': 'bridge.backfill.message',
            'external_id': 'message:msg_stream_test',
            'payload': {
                'info': {
                    'id': 'msg_stream_test',
                    'role': 'assistant',
                    'time': {'completed': 2},
                },
                'parts': [{
                    'type': 'text',
                    'text': 'Hello <script> world.',
                }],
            },
        }])

        final_event = self.env['odupilot.event'].sudo().search([
            ('session_id', '=', session.id),
            ('external_id', '=', 'message:msg_stream_test'),
        ])
        self.assertTrue(final_event.mail_message_id)
        self.assertNotIn('<script>', final_event.mail_message_id.body)
        done_notifications = []
        self.env.cr.precommit.run()
        for bus_event in self.env['bus.bus'].sudo().search([]):
            message = json.loads(bus_event.message)
            if (message.get('type') == 'odupilot_stream/update'
                    and message['payload']['message_id'] == 'msg_stream_test'
                    and message['payload']['state'] == 'done'):
                done_notifications.append(message['payload'])
        self.assertTrue(done_notifications)
        self.assertFalse(session.stream_message_id)
        self.assertFalse(session.stream_text)

    def _ingest(self, session, envelopes):
        self.env['odupilot.session'].ingest_events([{
            'opencode_session_id': session.opencode_session_id,
            'event_type': envelope['event_type'],
            'external_id': envelope['external_id'],
            'payload': {
                'payload': {
                    'type': envelope['event_type'],
                    'properties': envelope['properties'],
                },
            },
        } for envelope in envelopes])

    def _start_long_answer(self, session, chunks=12, chunk_size=2000):
        """Стартовать ход и надиктовать длинный ответ по кускам."""
        envelopes = [
            {
                'event_type': 'message.updated',
                'external_id': 'size:message:start',
                'properties': {
                    'sessionID': session.opencode_session_id,
                    'info': {
                        'id': 'msg_size_test',
                        'sessionID': session.opencode_session_id,
                        'role': 'assistant',
                        'time': {'created': 1},
                    },
                },
            },
            {
                'event_type': 'message.part.updated',
                'external_id': 'size:part:start',
                'properties': {
                    'sessionID': session.opencode_session_id,
                    'part': {
                        'id': 'prt_size_test',
                        'messageID': 'msg_size_test',
                        'sessionID': session.opencode_session_id,
                        'type': 'text',
                        'text': '',
                    },
                },
            },
        ]
        for index in range(chunks):
            envelopes.append({
                'event_type': 'message.part.delta',
                'external_id': 'size:delta:%s' % index,
                'properties': {
                    'sessionID': session.opencode_session_id,
                    'messageID': 'msg_size_test',
                    'partID': 'prt_size_test',
                    'field': 'text',
                    'delta': 'x' * chunk_size,
                },
            })
        self._ingest(session, envelopes)
        return chunks * chunk_size

    def test_stream_updates_stay_small_while_the_answer_grows(self):
        session = self._new_session()
        session.write({
            'opencode_session_id': 'ses_stream_size',
            'state': 'busy',
        })

        expected = self._start_long_answer(session)

        payloads = self._stream_notifications('msg_size_test')
        updates = [item for item in payloads if item['state'] == 'update']
        self.assertTrue(updates)
        biggest = max(len(json.dumps(item)) for item in updates)
        # Раньше каждое уведомление несло весь накопленный ответ, поэтому
        # последнее весило столько же, сколько ответ целиком.
        self.assertLess(
            biggest, expected // 2,
            'уведомление обновления не должно расти вместе с ответом')
        self.assertEqual(
            len(self._assembled_stream(payloads)['text']), expected)

    def test_stream_snapshot_serves_a_tab_that_missed_the_start(self):
        session = self._new_session()
        session.write({
            'opencode_session_id': 'ses_stream_snapshot',
            'state': 'busy',
        })
        expected = self._start_long_answer(session, chunks=3, chunk_size=100)

        snapshot = self.env['odupilot.session'].with_user(
            self.owner).stream_snapshot(session.channel_id.id)

        self.assertEqual(snapshot['state'], 'start')
        self.assertEqual(snapshot['seq'], session.stream_seq)
        self.assertEqual(len(snapshot['text']), expected)
        self.assertEqual(
            [part['type'] for part in snapshot['parts']], ['text'])

    def test_stream_snapshot_is_closed_to_strangers(self):
        session = self._new_session()
        session.write({
            'opencode_session_id': 'ses_stream_private',
            'state': 'busy',
        })
        self._start_long_answer(session, chunks=1, chunk_size=10)

        with self.assertRaises(AccessError):
            self.env['odupilot.session'].with_user(
                self.outsider).stream_snapshot(session.channel_id.id)

    def test_stream_snapshot_is_empty_without_a_live_answer(self):
        session = self._new_session()

        self.assertFalse(self.env['odupilot.session'].with_user(
            self.owner).stream_snapshot(session.channel_id.id))

    def test_assistant_answer_is_flagged_apart_from_service_notices(self):
        session = self._new_session()
        session.write({
            'opencode_session_id': 'ses_flag_test',
            'state': 'busy',
        })
        # Шаг без текста — только рассуждение и вызов инструмента — виден в
        # разговоре, но ответом не считается.
        self.env['odupilot.session'].ingest_events([{
            'opencode_session_id': session.opencode_session_id,
            'event_type': 'bridge.backfill.message',
            'external_id': 'message:msg_flag_step',
            'payload': {
                'info': {
                    'id': 'msg_flag_step',
                    'role': 'assistant',
                    'time': {'completed': 1},
                },
                'parts': [
                    {
                        'id': 'prt_flag_reasoning',
                        'type': 'reasoning',
                        'text': 'I should read the report first.',
                    },
                    {
                        'id': 'prt_flag_tool',
                        'type': 'tool',
                        'tool': 'odoo_search_records',
                        'state': {
                            'status': 'completed',
                            'input': {'model': 'res.partner'},
                            'output': 'ok',
                        },
                    },
                ],
            },
        }])
        step = self.env['odupilot.event'].sudo().search([
            ('session_id', '=', session.id),
            ('external_id', '=', 'message:msg_flag_step'),
        ]).mail_message_id
        self.assertTrue(step)
        self.assertFalse(step.with_user(self.owner).message_format()[0].get(
            'odupilot_assistant'))

        self.env['odupilot.session'].ingest_events([{
            'opencode_session_id': session.opencode_session_id,
            'event_type': 'bridge.backfill.message',
            'external_id': 'message:msg_flag_test',
            'payload': {
                'info': {
                    'id': 'msg_flag_test',
                    'role': 'assistant',
                    'time': {'completed': 2},
                },
                'parts': [{'type': 'text', 'text': 'The report is ready.'}],
            },
        }])
        answer = self.env['odupilot.event'].sudo().search([
            ('session_id', '=', session.id),
            ('external_id', '=', 'message:msg_flag_test'),
        ]).mail_message_id
        self.assertTrue(answer)
        self.assertTrue(answer.with_user(self.owner).message_format()[0].get(
            'odupilot_assistant'))

        # Служебные заметки бота идут той же шиной; липкое уведомление на них
        # появляться не должно.
        notice = session.channel_id.with_context(
            odupilot_skip_enqueue=True).sudo().message_post(
                author_id=self.env.ref('odupilot.partner_ai_bot').id,
                body='Files available to AI: report.pdf',
                message_type='notification',
                subtype_xmlid='mail.mt_comment',
            )
        self.assertFalse(notice.with_user(self.owner).message_format()[0].get(
            'odupilot_assistant'))

        # Сообщение человека — обычная переписка, а не ответ агента.
        prompt = self._post(session.channel_id, self.owner, 'Where is it?')
        self.assertFalse(prompt.with_user(self.owner).message_format()[0].get(
            'odupilot_assistant'))

    def test_reasoning_and_tool_steps_stay_visible_in_the_live_stream(self):
        session = self._new_session()
        session.write({
            'opencode_session_id': 'ses_trace_test',
            'state': 'busy',
        })
        envelopes = [
            ('message.updated', 'trace:message:reasoning', {
                'info': {
                    'id': 'msg_trace_reasoning',
                    'role': 'assistant',
                    'time': {'created': 1},
                },
            }),
            ('message.part.updated', 'trace:part:reasoning', {
                'part': {
                    'id': 'prt_trace_reasoning',
                    'messageID': 'msg_trace_reasoning',
                    'type': 'reasoning',
                    'text': 'Checking the partner list',
                },
            }),
            ('message.part.updated', 'trace:part:tool', {
                'part': {
                    'id': 'prt_trace_tool',
                    'messageID': 'msg_trace_reasoning',
                    'type': 'tool',
                    'tool': 'odoo_search_records',
                    'state': {
                        'status': 'completed',
                        'input': {'model': 'res.partner'},
                        'output': '{"records": []}',
                    },
                },
            }),
            ('message.updated', 'trace:message:answer', {
                'info': {
                    'id': 'msg_trace_answer',
                    'role': 'assistant',
                    'time': {'created': 2},
                },
            }),
            ('message.part.updated', 'trace:part:answer', {
                'part': {
                    'id': 'prt_trace_answer',
                    'messageID': 'msg_trace_answer',
                    'type': 'text',
                    'text': '',
                },
            }),
            ('message.part.delta', 'trace:delta:answer', {
                'messageID': 'msg_trace_answer',
                'partID': 'prt_trace_answer',
                'field': 'text',
                'delta': 'No partners found.',
            }),
        ]
        self.env['odupilot.session'].ingest_events([{
            'opencode_session_id': session.opencode_session_id,
            'event_type': event_type,
            'external_id': external_id,
            'payload': {
                'payload': {
                    'type': event_type,
                    'properties': properties,
                },
            },
        } for event_type, external_id, properties in envelopes])

        parts = json.loads(session.stream_parts_json)
        self.assertEqual(
            [part['type'] for part in parts],
            ['reasoning', 'tool', 'text'])
        self.assertEqual(parts[0]['text'], 'Checking the partner list')
        self.assertEqual(parts[1]['tool'], 'odoo_search_records')
        self.assertEqual(parts[1]['status'], 'completed')
        self.assertIn('res.partner', parts[1]['input'])
        # Ответ приходит следующим assistant-сообщением и не должен затирать
        # ни рассуждение, ни вызов инструмента.
        self.assertEqual(session.stream_text, 'No partners found.')
        self.assertEqual(session.stream_key, 'msg_trace_reasoning')

        payloads = self._stream_notifications()
        self.assertEqual(payloads[-1]['message_id'], 'msg_trace_reasoning')
        self.assertEqual(
            [part['type'] for part in self._assembled_stream(payloads)['parts']],
            ['reasoning', 'tool', 'text'])

    def test_step_without_answer_is_posted_as_collapsible_trace(self):
        session = self._new_session()
        session.write({
            'opencode_session_id': 'ses_trace_backfill',
            'state': 'busy',
        })
        self.env['odupilot.session'].ingest_events([{
            'opencode_session_id': session.opencode_session_id,
            'event_type': 'bridge.backfill.message',
            'external_id': 'message:msg_trace_step',
            'payload': {
                'info': {
                    'id': 'msg_trace_step',
                    'role': 'assistant',
                    'time': {'completed': 2},
                },
                'parts': [
                    {'id': 'prt_step_start', 'type': 'step-start'},
                    {
                        'id': 'prt_step_reasoning',
                        'type': 'reasoning',
                        'text': 'I should read the partner list first.',
                    },
                    {
                        'id': 'prt_step_tool',
                        'type': 'tool',
                        'tool': 'odoo_search_records',
                        'state': {
                            'status': 'completed',
                            'input': {'model': 'res.partner'},
                            'output': '<script>alert(1)</script>',
                        },
                    },
                    {'id': 'prt_step_finish', 'type': 'step-finish'},
                ],
            },
        }])

        event = self.env['odupilot.event'].sudo().search([
            ('session_id', '=', session.id),
            ('external_id', '=', 'message:msg_trace_step'),
        ])
        body = event.mail_message_id.body
        self.assertTrue(body)
        self.assertIn('<details', body)
        self.assertIn('I should read the partner list first.', body)
        self.assertIn('odoo_search_records', body)
        self.assertNotIn('<script>', body)
        # Шаг без ответа не заканчивает ход, поэтому сессия остаётся занятой.
        self.assertEqual(session.state, 'busy')

        self.env['odupilot.session'].ingest_events([{
            'opencode_session_id': session.opencode_session_id,
            'event_type': 'bridge.backfill.message',
            'external_id': 'message:msg_trace_answer',
            'payload': {
                'info': {
                    'id': 'msg_trace_answer',
                    'role': 'assistant',
                    'time': {'completed': 3},
                },
                'parts': [{
                    'id': 'prt_answer',
                    'type': 'text',
                    'text': 'There are no partners.',
                }],
            },
        }])
        self.assertEqual(session.state, 'ready')

    def _backfill(self, session, external_id, message_id, parts):
        self.env['odupilot.session'].ingest_events([{
            'opencode_session_id': session.opencode_session_id,
            'event_type': 'bridge.backfill.message',
            'external_id': external_id,
            'payload': {
                'info': {
                    'id': message_id,
                    'role': 'assistant',
                    'time': {'completed': 1},
                },
                'parts': parts,
            },
        }])
        return self.env['odupilot.event'].sudo().search([
            ('session_id', '=', session.id),
            ('external_id', '=', external_id),
        ]).mail_message_id

    def test_service_steps_share_one_collapsed_group_until_the_answer(self):
        session = self._new_session()
        session.write({
            'opencode_session_id': 'ses_trace_group',
            'state': 'busy',
        })
        first = self._backfill(session, 'message:group_1', 'msg_group_1', [{
            'id': 'prt_group_reasoning',
            'type': 'reasoning',
            'text': 'The partner list comes first.',
        }])
        second = self._backfill(session, 'message:group_2', 'msg_group_2', [{
            'id': 'prt_group_tool',
            'type': 'tool',
            'tool': 'odoo_search_records',
            'state': {
                'status': 'completed',
                'input': {'model': 'res.partner'},
                'output': 'ok',
            },
        }])
        # Оба шага живут в одном сообщении: цепочка растёт на месте.
        self.assertEqual(first, second)
        self.assertIn('o_AiChatTrace_group', second.body)
        self.assertIn('AI work: 2 steps', second.body)
        self.assertIn('odoo_search_records', second.body)
        self.assertIn('The partner list comes first.', second.body)
        # Ни один служебный блок не раскрыт по умолчанию.
        self.assertNotIn('open=', second.body)
        self.assertFalse(second.with_user(self.owner).message_format()[0].get(
            'odupilot_assistant'))
        self.assertTrue(second.with_user(self.owner).message_format()[0].get(
            'odupilot_step'))

        answer = self._backfill(session, 'message:group_answer', 'msg_answer', [
            {'type': 'text', 'text': 'There are no partners.'},
        ])
        self.assertNotEqual(answer, second)
        self.assertNotIn('o_AiChatTrace', answer.body)
        self.assertFalse(session.trace_message_id)

        # Ответ закрыл группу: следующий служебный шаг начинает новую.
        third = self._backfill(session, 'message:group_3', 'msg_group_3', [{
            'id': 'prt_group_tool_2',
            'type': 'tool',
            'tool': 'odoo_count_records',
            'state': {'status': 'completed', 'output': '0'},
        }])
        self.assertNotIn(third, first | answer)
        self.assertNotIn('o_AiChatTrace_group', third.body)

    def test_permission_request_is_flagged_for_the_reply_notification(self):
        session = self._new_session()
        session.write({
            'opencode_session_id': 'ses_permission_flag',
            'state': 'busy',
        })
        self.env['odupilot.session'].ingest_events([{
            'opencode_session_id': session.opencode_session_id,
            'event_type': 'permission.asked',
            'external_id': 'permission:req_flag',
            'payload': {
                'properties': {
                    'id': 'req_flag',
                    'permission': 'edit',
                    'patterns': ['*.py'],
                    'metadata': {'path': 'model.py'},
                },
            },
        }])
        permission = self.env['odupilot.permission'].sudo().search([
            ('session_id', '=', session.id),
            ('request_id', '=', 'req_flag'),
        ])
        message = permission.mail_message_id
        self.assertTrue(message.odupilot_is_request)
        # Вопрос к человеку поднимает уведомление наравне с ответом.
        formatted = message.with_user(self.owner).message_format()[0]
        self.assertTrue(formatted.get('odupilot_assistant'))
        self.assertFalse(formatted.get('odupilot_step'))

    def test_new_chat_is_named_with_owner_initials(self):
        session = self._new_session()
        self.assertEqual(session.channel_id.name, 'Odoo Assistant - OO')

    def test_first_answer_renames_the_chat_and_keeps_the_initials(self):
        session = self._new_session()
        session.write({
            'opencode_session_id': 'ses_title',
            'state': 'busy',
        })
        self._post(session.channel_id, self.owner, 'List the overdue invoices')
        system = json.loads(self._last_prompt(session).payload)['system']
        self.assertIn('ODUPILOT_TITLE=', system)

        message = self._backfill(session, 'message:title', 'msg_title', [{
            'type': 'text',
            'text': 'Here they are.\n\nODUPILOT_TITLE=Overdue invoices',
        }])
        self.assertEqual(session.channel_id.name, 'Overdue invoices - OO')
        self.assertTrue(session.title_auto_set)
        self.assertNotIn('ODUPILOT_TITLE', message.body)
        self.assertIn('Here they are.', message.body)

        # Названный разговор второй раз заголовок не просит и не меняет.
        self._post(session.channel_id, self.owner, 'And the paid ones?')
        self.assertNotIn(
            'ODUPILOT_TITLE=',
            json.loads(self._last_prompt(session).payload)['system'])
        self._backfill(session, 'message:title_2', 'msg_title_2', [{
            'type': 'text',
            'text': 'ODUPILOT_TITLE=Paid invoices\n\nNothing paid yet.',
        }])
        self.assertEqual(session.channel_id.name, 'Overdue invoices - OO')

    def test_manual_rename_prevents_first_answer_from_overwriting_title(self):
        session = self._new_session()

        session.channel_id.with_user(self.owner).channel_rename(
            'My invoice review')

        self.assertEqual(session.channel_id.name, 'My invoice review')
        self.assertTrue(session.title_auto_set)
        event = self.env['odupilot.event'].sudo().search([
            ('session_id', '=', session.id),
            ('event_type', '=', 'session.title.renamed'),
        ], limit=1)
        self.assertEqual(event.actor_user_id, self.owner)
        self.assertEqual(json.loads(event.payload)['title'], 'My invoice review')

        self._post(session.channel_id, self.owner, 'List the overdue invoices')
        self.assertNotIn(
            'ODUPILOT_TITLE=',
            json.loads(self._last_prompt(session).payload)['system'])
        self._backfill(session, 'message:manual_title', 'msg_manual_title', [{
            'type': 'text',
            'text': 'ODUPILOT_TITLE=Overdue invoices\n\nHere they are.',
        }])
        self.assertEqual(session.channel_id.name, 'My invoice review')

    def test_retention_removes_technical_data_but_keeps_discuss_channel(self):
        closed_session = self._new_session()
        channel = closed_session.channel_id
        closed_session.write({
            'state': 'closed',
            'closed_at': fields.Datetime.now() - timedelta(days=366),
        })
        active_session = self._new_session()
        old_event = active_session._audit_event(
            'retention.test', {}, self.owner, 'retention:test')
        self.env.cr.execute(
            'UPDATE odupilot_event SET create_date = %s WHERE id = %s',
            [fields.Datetime.now() - timedelta(days=91), old_event.id],
        )
        self.env['ir.config_parameter'].sudo().set_param(
            'odupilot.event_retention_days', '90')
        self.env['ir.config_parameter'].sudo().set_param(
            'odupilot.closed_session_retention_days', '365')

        result = self.env['odupilot.session']._cron_apply_retention()

        self.assertGreaterEqual(result['events'], 1)
        self.assertGreaterEqual(result['sessions'], 1)
        self.assertFalse(old_event.exists())
        self.assertFalse(closed_session.exists())
        self.assertTrue(channel.exists())

    def test_command_duration_and_runtime_heartbeat_metrics(self):
        session = self._new_session()
        command = session.command_ids[:1]
        command.write({
            'state': 'processing',
            'processing_started_at': fields.Datetime.now(),
        })
        command.write({'state': 'done'})

        self.assertTrue(command.completed_at)
        self.assertGreaterEqual(command.duration_seconds, 0)

        runtime = self.env.ref('odupilot.runtime_main')
        self.env['odupilot.runtime'].bridge_heartbeat({
            'bridge_version': 'test-version',
            'bridge_started_at': '2026-08-17 01:00:00',
            'opencode_healthy': True,
            'opencode_version': '1.18.9',
            'opencode_latency_ms': 7,
            'event_queue_size': 2,
        })

        self.assertEqual(runtime.status, 'healthy')
        self.assertEqual(runtime.bridge_version, 'test-version')
        self.assertEqual(runtime.opencode_version, '1.18.9')
        self.assertEqual(runtime.opencode_latency_ms, 7)
        self.assertEqual(runtime.event_queue_size, 2)
        self.assertGreaterEqual(runtime.completed_command_24h_count, 1)

    def test_last_runtime_error_is_marked_resolved_once_health_recovers(self):
        runtime = self.env.ref('odupilot.runtime_main')
        self.env['odupilot.runtime'].bridge_heartbeat({
            'bridge_version': 'test-version',
            'opencode_healthy': False,
            'error': 'failed to resolve opencode host',
        })

        self.assertEqual(runtime.health_error, 'failed to resolve opencode host')
        self.assertTrue(runtime.last_error_state.startswith('Active'))

        # мост восстановился: текущей ошибки нет, но след прошлой остаётся
        runtime.sudo().write({
            'last_error_at': fields.Datetime.now() - timedelta(hours=13),
        })
        self.env['odupilot.runtime'].bridge_heartbeat({
            'bridge_version': 'test-version',
            'opencode_healthy': True,
        })

        self.assertFalse(runtime.health_error)
        self.assertEqual(runtime.last_error, 'failed to resolve opencode host')
        self.assertEqual(runtime.last_error_state, 'Resolved · was 13 h ago')

    def test_outsider_cannot_answer_permission(self):
        session = self._new_session()
        permission = self.env['odupilot.permission'].sudo().create({
            'session_id': session.id,
            'request_id': 'per_private',
            'permission': 'bash',
        })

        with self.assertRaises(AccessError):
            permission.with_user(self.outsider).action_reply('reject')

    def test_assistant_markdown_table_is_rendered_as_safe_html(self):
        session = self._new_session()
        session.write({
            'opencode_session_id': 'ses_table_test',
            'state': 'busy',
        })
        values = [{
            'opencode_session_id': session.opencode_session_id,
            'event_type': 'bridge.backfill.message',
            'external_id': 'message:msg_table_test',
            'payload': {
                'info': {
                    'id': 'msg_table_test',
                    'role': 'assistant',
                    'time': {'completed': 1},
                },
                'parts': [{
                    'type': 'text',
                    'text': (
                        'Top customers:\n\n'
                        '| Customer | Sales |\n'
                        '|:---|---:|\n'
                        '| ACME <script>alert(1)</script> | 42 EUR |'),
                }],
            },
        }]

        self.env['odupilot.session'].ingest_events(values)

        event = self.env['odupilot.event'].sudo().search([
            ('session_id', '=', session.id),
            ('external_id', '=', 'message:msg_table_test'),
        ])
        body = event.mail_message_id.body
        self.assertIn('<table', body)
        self.assertIn('<th style="text-align:left">Customer</th>', body)
        self.assertIn('<td style="text-align:right">42 EUR</td>', body)
        self.assertNotIn('alert(1)', body)
        self.assertNotIn('|:---|---:|', body)

    def test_assistant_html_is_sanitized(self):
        body = str(render_assistant_message(
            '<table><tr><td>Readable</td></tr></table>'
            '<img src="x" onerror="alert(1)">'
            '<script>alert(2)</script>'))

        self.assertIn('<table class="table table-bordered table-hover table-sm">', body)
        self.assertIn('<td>Readable</td>', body)
        self.assertNotIn('onerror', body)
        self.assertNotIn('<script', body)

    def test_record_markers_become_form_links(self):
        body = str(render_assistant_message(
            '| ID | Customer |\n'
            '|---:|:---------|\n'
            '| [1](odoo://res.partner/1) | Veles Agro |\n\n'
            'Bill [42](odoo://account.move/42) is posted.',
            'https://odoo.example.com/'))

        self.assertIn(
            '<a href="https://odoo.example.com/web#model=res.partner&amp;'
            'id=1&amp;view_type=form">1</a>',
            body)
        self.assertIn(
            '<a href="https://odoo.example.com/web#model=account.move&amp;'
            'id=42&amp;view_type=form">42</a>',
            body)
        self.assertNotIn('odoo://', body)

    def test_record_markers_survive_without_base_url(self):
        body = str(render_assistant_message('[7](odoo://res.partner/7)'))

        self.assertIn(
            '<a href="/web#model=res.partner&amp;id=7&amp;view_type=form">7</a>',
            body)

    def test_prompt_system_asks_for_record_links(self):
        session = self._new_session()
        message = self._post(
            session.channel_id, self.owner, '<p>Show me the customers.</p>')

        command = self.env['odupilot.command'].sudo().search([
            ('source_message_id', '=', message.id),
        ])
        system = json.loads(command.payload)['system']
        self.assertIn('odoo://<model>/<id>', system)
        self.assertIn('Never guess an ID', system)

    def test_named_record_mentions_become_form_links(self):
        body = str(render_assistant_message(
            'Task [P1](odoo://project.task/318) is still in '
            '[Done](odoo://project.task.type/7).',
            'https://odoo.example.com'))

        self.assertIn(
            '<a href="https://odoo.example.com/web#model=project.task&amp;'
            'id=318&amp;view_type=form">P1</a>',
            body)
        self.assertIn(
            '<a href="https://odoo.example.com/web#model=project.task.type&amp;'
            'id=7&amp;view_type=form">Done</a>',
            body)

    def test_assistant_commonmark_features_are_rendered(self):
        body = str(render_assistant_message(
            '# Summary\n\n'
            '- **Important** item\n'
            '- ~~obsolete~~ value\n\n'
            '```python\nprint("safe")\n```\n\n'
            'https://example.com'))

        self.assertIn('<h1>Summary</h1>', body)
        self.assertIn('<ul>', body)
        self.assertIn('<strong>Important</strong>', body)
        self.assertIn('<s>obsolete</s>', body)
        self.assertIn('<code class="language-python">', body)
        self.assertIn('<a href="https://example.com">', body)

    def test_profile_unlink_removes_sessions_and_clears_users(self):
        session = self._new_session()
        session_id = session.id
        channel = session.channel_id
        archived = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': 'OduPilot Archived',
                'login': 'odupilot_archived',
                'odupilot_profile_id': self.profile.id,
            })
        archived.sudo().write({'active': False})

        self.profile.unlink()

        self.assertFalse(session.exists())
        self.assertFalse(self.owner.sudo().odupilot_profile_id)
        self.assertFalse(archived.sudo().odupilot_profile_id)
        # Переписка в Discuss переживает удаление профиля.
        self.assertTrue(channel.exists())
        # Каталог на volume моста убирает команда close, пережившая сессию.
        cleanup = self.env['odupilot.command'].sudo().search([
            ('external_id', '=', 'close:%s' % session_id),
        ])
        self.assertEqual(len(cleanup), 1)
        self.assertEqual(cleanup.command_type, 'close')
        self.assertEqual(cleanup.state, 'pending')
        self.assertFalse(cleanup.session_id)

    def test_store_serializes_session_status_and_blocks_outsiders(self):
        from odoo.addons.mail.tools.discuss import Store
        session = self._new_session()
        data = Store().add(session.channel_id.with_user(self.owner)).get_result()
        channel = data['discuss.channel'][0]
        self.assertTrue(channel['is_odupilot'])
        self.assertEqual(channel['odupilot_session']['session_id'], session.id)
        with self.assertRaises(AccessError):
            session.channel_id.with_user(self.outsider).channel_info()

    def test_member_model_cannot_bypass_invitation_rules(self):
        session = self._new_session()
        session.channel_id.with_user(self.owner).add_members(partner_ids=self.invited.partner_id.ids)
        with self.assertRaises(AccessError):
            self.env['discuss.channel.member'].with_user(self.invited).create({
                'channel_id': session.channel_id.id, 'partner_id': self.outsider.partner_id.id,
            })
        bot_member = session.channel_id.channel_member_ids.filtered(
            lambda member: member.partner_id == self.env.ref('odupilot.partner_ai_bot'))
        with self.assertRaises(ValidationError):
            bot_member.with_user(self.owner).with_context(odupilot_membership_allowed=True).unlink()
