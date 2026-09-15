# -*- encoding: utf-8 -*-
import json
import re
from urllib.parse import urlparse

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


MCP_CODE_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')
HEADER_NAME_PATTERN = re.compile(r"^[!#$%&'*+.^_`|~0-9a-zA-Z-]+$")
ENVIRONMENT_NAME_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
OAUTH_FIELDS = {
    'clientId',
    'clientSecret',
    'scope',
    'callbackPort',
    'redirectUri',
}


class AiChatMcpServer(models.Model):
    _name = 'odupilot.mcp.server'
    _description = 'OduPilot MCP Server'
    _order = 'name, id'

    name = fields.Char(required=True)
    code = fields.Char(
        required=True,
        index=True,
        help='Unique OpenCode MCP server name used as a tool prefix.',
    )
    active = fields.Boolean(default=True)
    server_type = fields.Selection([
        ('remote', 'Remote HTTP'),
        ('local', 'Local command'),
    ], required=True, default='remote')
    enabled = fields.Boolean(
        default=True,
        help='Enable this server when OpenCode loads the workspace.',
    )
    timeout = fields.Integer(
        string='Timeout (ms)',
        required=True,
        default=5000,
        help='Positive timeout in milliseconds for MCP server requests.',
    )
    url = fields.Char(
        string='Remote URL',
        help='Absolute HTTP or HTTPS Streamable HTTP endpoint.',
    )
    headers_json = fields.Text(
        string='Headers',
        default='{}',
        help='JSON object with HTTP header names and string values.',
    )
    oauth_json = fields.Text(
        string='OAuth',
        help='JSON object with OpenCode OAuth options, or false to disable OAuth auto-detection.',
    )
    command_json = fields.Text(
        string='Command',
        default='[]',
        help='JSON array containing the executable followed by its arguments.',
    )
    cwd = fields.Char(
        string='Working directory',
        help='Optional MCP process directory. Relative paths resolve from the workspace.',
    )
    environment_json = fields.Text(
        string='Environment',
        default='{}',
        help='JSON object with environment variable names and string values.',
    )

    _odupilot_mcp_server_code_unique = models.Constraint('unique(code)', 'The MCP server code must be unique.')

    @api.onchange('server_type')
    def _onchange_server_type(self):
        if self.server_type == 'remote':
            self.command_json = '[]'
            self.cwd = False
            self.environment_json = '{}'
        else:
            self.url = False
            self.headers_json = '{}'
            self.oauth_json = False

    def _parse_json(self, value, label):
        try:
            return json.loads(value)
        except (TypeError, ValueError) as error:
            raise ValidationError(_(
                '%(label)s must contain valid JSON: %(error)s',
                label=label,
                error=error,
            ))

    def _parse_string_object(self, value, label):
        parsed = self._parse_json(value or '{}', label)
        if not isinstance(parsed, dict):
            raise ValidationError(_('%s must be a JSON object.', label))
        if any(not isinstance(key, str) or not isinstance(item, str)
               for key, item in parsed.items()):
            raise ValidationError(_(
                '%s keys and values must be strings.', label))
        return parsed

    def _validated_headers(self):
        headers = self._parse_string_object(
            self.headers_json, _('Headers'))
        for name, value in headers.items():
            if not HEADER_NAME_PATTERN.fullmatch(name):
                raise ValidationError(_(
                    'Header name "%s" is not valid.', name))
            if '\r' in value or '\n' in value:
                raise ValidationError(_(
                    'Header values must not contain line breaks.'))
        return headers

    def _validated_environment(self):
        environment = self._parse_string_object(
            self.environment_json, _('Environment'))
        for name in environment:
            if not ENVIRONMENT_NAME_PATTERN.fullmatch(name):
                raise ValidationError(_(
                    'Environment variable name "%s" is not valid.', name))
        return environment

    def _validated_oauth(self):
        if not (self.oauth_json or '').strip():
            return None
        oauth = self._parse_json(self.oauth_json, _('OAuth'))
        if oauth is False:
            return False
        if not isinstance(oauth, dict):
            raise ValidationError(_(
                'OAuth must be a JSON object or false.'))
        unknown = set(oauth) - OAUTH_FIELDS
        if unknown:
            raise ValidationError(_(
                'OAuth contains unsupported options: %s.',
                ', '.join(sorted(unknown)),
            ))
        for name in ('clientId', 'clientSecret', 'scope', 'redirectUri'):
            if name in oauth and not isinstance(oauth[name], str):
                raise ValidationError(_(
                    'OAuth option "%s" must be a string.', name))
        callback_port = oauth.get('callbackPort')
        if (callback_port is not None
                and (isinstance(callback_port, bool)
                     or not isinstance(callback_port, int)
                     or not 1 <= callback_port <= 65535)):
            raise ValidationError(_(
                'OAuth callbackPort must be an integer from 1 to 65535.'))
        redirect_uri = oauth.get('redirectUri')
        if redirect_uri:
            parsed = urlparse(redirect_uri)
            if parsed.scheme not in ('http', 'https') or not parsed.netloc:
                raise ValidationError(_(
                    'OAuth redirectUri must be an absolute HTTP or HTTPS URL.'))
        return oauth

    def _validated_command(self):
        command = self._parse_json(self.command_json or '[]', _('Command'))
        if (not isinstance(command, list) or not command
                or any(not isinstance(item, str) or not item.strip()
                       or '\x00' in item for item in command)):
            raise ValidationError(_(
                'Command must be a non-empty JSON array of non-empty strings.'))
        return command

    @api.constrains(
        'code', 'server_type', 'timeout', 'url', 'headers_json',
        'oauth_json', 'command_json', 'cwd', 'environment_json',
    )
    def _check_configuration(self):
        for server in self:
            if not MCP_CODE_PATTERN.fullmatch(server.code or ''):
                raise ValidationError(_(
                    'MCP server code may contain only letters, numbers, underscores, and hyphens.'))
            if server.timeout <= 0:
                raise ValidationError(_(
                    'MCP timeout must be greater than zero.'))
            if server.server_type == 'remote':
                parsed = urlparse(server.url or '')
                if (parsed.scheme not in ('http', 'https')
                        or not parsed.netloc):
                    raise ValidationError(_(
                        'Remote MCP URL must be an absolute HTTP or HTTPS URL.'))
                if parsed.username or parsed.password:
                    raise ValidationError(_(
                        'Remote MCP URL must not contain credentials.'))
                server._validated_headers()
                server._validated_oauth()
            else:
                server._validated_command()
                server._validated_environment()
                if '\x00' in (server.cwd or ''):
                    raise ValidationError(_(
                        'MCP working directory contains an invalid character.'))

    def _opencode_config(self):
        self.ensure_one()
        values = {
            'type': self.server_type,
            'enabled': self.enabled,
            'timeout': self.timeout,
        }
        if self.server_type == 'remote':
            values['url'] = self.url
            headers = self._validated_headers()
            oauth = self._validated_oauth()
            if headers:
                values['headers'] = headers
            if oauth is not None:
                values['oauth'] = oauth
        else:
            values['command'] = self._validated_command()
            if self.cwd:
                values['cwd'] = self.cwd
            environment = self._validated_environment()
            if environment:
                values['environment'] = environment
        return values
