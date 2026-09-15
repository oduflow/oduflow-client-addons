import base64
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.modules.setdefault("requests", mock.Mock())

import bridge as bridge_module
from bridge import Bridge, OdooClient, OpenCodeClient, WorkspaceManager


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeAnydoc:
    class ConvertError(Exception):
        pass

    class UnsupportedError(ConvertError):
        pass

    class MalformedError(ConvertError):
        pass

    def __init__(self, results, malformed=None):
        self.results = results
        self.malformed = malformed or set()

    def to_markdown(self, path):
        name = os.path.basename(path)
        if name in self.malformed:
            raise self.MalformedError("document is unusable")
        if name not in self.results:
            raise self.UnsupportedError("unknown format")
        return self.results[name]


class TestOdooClient(unittest.TestCase):
    def test_poll_tracks_bus_cursor_without_command_payload(self):
        client = OdooClient.__new__(OdooClient)
        client.url = "https://odoo.example.com"
        client.http = mock.Mock()
        client.http.post.return_value = FakeResponse({
            "result": [{
                "id": 42,
                "message": {
                    "type": "odupilot.command.available",
                    "payload": {},
                },
            }],
        })

        last, notifications = client.wait_for_commands(17)

        self.assertEqual(last, 42)
        self.assertEqual(len(notifications), 1)
        request = client.http.post.call_args.kwargs["json"]
        self.assertEqual(client.http.post.call_args.args[0], "https://odoo.example.com/odupilot/bridge/poll")
        self.assertNotIn("channels", request["params"])
        self.assertEqual(request["params"]["last"], 17)


class TestOpenCodeClient(unittest.TestCase):
    def test_health_reports_version_and_latency(self):
        client = OpenCodeClient.__new__(OpenCodeClient)
        client.request = mock.Mock(return_value=FakeResponse({
            "healthy": True,
            "version": "1.18.9",
        }))

        health = client.health()

        self.assertTrue(health["healthy"])
        self.assertEqual(health["version"], "1.18.9")
        self.assertGreaterEqual(health["latency_ms"], 0)

    def test_prompt_leaves_message_id_to_opencode_and_uses_stable_part_id(self):
        client = OpenCodeClient.__new__(OpenCodeClient)
        client.url = "http://opencode:4096"
        client.auth = ("opencode", "secret")
        response = mock.Mock()
        response.raise_for_status.return_value = None

        with mock.patch("bridge.requests.request", return_value=response) as request:
            client.prompt_async({
                "directory": "/workspace/chat_42",
                "opencode_session_id": "ses_42",
                "model": "test-model",
                "payload": {
                    "message_id": "msg_deterministic",
                    "text": "Hello",
                    "system": "System",
                },
            })

        body = request.call_args.kwargs["json"]
        self.assertNotIn("messageID", body)
        self.assertEqual(body["parts"][0]["id"], "prt_deterministic")

    def test_prompt_retry_does_not_duplicate_existing_part(self):
        client = OpenCodeClient.__new__(OpenCodeClient)
        client.request = mock.Mock()
        client.list_messages = mock.Mock(return_value=[{
            "info": {"id": "msg_generated", "role": "user"},
            "parts": [{"id": "prt_deterministic", "type": "text"}],
        }])
        client.session_busy = mock.Mock(return_value=False)

        result = client.prompt_async({
            "attempts": 2,
            "directory": "/workspace/chat_42",
            "opencode_session_id": "ses_42",
            "model": "test-model",
            "payload": {
                "message_id": "msg_deterministic",
                "text": "Hello",
                "system": "System",
            },
        })

        client.list_messages.assert_called_once()
        client.session_busy.assert_called_once()
        client.request.assert_not_called()
        self.assertEqual(result, {
            "already_admitted": True,
            "session_busy": False,
        })

    def test_permission_reply_treats_missing_resolved_request_as_success(self):
        class FakeHttpError(Exception):
            def __init__(self, response):
                super().__init__("Not found")
                self.response = response

        client = OpenCodeClient.__new__(OpenCodeClient)
        client.request = mock.Mock(side_effect=FakeHttpError(
            mock.Mock(status_code=404)))
        command = {
            "directory": "/workspace/chat_42",
            "payload": {
                "permission_id": "per_resolved",
                "response": "always",
            },
        }

        with mock.patch.object(
                bridge_module.requests, "HTTPError", FakeHttpError):
            client.respond_permission(command)

        client.request.assert_called_once_with(
            "POST",
            "/permission/per_resolved/reply",
            directory="/workspace/chat_42",
            payload={"reply": "always"},
        )


