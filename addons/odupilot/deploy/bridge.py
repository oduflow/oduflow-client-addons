import base64
import binascii
import calendar
import fcntl
import hashlib
import json
import logging
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import xmlrpc.client
from contextlib import contextmanager
from urllib.parse import urlparse

import requests

try:
    import anydoc
except ImportError:  # pragma: no cover - образ моста всегда содержит anydoc
    anydoc = None


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
_logger = logging.getLogger("odupilot_bridge")

COMMAND_CHANNEL = "odupilot_commands"
BRIDGE_VERSION = os.getenv("ODUPILOT_BRIDGE_VERSION", "unknown")
ENVIRONMENT_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
WORKSPACE_ROOT = "/workspace"


def _xmlrpc_safe(value):
    if isinstance(value, dict):
        return {
            key: _xmlrpc_safe(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_xmlrpc_safe(item) for item in value]
    if isinstance(value, int) and not (-2147483648 <= value <= 2147483647):
        return str(value)
    return value


def _busy_grace_expired(busy_since):
    # Промпт уже отмечен busy в Odoo, но OpenCode мог ещё не поднять статус
    # сессии. Сверяем только те, что висят дольше грейса.
    grace = float(os.getenv("ODUPILOT_RECONCILE_GRACE_SECONDS", "30"))
    if not busy_since:
        return True
    try:
        started = time.strptime(busy_since, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return True
    return time.time() - calendar.timegm(started) >= grace


def _required(name):
    value = os.getenv(name)
    if not value:
        raise RuntimeError("Missing required environment variable: %s" % name)
    return value


GIT_ASKPASS_SCRIPT = '''#!/bin/sh
case "$1" in
  *Username*) printf '%s\\n' "$ODUPILOT_GIT_USERNAME" ;;
  *Password*) printf '%s\\n' "$ODUPILOT_GIT_PASSWORD" ;;
  *) exit 1 ;;
esac
'''


class WorkspaceManager:
    def __init__(self):
        self.root = os.path.realpath(WORKSPACE_ROOT)
        self.max_attachment_bytes = int(os.getenv(
            "ODUPILOT_ATTACHMENT_MAX_BYTES", str(25 * 1024 * 1024)))

    def _workspace(self, command):
        workspace = command.get("workspace") or {}
        configured_root = os.path.realpath(workspace.get("root") or "")
        if configured_root != self.root:
            raise RuntimeError("Odoo and sidecar workspace roots do not match")
        directory = self._safe_path(workspace.get("directory"))
        if directory != self._safe_path(command.get("directory")):
            raise RuntimeError("AI session directory metadata does not match")
        workspace["directory"] = directory
        workspace["root"] = self.root
        return workspace

    def _safe_path(self, path):
        if not path or not os.path.isabs(path):
            raise RuntimeError("AI workspace path must be absolute")
        candidate = os.path.realpath(path)
        try:
            if os.path.commonpath([self.root, candidate]) != self.root:
                raise RuntimeError("AI workspace path is outside the workspace root")
        except ValueError:
            raise RuntimeError("AI workspace path is invalid")
        return candidate

    def _validate_layout(self, workspace):
        directory = workspace["directory"]
        workspace_type = workspace.get("type")
        if workspace_type == "files":
            expected_parent = os.path.join(self.root, "users")
            if os.path.commonpath([expected_parent, directory]) != expected_parent:
                raise RuntimeError("File workspace path is invalid")
            return
        if workspace_type != "worktree":
            raise RuntimeError("Unsupported AI workspace type")
        branch = workspace.get("branch") or ""
        if (not branch or os.path.basename(directory) != branch
                or os.path.dirname(directory) != os.path.join(
                    self.root, "worktrees")):
            raise RuntimeError("Developer worktree path is invalid")
        repository = self._safe_path(workspace.get("repository_directory"))
        expected = os.path.join(
            self.root, "repo", "profile_%s" % workspace.get("profile_id"))
        if repository != expected:
            raise RuntimeError("Developer repository cache path is invalid")
        workspace["repository_directory"] = repository

    @contextmanager
    def _git_environment(self, github_pat):
        environment = os.environ.copy()
        environment.update({
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
        })
        askpass_path = False
        try:
            descriptor, askpass_path = tempfile.mkstemp(
                prefix="odupilot-git-askpass-")
            with os.fdopen(descriptor, "w", encoding="utf-8") as helper:
                helper.write(GIT_ASKPASS_SCRIPT)
            os.chmod(askpass_path, 0o700)
            environment.update({
                "GIT_ASKPASS": askpass_path,
                "GIT_ASKPASS_REQUIRE": "force",
                "ODUPILOT_GIT_USERNAME": "x-access-token",
                "ODUPILOT_GIT_PASSWORD": github_pat,
            })
            yield environment
        finally:
            if askpass_path:
                try:
                    os.unlink(askpass_path)
                except FileNotFoundError:
                    pass

    def _run_git(self, arguments, github_pat="", check=True):
        try:
            with self._git_environment(github_pat) as environment:
                result = subprocess.run(
                    arguments,
                    check=False,
                    timeout=300,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=environment,
                    text=True,
                )
        except FileNotFoundError:
            raise RuntimeError("Git is not installed in the AI chat sidecar")
        except subprocess.TimeoutExpired:
            raise RuntimeError("Git timed out while preparing the developer workspace")
        if check and result.returncode:
            detail = (result.stderr or result.stdout or "").strip()
            if github_pat:
                detail = detail.replace(github_pat, "***")
            raise RuntimeError(
                "Git could not prepare the developer workspace: %s" % (
                    detail or "unknown Git error"))
        return result

    def _prepare_files(self, workspace):
        directory = workspace["directory"]
        os.makedirs(directory, mode=0o700, exist_ok=True)
        if not os.path.isdir(os.path.join(directory, ".git")):
            self._run_git(["git", "init", "--quiet", directory])

    def _prepare_worktree(self, workspace):
        repository = workspace["repository_directory"]
        directory = workspace["directory"]
        branch = workspace["branch"]
        repo_url = workspace.get("repo_url") or ""
        github_pat = workspace.get("github_pat") or ""
        base_branch = workspace.get("base_branch") or "prod"
        if not repo_url or not github_pat:
            raise RuntimeError("Developer repository credentials are missing")
        os.makedirs(os.path.dirname(repository), mode=0o700, exist_ok=True)
        with open(repository + ".lock", "a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            if not os.path.isdir(os.path.join(repository, ".git")):
                if os.path.exists(repository):
                    raise RuntimeError(
                        "Developer repository cache is not a Git repository")
                self._run_git([
                    "git", "clone", "--no-checkout", "--origin", "origin",
                    repo_url, repository,
                ], github_pat)
            else:
                configured_url = self._run_git([
                    "git", "-C", repository, "remote", "get-url", "origin",
                ], github_pat).stdout.strip().rstrip("/")
                if configured_url != repo_url.rstrip("/"):
                    raise RuntimeError(
                        "Developer repository cache uses a different origin URL")
            self._run_git([
                "git", "-C", repository, "fetch", "--prune", "origin",
            ], github_pat)
            base_reference = "refs/remotes/origin/%s" % base_branch
            base_exists = self._run_git([
                "git", "-C", repository, "show-ref", "--verify", "--quiet",
                base_reference,
            ], github_pat, check=False)
            if base_exists.returncode:
                raise RuntimeError(
                    "Developers base branch does not exist in the repository")
            if os.path.isdir(directory):
                if not os.path.isfile(os.path.join(directory, ".git")):
                    raise RuntimeError(
                        "Developer worktree path already exists and is invalid")
                return
            branch_exists = self._run_git([
                "git", "-C", repository, "show-ref", "--verify", "--quiet",
                "refs/heads/%s" % branch,
            ], github_pat, check=False)
            if not branch_exists.returncode:
                self._run_git([
                    "git", "-C", repository, "branch", "-D", branch,
                ], github_pat)
            os.makedirs(os.path.dirname(directory), mode=0o700, exist_ok=True)
            self._run_git([
                "git", "-C", repository, "worktree", "add",
                "-b", branch, directory, "origin/%s" % base_branch,
            ], github_pat)

    def _environment_directory(self, workspace):
        session_id = workspace.get("session_id")
        if (isinstance(session_id, bool) or not isinstance(session_id, int)
                or session_id <= 0):
            raise RuntimeError("AI session identifier is invalid")
        return self._safe_path(os.path.join(
            self.root, ".odupilot-environment", "session_%s" % session_id))

    def _sync_environment(self, command, workspace):
        environment = command.get("opencode_environment") or {}
        if not isinstance(environment, dict):
            raise RuntimeError("OpenCode session environment is invalid")
        if any(
                not isinstance(name, str)
                or not ENVIRONMENT_NAME_PATTERN.fullmatch(name)
                or not isinstance(value, str)
                for name, value in environment.items()):
            raise RuntimeError("OpenCode session environment is invalid")
        directory = self._environment_directory(workspace)
        previous = {}
        if os.path.isdir(directory):
            for name in os.listdir(directory):
                path = os.path.join(directory, name)
                if os.path.isfile(path):
                    with open(path, encoding="utf-8") as secret_file:
                        previous[name] = secret_file.read()
        changed = previous != environment
        if not environment:
            shutil.rmtree(directory, ignore_errors=True)
            return {}, changed
        os.makedirs(directory, mode=0o700, exist_ok=True)
        os.chmod(directory, 0o700)
        for name, value in environment.items():
            path = os.path.join(directory, name)
            temporary_path = path + ".tmp"
            with open(temporary_path, "w", encoding="utf-8") as secret_file:
                secret_file.write(value)
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, path)
        for name in set(previous) - set(environment):
            try:
                os.unlink(os.path.join(directory, name))
            except FileNotFoundError:
                pass
        return {
            name: os.path.join(directory, name)
            for name in environment
        }, changed

    def _replace_environment_references(self, value, paths):
        if isinstance(value, dict):
            return {
                key: self._replace_environment_references(item, paths)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [
                self._replace_environment_references(item, paths)
                for item in value
            ]
        if isinstance(value, str):
            for name, path in paths.items():
                value = value.replace(
                    "{env:%s}" % name, "{file:%s}" % path)
        return value

    def write_config(self, command):
        workspace = self._workspace(command)
        self._validate_layout(workspace)
        directory = workspace["directory"]
        if not os.path.isdir(directory):
            raise RuntimeError("AI session workspace does not exist")
        environment_paths, environment_changed = self._sync_environment(
            command, workspace)
        config = self._replace_environment_references(
            command["opencode_config"], environment_paths)
        content = json.dumps(
            config, ensure_ascii=False, indent=2) + "\n"
        path = os.path.join(directory, "opencode.json")
        previous = ""
        try:
            with open(path, encoding="utf-8") as config_file:
                previous = config_file.read()
        except FileNotFoundError:
            pass
        temporary_path = path + ".tmp"
        with open(temporary_path, "w", encoding="utf-8") as config_file:
            config_file.write(content)
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, path)
        return previous != content or environment_changed

    def prepare(self, command):
        workspace = self._workspace(command)
        workspace["profile_id"] = (
            command.get("workspace") or {}).get("profile_id")
        self._validate_layout(workspace)
        if workspace["type"] == "worktree":
            self._prepare_worktree(workspace)
        else:
            self._prepare_files(workspace)
        self.write_config(command)

    def _write_private_file(self, path, data):
        temporary_path = path + ".tmp"
        mode = "wb" if isinstance(data, bytes) else "w"
        encoding = None if isinstance(data, bytes) else "utf-8"
        with open(temporary_path, mode, encoding=encoding) as target:
            target.write(data)
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, path)

    def _convert_attachment(self, path, relative):
        # Модель не читает бинарный документ, поэтому кладём рядом Markdown
        # от AnyDoc. Формат определяется по содержимому файла.
        if anydoc is None:
            return ""
        try:
            markdown = anydoc.to_markdown(path)
        except anydoc.UnsupportedError:
            return ""
        except anydoc.ConvertError as error:
            _logger.warning("AnyDoc could not convert %s: %s", relative, error)
            return ""
        except Exception:
            _logger.exception("AnyDoc failed on %s", relative)
            return ""
        self._write_private_file(path + ".md", markdown)
        return relative + ".md"

    def write_attachments(self, command):
        workspace = self._workspace(command)
        self._validate_layout(workspace)
        directory = workspace["directory"]
        total = 0
        conversions = []
        for attachment in command.get("payload", {}).get("attachments", []):
            relative = os.path.normpath(attachment.get("path") or "")
            if (not relative or os.path.isabs(relative)
                    or relative == ".." or relative.startswith("../")):
                raise RuntimeError("AI chat attachment path is invalid")
            path = os.path.realpath(os.path.join(directory, relative))
            if os.path.commonpath([directory, path]) != directory:
                raise RuntimeError("AI chat attachment path is invalid")
            try:
                data = base64.b64decode(
                    attachment.get("data") or "", validate=True)
            except (binascii.Error, ValueError, TypeError):
                raise RuntimeError("AI chat attachment data is invalid")
            total += len(data)
            if total > self.max_attachment_bytes:
                raise RuntimeError("AI chat attachments exceed the size limit")
            os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
            self._write_private_file(path, data)
            markdown_relative = self._convert_attachment(path, relative)
            if markdown_relative:
                conversions.append(markdown_relative)
        return conversions

    def _github_repository(self, repo_url):
        parsed = urlparse(repo_url)
        if parsed.scheme != "https" or parsed.hostname != "github.com":
            return False
        path = parsed.path.strip("/")
        if path.endswith(".git"):
            path = path[:-4]
        parts = path.split("/")
        if len(parts) != 2 or not all(parts):
            return False
        return parts[0], parts[1]

    def _github_pull_request(
            self, repo_url, github_pat, branch, base_branch, title, body):
        repository = self._github_repository(repo_url)
        if not repository:
            return "", ""
        owner, name = repository
        api_url = "https://api.github.com/repos/%s/%s" % (owner, name)
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer %s" % github_pat,
            "X-GitHub-Api-Version": "2022-11-28",
        }

        def request(method, path, params=None, payload=None):
            response = requests.request(
                method,
                api_url + path,
                headers=headers,
                params=params,
                json=payload,
                timeout=30,
            )
            try:
                response.raise_for_status()
            except requests.HTTPError:
                detail = (response.text or "").strip()[:1000]
                raise RuntimeError(
                    "GitHub could not create or update the pull request: %s" % (
                        detail or "unknown GitHub API error"))
            return response.json()

        existing = request("GET", "/pulls", params={
            "state": "open",
            "head": "%s:%s" % (owner, branch),
            "base": base_branch,
        })
        values = {
            "title": title,
            "body": body,
            "base": base_branch,
        }
        if existing:
            pull_request = request(
                "PATCH", "/pulls/%s" % existing[0]["number"],
                payload=values,
            )
        else:
            values["head"] = branch
            pull_request = request("POST", "/pulls", payload=values)
        branch_url = "https://github.com/%s/%s/tree/%s" % (
            owner, name, branch)
        return pull_request.get("html_url") or "", branch_url

    def publish(self, command):
        workspace = self._workspace(command)
        workspace["profile_id"] = (
            command.get("workspace") or {}).get("profile_id")
        self._validate_layout(workspace)
        if workspace["type"] != "worktree":
            raise RuntimeError("Only developer worktrees can be published")
        directory = workspace["directory"]
        branch = workspace.get("branch") or ""
        repo_url = workspace.get("repo_url") or ""
        github_pat = workspace.get("github_pat") or ""
        base_branch = workspace.get("base_branch") or "prod"
        payload = command.get("payload") or {}
        title = payload.get("title") or ""
        body = payload.get("body") or ""
        if not repo_url or not github_pat:
            raise RuntimeError("Developer repository credentials are missing")
        if not isinstance(title, str) or not title.strip():
            raise RuntimeError("Pull request title is missing")
        if not isinstance(body, str):
            raise RuntimeError("Pull request body is invalid")
        current_branch = self._run_git([
            "git", "-C", directory, "branch", "--show-current",
        ]).stdout.strip()
        if current_branch != branch:
            raise RuntimeError("Developer worktree is on an unexpected branch")
        status = self._run_git([
            "git", "-C", directory, "status", "--porcelain=v1",
            "--untracked-files=all",
        ]).stdout.splitlines()
        dirty = []
        for line in status:
            path = line[3:] if len(line) > 3 else ""
            generated = (
                path == "opencode.json"
                or path.startswith("attachments/"))
            if not (line.startswith("?? ") and generated):
                dirty.append(line)
        if dirty:
            raise RuntimeError(
                "Developer worktree has uncommitted changes; commit them before publishing")
        protected = self._run_git([
            "git", "-C", directory, "diff", "--name-only",
            "origin/%s...HEAD" % base_branch,
        ]).stdout.splitlines()
        if any(path == "opencode.json" or path.startswith("attachments/")
               for path in protected):
            raise RuntimeError(
                "Developer branch contains protected AI chat workspace files")
        ahead = self._run_git([
            "git", "-C", directory, "rev-list", "--count",
            "origin/%s..HEAD" % base_branch,
        ]).stdout.strip()
        if not ahead or int(ahead) < 1:
            raise RuntimeError(
                "Developer branch has no commits to publish")
        self._run_git([
            "git", "-C", directory, "push", "--set-upstream", "origin",
            branch,
        ], github_pat)
        pull_request_url, branch_url = self._github_pull_request(
            repo_url,
            github_pat,
            branch,
            base_branch,
            title.strip()[:200],
            body[:10000],
        )
        return {
            "branch": branch,
            "branch_url": branch_url,
            "pull_request_url": pull_request_url,
        }

    def cleanup(self, command):
        workspace = self._workspace(command)
        workspace["profile_id"] = (
            command.get("workspace") or {}).get("profile_id")
        self._validate_layout(workspace)
        shutil.rmtree(
            self._environment_directory(workspace), ignore_errors=True)
        directory = workspace["directory"]
        if workspace["type"] == "files":
            shutil.rmtree(directory, ignore_errors=True)
            return
        repository = workspace["repository_directory"]
        if not os.path.isdir(os.path.join(repository, ".git")):
            shutil.rmtree(directory, ignore_errors=True)
            return
        with open(repository + ".lock", "a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            removed = self._run_git([
                "git", "-C", repository, "worktree", "remove",
                "--force", directory,
            ], check=False)
            if removed.returncode:
                shutil.rmtree(directory, ignore_errors=True)
            self._run_git([
                "git", "-C", repository, "worktree", "prune",
            ], check=False)