class TestBridgeCommandRetry(unittest.TestCase):
    def test_reset_replaces_the_opencode_conversation(self):
        bridge = Bridge.__new__(Bridge)
        bridge.odoo = mock.Mock()
        bridge.opencode = mock.Mock()
        bridge.workspace = mock.Mock()
        bridge.command_wakeup = mock.Mock()
        bridge.refresh_sessions = mock.Mock()
        bridge.opencode.create_session.return_value = {'id': 'ses_fresh'}
        command = {
            'id': 42,
            'attempts': 1,
            'command_type': 'reset',
            'directory': '/workspace/chat_42',
            'opencode_session_id': 'ses_old',
            'payload': {},
        }

        bridge.process_command(command)

        bridge.opencode.close_session.assert_called_once_with(command)
        bridge.opencode.create_session.assert_called_once_with(command)
        bridge.workspace.prepare.assert_not_called()
        bridge.odoo.execute.assert_called_once_with(
            'odupilot.command',
            'bridge_ack',
            [42, True, {'id': 'ses_fresh'}, ''],
        )

    def test_runtime_heartbeat_contains_queue_and_health_metrics(self):
        bridge = Bridge.__new__(Bridge)
        bridge.odoo = mock.Mock()
        bridge.opencode = mock.Mock()
        bridge.opencode.health.return_value = {
            "healthy": True,
            "version": "1.18.9",
            "latency_ms": 12,
        }
        bridge.events = queue.Queue()
        bridge.events.put({"event": 1})
        bridge.started_at = "2026-08-17 01:00:00"

        bridge.report_heartbeat()

        values = bridge.odoo.execute.call_args.args[2][0]
        self.assertTrue(values["opencode_healthy"])
        self.assertEqual(values["opencode_version"], "1.18.9")
        self.assertEqual(values["opencode_latency_ms"], 12)
        self.assertEqual(values["event_queue_size"], 1)
        self.assertEqual(values["bridge_started_at"], "2026-08-17 01:00:00")

    def test_prompt_lists_the_markdown_conversions_the_bridge_produced(self):
        bridge = Bridge.__new__(Bridge)
        bridge.odoo = mock.Mock()
        bridge.opencode = mock.Mock()
        bridge.workspace = mock.Mock()
        bridge.command_wakeup = mock.Mock()
        bridge.workspace.write_config.return_value = False
        bridge.workspace.write_attachments.return_value = [
            "attachments/message_7/report.docx.md",
        ]
        command = {
            "id": 9,
            "attempts": 1,
            "command_type": "prompt",
            "payload": {"text": "Read the report."},
        }

        bridge.process_command(command)

        text = command["payload"]["text"]
        self.assertIn("AnyDoc Markdown conversions:", text)
        self.assertIn("- attachments/message_7/report.docx.md", text)
        self.assertIs(
            bridge.opencode.prompt_async.call_args.args[0], command)

    def test_failed_command_schedules_retry_from_acknowledgement(self):
        bridge = Bridge.__new__(Bridge)
        bridge.odoo = mock.Mock()
        bridge.opencode = mock.Mock()
        bridge.workspace = mock.Mock()
        bridge.command_wakeup = mock.Mock()
        bridge.opencode.abort.side_effect = RuntimeError("OpenCode unavailable")
        bridge.odoo.execute.return_value = {"retry_after": 4}

        with mock.patch("bridge.threading.Timer") as timer_class:
            bridge.process_command({
                "id": 7,
                "attempts": 2,
                "command_type": "abort",
                "payload": {},
            })

        timer_class.assert_called_once_with(4, bridge.command_wakeup.set)
        timer = timer_class.return_value
        self.assertTrue(timer.daemon)
        timer.start.assert_called_once_with()
        bridge.odoo.execute.assert_called_once_with(
            "odupilot.command",
            "bridge_ack",
            [7, False, {}, "OpenCode unavailable"],
        )


class FakeStreamResponse:
    def __init__(self, chunks):
        self.chunks = chunks

    def iter_content(self, chunk_size=8192):
        return iter(self.chunks)


class TestBridgeEventStream(unittest.TestCase):
    def _bridge(self):
        bridge = Bridge.__new__(Bridge)
        bridge.events = queue.Queue()
        bridge.sessions = {}
        bridge.sessions_lock = threading.Lock()
        return bridge

    def test_unicode_line_separator_does_not_split_an_event(self):
        bridge = self._bridge()
        # U+2028 внутри текста ассистента: JSON.stringify его не экранирует,
        # а str.splitlines() ломает на нём строку.
        event = json.dumps({
            "payload": {
                "type": "message.part.delta",
                "sessionID": "ses_42",
                "text": "first\u2028second",
            },
        }, ensure_ascii=False)
        response = FakeStreamResponse([
            ("data: %s\n" % event).encode("utf-8"),
        ])

        lines = list(bridge.iter_event_lines(response))

        self.assertEqual(len(lines), 1)
        self.assertEqual(
            json.loads(lines[0][5:].strip())["payload"]["text"],
            "first\u2028second",
        )

    def test_event_split_across_chunks_is_reassembled(self):
        bridge = self._bridge()
        response = FakeStreamResponse([
            b'data: {"payload": {"sess',
            b'ionID": "ses_42"}}\ndata: {"payload": {}}\n',
        ])

        lines = list(bridge.iter_event_lines(response))

        self.assertEqual(len(lines), 2)
        self.assertEqual(
            json.loads(lines[0][5:].strip())["payload"]["sessionID"],
            "ses_42",
        )

    def test_malformed_line_is_skipped_without_dropping_the_stream(self):
        bridge = self._bridge()
        bridge.opencode = mock.Mock()
        bridge.refresh_sessions = mock.Mock()
        bridge.reconcile_busy_sessions = mock.Mock()
        bridge.queue_event = mock.Mock()
        bridge.opencode.events.side_effect = [
            FakeStreamResponse([
                b'data: {"payload": {"type": "broken"\n'
                b'data: {"payload": {"type": "message.updated"}}\n',
            ]),
            # Второе подключение обрывает цикл, чтобы тест не крутился вечно.
            RuntimeError("stop"),
        ]

        with mock.patch("bridge.time.sleep", side_effect=KeyboardInterrupt):
            with mock.patch.object(bridge_module._logger, "exception"):
                with self.assertRaises(KeyboardInterrupt):
                    bridge.event_loop()

        self.assertEqual(bridge.queue_event.call_count, 1)
        self.assertEqual(
            bridge.queue_event.call_args.args[0]["payload"]["type"],
            "message.updated",
        )


class TestBridgeReconciliation(unittest.TestCase):
    def _bridge(self, session):
        bridge = Bridge.__new__(Bridge)
        bridge.events = queue.Queue()
        bridge.sessions_lock = threading.Lock()
        bridge.sessions = {session["opencode_session_id"]: session}
        bridge.opencode = mock.Mock()
        return bridge

    def _session(self, **overrides):
        session = {
            "opencode_session_id": "ses_42",
            "directory": "/workspace/chat_42",
            "state": "busy",
            "busy_since": "2026-08-17 13:21:28",
        }
        session.update(overrides)
        return session

    def test_busy_session_unknown_to_opencode_gets_a_synthetic_idle(self):
        bridge = self._bridge(self._session())
        bridge.opencode.session_statuses.return_value = {}

        bridge.reconcile_busy_sessions()

        event = bridge.events.get_nowait()
        self.assertEqual(event["event_type"], "session.idle")
        self.assertEqual(event["opencode_session_id"], "ses_42")
        self.assertEqual(
            event["external_id"],
            "bridge.reconcile.idle:ses_42:2026-08-17 13:21:28",
        )
        self.assertTrue(event["payload"]["bridge_reconciled"])
        bridge.opencode.session_statuses.assert_called_once_with(
            "/workspace/chat_42")

    def test_session_still_running_in_opencode_is_left_alone(self):
        bridge = self._bridge(self._session())
        bridge.opencode.session_statuses.return_value = {"ses_42": {}}

        bridge.reconcile_busy_sessions()

        self.assertTrue(bridge.events.empty())

    def test_fresh_prompt_stays_within_the_grace_period(self):
        busy_since = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
        bridge = self._bridge(self._session(busy_since=busy_since))

        bridge.reconcile_busy_sessions()

        self.assertTrue(bridge.events.empty())
        bridge.opencode.session_statuses.assert_not_called()

    def test_ready_session_is_not_reconciled(self):
        bridge = self._bridge(self._session(state="ready"))

        bridge.reconcile_busy_sessions()

        self.assertTrue(bridge.events.empty())
        bridge.opencode.session_statuses.assert_not_called()

    def test_unreadable_status_does_not_release_the_session(self):
        bridge = self._bridge(self._session())
        bridge.opencode.session_statuses.side_effect = RuntimeError("down")

        bridge.reconcile_busy_sessions()

        self.assertTrue(bridge.events.empty())