class OdooClient:
    def __init__(self):
        self.url = _required("ODOO_URL").rstrip("/")
        self.database = _required("ODOO_DATABASE")
        self.login = _required("ODOO_LOGIN")
        self.password = _required("ODOO_PASSWORD")
        self.uid = False
        self.http = requests.Session()
        self.http_authenticated = False

    def authenticate(self):
        common = xmlrpc.client.ServerProxy(
            self.url + "/xmlrpc/2/common", allow_none=True)
        self.uid = common.authenticate(
            self.database, self.login, self.password, {})
        if not self.uid:
            raise RuntimeError("Odoo authentication failed")
        if not self.http_authenticated:
            self.authenticate_http()
        _logger.info("Connected to Odoo as uid=%s", self.uid)

    def authenticate_http(self):
        response = self.http.post(
            self.url + "/web/session/authenticate",
            json={
                "jsonrpc": "2.0",
                "method": "call",
                "params": {
                    "db": self.database,
                    "login": self.login,
                    "password": self.password,
                },
                "id": None,
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("error") or not (data.get("result") or {}).get("uid"):
            raise RuntimeError("Odoo HTTP session authentication failed")
        self.http_authenticated = True

    def wait_for_commands(self, last=0):
        response = self.http.post(
            self.url + "/odupilot/bridge/poll",
            json={
                "jsonrpc": "2.0",
                "method": "call",
                "params": {
                    "last": last,
                },
                "id": None,
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("error"):
            raise RuntimeError("Odoo command polling failed: %s" % data["error"])
        notifications = data.get("result") or []
        if notifications:
            last = max(item.get("id", last) for item in notifications)
        else:
            time.sleep(1)
        return last, notifications

    def execute(self, model, method, args=None, kwargs=None):
        if not self.uid:
            self.authenticate()
        objects = xmlrpc.client.ServerProxy(
            self.url + "/xmlrpc/2/object", allow_none=True)
        try:
            return objects.execute_kw(
                self.database,
                self.uid,
                self.password,
                model,
                method,
                _xmlrpc_safe(args or []),
                _xmlrpc_safe(kwargs or {}),
            )
        except xmlrpc.client.Fault:
            raise
        except Exception:
            self.uid = False
            raise


class OpenCodeClient:
    def __init__(self):
        self.url = _required("OPENCODE_URL").rstrip("/")
        self.auth = (
            os.getenv("OPENCODE_SERVER_USERNAME", "opencode"),
            _required("OPENCODE_SERVER_PASSWORD"),
        )

    def request(self, method, path, directory=False, payload=False, stream=False):
        params = {"directory": directory} if directory else None
        response = requests.request(
            method,
            self.url + path,
            params=params,
            json=payload if payload is not False else None,
            auth=self.auth,
            timeout=(10, None if stream else 60),
            stream=stream,
        )
        response.raise_for_status()
        return response

    def create_session(self, command):
        response = self.request(
            "POST",
            "/session",
            directory=command["directory"],
            payload={"title": command["title"]},
        )
        return response.json()

    def health(self):
        started_at = time.monotonic()
        response = self.request("GET", "/global/health")
        payload = response.json()
        payload["latency_ms"] = max(
            0, int((time.monotonic() - started_at) * 1000))
        return payload

    def dispose_instance(self, command):
        self.request(
            "POST",
            "/instance/dispose",
            directory=command["directory"],
            payload={},
        )

    def prompt_async(self, command):
        payload = command["payload"]
        # OpenCode сравнивает ID user/assistant сообщений лексикографически.
        # Произвольный детерминированный messageID может оказаться "новее"
        # серверного assistant ID и зациклить turn даже после finish=stop.
        # Идемпотентность повторной доставки сохраняем на стабильном part ID,
        # а сортируемый message ID всегда оставляем генерировать OpenCode.
        prompt_part_id = "prt_%s" % payload["message_id"].split("_", 1)[-1]
        if int(command.get("attempts", 1)) > 1:
            for message in self.list_messages(command):
                if any(
                        part.get("id") == prompt_part_id
                        for part in message.get("parts", [])):
                    return {
                        "already_admitted": True,
                        "session_busy": self.session_busy(command),
                    }
        body = {
            "model": {
                "providerID": "litellm",
                "modelID": command["model"],
            },
            "parts": [{
                "id": prompt_part_id,
                "type": "text",
                "text": payload["text"],
            }],
        }
        if payload.get("system"):
            body["system"] = payload["system"]
        self.request(
            "POST",
            "/session/%s/prompt_async" % command["opencode_session_id"],
            directory=command["directory"],
            payload=body,
        )
        return {}

    def session_statuses(self, directory):
        response = self.request(
            "GET",
            "/session/status",
            directory=directory,
        )
        return response.json()

    def session_busy(self, command):
        statuses = self.session_statuses(command["directory"])
        return command["opencode_session_id"] in statuses

    def abort(self, command):
        self.request(
            "POST",
            "/session/%s/abort" % command["opencode_session_id"],
            directory=command["directory"],
            payload={},
        )

    def close_session(self, command):
        session_id = command.get("opencode_session_id")
        if not session_id:
            return
        try:
            self.request(
                "DELETE",
                "/session/%s" % session_id,
                directory=command["directory"],
            )
        except requests.HTTPError as error:
            if error.response is None or error.response.status_code != 404:
                raise

    def respond_permission(self, command):
        payload = command["payload"]
        try:
            self.request(
                "POST",
                "/permission/%s/reply" % payload["permission_id"],
                directory=command["directory"],
                payload={"reply": payload["response"]},
            )
        except requests.HTTPError as error:
            # OpenCode удаляет resolved request. Повтор после потерянного ack
            # или автоматического Always должен оставаться идемпотентным.
            if error.response is None or error.response.status_code != 404:
                raise

    def list_messages(self, session):
        response = self.request(
            "GET",
            "/session/%s/message" % session["opencode_session_id"],
            directory=session["directory"],
        )
        return response.json()

    def events(self):
        return self.request("GET", "/global/event", stream=True)


class Bridge:
    def __init__(self):
        self.odoo = OdooClient()
        self.opencode = OpenCodeClient()
        self.workspace = WorkspaceManager()
        self.batch_size = int(os.getenv("ODUPILOT_EVENT_BATCH_SIZE", "50"))
        self.flush_seconds = float(
            os.getenv("ODUPILOT_EVENT_FLUSH_SECONDS", "0.5"))
        self.events = queue.Queue()
        self.command_wakeup = threading.Event()
        self.sessions = {}
        self.sessions_lock = threading.Lock()
        self.started_at = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.gmtime())

    def run(self):
        self.odoo.authenticate()
        self.refresh_sessions(backfill=True)
        threads = [
            threading.Thread(target=self.command_loop, daemon=True),
            threading.Thread(target=self.command_event_loop, daemon=True),
            threading.Thread(target=self.event_loop, daemon=True),
            threading.Thread(target=self.ingest_loop, daemon=True),
            threading.Thread(target=self.heartbeat_loop, daemon=True),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    def report_heartbeat(self):
        values = {
            "bridge_version": BRIDGE_VERSION,
            "bridge_started_at": self.started_at,
            "event_queue_size": self.events.qsize(),
            "opencode_healthy": False,
            "opencode_version": "",
            "opencode_latency_ms": 0,
            "error": "",
        }
        try:
            health = self.opencode.health()
            values.update({
                "opencode_healthy": bool(health.get("healthy")),
                "opencode_version": health.get("version") or "",
                "opencode_latency_ms": health.get("latency_ms") or 0,
            })
            if not values["opencode_healthy"]:
                values["error"] = "OpenCode health check reported unhealthy"
        except Exception as error:
            values["error"] = str(error)[:2000]
        self.odoo.execute(
            "odupilot.runtime", "bridge_heartbeat", [values])

    def heartbeat_loop(self):
        delay = 1
        while True:
            try:
                self.report_heartbeat()
                delay = 30
            except Exception:
                _logger.exception("Could not report AI chat runtime heartbeat")
                delay = min(max(delay * 2, 2), 30)
            time.sleep(delay)

    def refresh_sessions(self, backfill=False):
        sessions = self.odoo.execute(
            "odupilot.session", "bridge_sessions")
        with self.sessions_lock:
            self.sessions = {
                item["opencode_session_id"]: item
                for item in sessions
                if item.get("opencode_session_id")
            }
        if backfill:
            for session in sessions:
                if session.get("opencode_session_id"):
                    self.backfill(session)

    def command_loop(self):
        while True:
            try:
                # Очищаем сигнал до claim: событие между claim и wait останется
                # установленным, а уже созданная команда попадёт в сам claim.
                self.command_wakeup.clear()
                commands = self.odoo.execute(
                    "odupilot.command", "bridge_claim", [10])
                if not commands:
                    self.command_wakeup.wait()
                    continue
                for command in commands:
                    self.process_command(command)
            except Exception:
                _logger.exception("Command polling failed")
                self.command_wakeup.wait(timeout=2)

    def command_event_loop(self):
        last = 0
        delay = 1
        while True:
            try:
                last, _notifications = self.odoo.wait_for_commands(last)
                # Пустой ответ раз в 50 секунд запускает reconciliation.
                self.command_wakeup.set()
                delay = 1
            except Exception:
                _logger.exception("Odoo command polling disconnected")
                # При недоступном bus сохраняем редкий pull fallback.
                self.command_wakeup.set()
                time.sleep(delay)
                delay = min(delay * 2, 30)
                try:
                    self.odoo.http_authenticated = False
                    self.odoo.authenticate_http()
                except Exception:
                    _logger.exception("Could not refresh Odoo HTTP session")

    def _announce_conversions(self, command, conversions):
        # Odoo знает только пути вложений; какие из них AnyDoc действительно
        # разобрал, выясняется здесь, поэтому список дописывает мост.
        if not conversions:
            return
        payload = command["payload"]
        payload["text"] = "%s\n\nAnyDoc Markdown conversions:\n%s" % (
            payload.get("text") or "",
            "\n".join("- %s" % path for path in conversions),
        )

    def process_command(self, command):
        try:
            command_type = command["command_type"]
            result = {}
            if command_type == "init":
                self.workspace.prepare(command)
                result = self.opencode.create_session(command)
            elif command_type == "reset":
                # Каталог сессии и её конфигурация остаются прежними: меняется
                # только разговор, поэтому prepare() здесь не нужен.
                self.opencode.close_session(command)
                result = self.opencode.create_session(command)
            elif command_type == "prompt":
                config_changed = self.workspace.write_config(command)
                if config_changed:
                    self.opencode.dispose_instance(command)
                conversions = self.workspace.write_attachments(command)
                self._announce_conversions(command, conversions)
                result = self.opencode.prompt_async(command)
            elif command_type == "abort":
                self.opencode.abort(command)
            elif command_type == "permission":
                self.opencode.respond_permission(command)
            elif command_type == "publish":
                result = self.workspace.publish(command)
            elif command_type == "close":
                self.opencode.close_session(command)
                self.workspace.cleanup(command)
            else:
                raise RuntimeError("Unsupported command type: %s" % command_type)
            self.odoo.execute(
                "odupilot.command",
                "bridge_ack",
                [command["id"], True, result, ""],
            )
            self.refresh_sessions()
        except Exception as error:
            _logger.exception("Command %s failed", command.get("id"))
            try:
                acknowledgement = self.odoo.execute(
                    "odupilot.command",
                    "bridge_ack",
                    [command["id"], False, {}, str(error)[:2000]],
                )
                retry_after = (
                    acknowledgement.get("retry_after", 0)
                    if isinstance(acknowledgement, dict)
                    else min(2 ** int(command.get("attempts", 1)), 60)
                )
                if retry_after:
                    timer = threading.Timer(
                        retry_after, self.command_wakeup.set)
                    timer.daemon = True
                    timer.start()
            except Exception:
                _logger.exception("Could not report command failure to Odoo")

    def iter_event_lines(self, response):
        # requests.iter_lines(decode_unicode=True) режет чанк через
        # str.splitlines(), а она ломает строку не только на \n, но и на \v,
        # \f, \x1c-\x1e, \x85, U+2028 и U+2029. JSON.stringify в OpenCode эти
        # символы не экранирует, поэтому событие с таким символом внутри
        # текста приезжало двумя кусками и роняло json.loads. Режем сами и
        # только по переводу строки SSE.
        buffer = b""
        for chunk in response.iter_content(chunk_size=8192):
            if not chunk:
                continue
            buffer += chunk
            while True:
                index = buffer.find(b"\n")
                if index < 0:
                    break
                line = buffer[:index].rstrip(b"\r")
                buffer = buffer[index + 1:]
                if line:
                    yield line

    def event_loop(self):
        delay = 1
        while True:
            try:
                response = self.opencode.events()
                # Поток открыт до сверки: то, что произошло в обрыве,
                # доберётся из истории, а завершённая в OpenCode сессия
                # перестанет висеть busy.
                self.refresh_sessions(backfill=True)
                self.reconcile_busy_sessions()
                delay = 1
                for line in self.iter_event_lines(response):
                    if not line.startswith(b"data:"):
                        continue
                    try:
                        raw = json.loads(line[5:].strip())
                    except ValueError:
                        # Одно битое событие не должно ронять весь поток:
                        # вместе с переподключением терялся session.idle и
                        # сессия оставалась busy до watchdog'а.
                        _logger.warning(
                            "Skipping malformed OpenCode SSE line (%s bytes)",
                            len(line))
                        continue
                    self.queue_event(raw)
            except Exception:
                _logger.exception("OpenCode SSE disconnected")
                time.sleep(delay)
                delay = min(delay * 2, 30)

    def reconcile_busy_sessions(self):
        # Сверка после переподключения: Odoo держит сессию busy, а OpenCode её
        # уже не выполняет — значит завершающее событие потерялось в обрыве.
        with self.sessions_lock:
            sessions = list(self.sessions.values())
        stale = [
            session for session in sessions
            if session.get("state") == "busy"
            and _busy_grace_expired(session.get("busy_since"))
        ]
        if not stale:
            return
        statuses = {}
        for session in stale:
            directory = session.get("directory") or ""
            if directory not in statuses:
                try:
                    statuses[directory] = self.opencode.session_statuses(
                        directory)
                except Exception:
                    _logger.exception(
                        "Could not read OpenCode session status for %s",
                        directory)
                    statuses[directory] = False
            status = statuses[directory]
            session_id = session["opencode_session_id"]
            if status is False or session_id in status:
                continue
            _logger.info(
                "Reconciling stale busy OpenCode session %s", session_id)
            # external_id держится на busy_since: повторная сверка того же
            # зависания дедуплицируется в Odoo, а новый turn получит свой ID.
            self.events.put({
                "opencode_session_id": session_id,
                "event_type": "session.idle",
                "external_id": "bridge.reconcile.idle:%s:%s" % (
                    session_id, session.get("busy_since") or ""),
                "payload": {
                    "type": "session.idle",
                    "properties": {"sessionID": session_id},
                    "bridge_reconciled": True,
                },
            })

    def queue_event(self, raw):
        payload = raw.get("payload") or raw
        session_id = self.find_session_id(payload)
        if not session_id:
            return
        with self.sessions_lock:
            session = self.sessions.get(session_id)
        if not session:
            return
        event_type = payload.get("type", "unknown")
        serialized = json.dumps(raw, sort_keys=True, separators=(",", ":"))
        external_id = raw.get("id") or "%s:%s" % (
            event_type,
            hashlib.sha256(serialized.encode()).hexdigest(),
        )
        self.events.put({
            "opencode_session_id": session_id,
            "event_type": event_type,
            "external_id": external_id,
            "payload": raw,
        })
        if event_type in ("session.idle", "session.error"):
            self.backfill(session)

    def find_session_id(self, value):
        if isinstance(value, dict):
            for key in ("sessionID", "sessionId", "session_id"):
                if value.get(key):
                    return value[key]
            for key in ("info", "part", "properties", "payload"):
                found = self.find_session_id(value.get(key))
                if found:
                    return found
        return False

    def backfill(self, session):
        try:
            for message in self.opencode.list_messages(session):
                info = message.get("info") or {}
                if info.get("role") != "assistant":
                    continue
                if (not (info.get("time") or {}).get("completed")
                        and not info.get("error")):
                    continue
                message_id = info.get("id")
                if not message_id:
                    continue
                self.events.put({
                    "opencode_session_id": session["opencode_session_id"],
                    "event_type": "bridge.backfill.message",
                    "external_id": "message:%s" % message_id,
                    "payload": message,
                })
        except Exception:
            _logger.exception(
                "Backfill failed for OpenCode session %s",
                session.get("opencode_session_id"),
            )

    def ingest_loop(self):
        while True:
            batch = []
            try:
                batch.append(self.events.get(timeout=self.flush_seconds))
            except queue.Empty:
                continue
            deadline = time.monotonic() + self.flush_seconds
            while len(batch) < self.batch_size:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    batch.append(self.events.get(timeout=remaining))
                except queue.Empty:
                    break
            try:
                self.odoo.execute(
                    "odupilot.session", "ingest_events", [batch])
                # session.idle может сделать следующий prompt доступным.
                self.command_wakeup.set()
            except Exception:
                _logger.exception("Could not ingest %s OpenCode events", len(batch))
                for item in batch:
                    self.events.put(item)
                time.sleep(2)


if __name__ == "__main__":
    Bridge().run()