class TestWorkspaceManager(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="odupilot-bridge-")
        workspace_root = mock.patch.object(
            bridge_module, "WORKSPACE_ROOT", self.root)
        workspace_root.start()
        self.addCleanup(workspace_root.stop)
        self.addCleanup(shutil.rmtree, self.root, True)
        self.manager = WorkspaceManager()

    def _command(self, workspace_type="files"):
        if workspace_type == "worktree":
            directory = os.path.join(
                self.root, "worktrees", "stoic-seahorse")
        else:
            directory = os.path.join(
                self.root, "users", "admin_2", "chat_42")
        return {
            "directory": directory,
            "workspace": {
                "root": self.root,
                "type": workspace_type,
                "session_id": 42,
                "profile_id": 1,
                "directory": directory,
                "repository_directory": os.path.join(
                    self.root, "repo", "profile_1"),
                "branch": (
                    "stoic-seahorse" if workspace_type == "worktree" else ""),
            },
            "opencode_config": {
                "model": "litellm/test-model",
                "provider": {
                    "litellm": {
                        "options": {"apiKey": "test-secret"},
                    },
                },
                "mcp": {
                    "odoo": {
                        "type": "remote",
                        "url": "https://odoo.example.com/mcp",
                        "headers": {
                            "Authorization": "Bearer {env:ODOO_MCP_TOKEN}",
                        },
                    },
                },
            },
            "opencode_environment": {
                "ODOO_MCP_TOKEN": "session-odoo-secret",
            },
            "payload": {},
        }

    def test_workspace_root_environment_override_is_ignored(self):
        with mock.patch.dict(os.environ, {
                "ODUPILOT_WORKSPACE_ROOT": "/environment-workspace"}):
            manager = WorkspaceManager()

        self.assertEqual(manager.root, os.path.realpath(self.root))

    def test_files_workspace_config_attachments_and_cleanup(self):
        command = self._command()
        self.manager.prepare(command)

        config_path = os.path.join(command["directory"], "opencode.json")
        with open(config_path, encoding="utf-8") as config_file:
            config = json.load(config_file)
        self.assertEqual(config["model"], "litellm/test-model")
        secret_path = os.path.join(
            self.manager.root, ".odupilot-environment", "session_42",
            "ODOO_MCP_TOKEN")
        self.assertEqual(
            config["mcp"]["odoo"]["headers"]["Authorization"],
            "Bearer {file:%s}" % secret_path,
        )
        self.assertNotIn("session-odoo-secret", json.dumps(config))
        with open(secret_path, encoding="utf-8") as secret_file:
            self.assertEqual(secret_file.read(), "session-odoo-secret")
        self.assertEqual(os.stat(secret_path).st_mode & 0o777, 0o600)
        self.assertEqual(os.stat(config_path).st_mode & 0o777, 0o600)
        self.assertTrue(os.path.isdir(
            os.path.join(command["directory"], ".git")))

        command["payload"]["attachments"] = [{
            "path": "attachments/message_7/report.txt",
            "data": base64.b64encode(b"report body").decode("ascii"),
        }]
        self.manager.write_attachments(command)
        with open(os.path.join(
                command["directory"], "attachments", "message_7",
                "report.txt"), "rb") as attachment:
            self.assertEqual(attachment.read(), b"report body")

        self.manager.cleanup(command)
        self.assertFalse(os.path.exists(command["directory"]))
        self.assertFalse(os.path.exists(os.path.dirname(secret_path)))

    def test_office_attachment_is_converted_to_markdown_by_anydoc(self):
        command = self._command()
        self.manager.prepare(command)
        command["payload"]["attachments"] = [
            {
                "path": "attachments/message_7/report.docx",
                "data": base64.b64encode(b"binary docx").decode("ascii"),
            },
            {
                "path": "attachments/message_7/photo.png",
                "data": base64.b64encode(b"binary png").decode("ascii"),
            },
        ]
        fake = FakeAnydoc({"report.docx": "# Report\n"})
        with mock.patch.object(bridge_module, "anydoc", fake):
            conversions = self.manager.write_attachments(command)

        self.assertEqual(
            conversions, ["attachments/message_7/report.docx.md"])
        markdown_path = os.path.join(
            command["directory"], "attachments", "message_7",
            "report.docx.md")
        with open(markdown_path, encoding="utf-8") as markdown:
            self.assertEqual(markdown.read(), "# Report\n")
        self.assertEqual(os.stat(markdown_path).st_mode & 0o777, 0o600)
        self.assertFalse(os.path.exists(os.path.join(
            command["directory"], "attachments", "message_7",
            "photo.png.md")))

    def test_broken_document_does_not_fail_the_prompt(self):
        command = self._command()
        self.manager.prepare(command)
        command["payload"]["attachments"] = [{
            "path": "attachments/message_7/broken.docx",
            "data": base64.b64encode(b"broken docx").decode("ascii"),
        }]
        fake = FakeAnydoc({}, malformed={"broken.docx"})
        with mock.patch.object(bridge_module, "anydoc", fake):
            conversions = self.manager.write_attachments(command)

        self.assertEqual(conversions, [])
        attachment_path = os.path.join(
            command["directory"], "attachments", "message_7", "broken.docx")
        self.assertTrue(os.path.exists(attachment_path))
        self.assertFalse(os.path.exists(attachment_path + ".md"))

    def test_changed_session_environment_reloads_opencode_config(self):
        command = self._command()
        self.manager.prepare(command)
        command["opencode_environment"]["ODOO_MCP_TOKEN"] = "rotated-secret"

        self.assertTrue(self.manager.write_config(command))
        secret_path = os.path.join(
            self.manager.root, ".odupilot-environment", "session_42",
            "ODOO_MCP_TOKEN")
        with open(secret_path, encoding="utf-8") as secret_file:
            self.assertEqual(secret_file.read(), "rotated-secret")

    def test_developer_worktree_is_created_by_sidecar(self):
        source = tempfile.mkdtemp(prefix="odupilot-source-")
        remote = tempfile.mkdtemp(prefix="odupilot-remote-")
        self.addCleanup(shutil.rmtree, source, True)
        self.addCleanup(shutil.rmtree, remote, True)
        subprocess.run(
            ["git", "init", "--initial-branch=prod", source], check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        with open(os.path.join(source, "README.md"), "w", encoding="utf-8") as readme:
            readme.write("test repository\n")
        subprocess.run(
            ["git", "-C", source, "add", "README.md"], check=True)
        subprocess.run([
            "git", "-C", source,
            "-c", "user.name=OduPilot Test",
            "-c", "user.email=odupilot@example.com",
            "commit", "-m", "Initial",
        ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        shutil.rmtree(remote)
        subprocess.run(
            ["git", "clone", "--bare", source, remote], check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        command = self._command("worktree")
        command["workspace"].update({
            "repo_url": remote,
            "github_pat": "test-pat",
            "base_branch": "prod",
        })
        self.manager.prepare(command)

        branch = subprocess.run([
            "git", "-C", command["directory"], "branch", "--show-current",
        ], check=True, stdout=subprocess.PIPE, text=True).stdout.strip()
        self.assertEqual(branch, "stoic-seahorse")
        self.assertTrue(os.path.isfile(os.path.join(
            command["directory"], "opencode.json")))

        feature_path = os.path.join(command["directory"], "feature.txt")
        with open(feature_path, "w", encoding="utf-8") as feature:
            feature.write("developer change\n")
        subprocess.run([
            "git", "-C", command["directory"], "add", "feature.txt",
        ], check=True)
        subprocess.run([
            "git", "-C", command["directory"],
            "-c", "user.name=OduPilot Test",
            "-c", "user.email=odupilot@example.com",
            "commit", "-m", "Developer change",
        ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        command["payload"] = {
            "title": "Developer change",
            "body": "Verified in the test environment.",
        }
        published = self.manager.publish(command)
        self.assertEqual(published["branch"], "stoic-seahorse")
        self.assertFalse(published["pull_request_url"])
        remote_branch = subprocess.run([
            "git", "-C", remote, "show-ref", "--verify", "--quiet",
            "refs/heads/stoic-seahorse",
        ], check=False)
        self.assertEqual(remote_branch.returncode, 0)

        self.manager.cleanup(command)
        self.assertFalse(os.path.exists(command["directory"]))

    def test_github_pull_request_is_created_without_exposing_pat(self):
        list_response = FakeResponse([])
        create_response = FakeResponse({
            "number": 17,
            "html_url": "https://github.com/example/repository/pull/17",
        })
        with mock.patch(
                "bridge.requests.request",
                side_effect=[list_response, create_response]) as request:
            pull_request_url, branch_url = self.manager._github_pull_request(
                "https://github.com/example/repository.git",
                "secret-pat",
                "stoic-seahorse",
                "prod",
                "Developer change",
                "Verified.",
            )

        self.assertEqual(
            pull_request_url,
            "https://github.com/example/repository/pull/17",
        )
        self.assertEqual(
            branch_url,
            "https://github.com/example/repository/tree/stoic-seahorse",
        )
        self.assertEqual(request.call_count, 2)
        self.assertNotIn("secret-pat", request.call_args.args[1])
        self.assertEqual(
            request.call_args.kwargs["headers"]["Authorization"],
            "Bearer secret-pat",
        )


if __name__ == "__main__":
    unittest.main()
