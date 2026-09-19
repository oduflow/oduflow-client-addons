from odoo import _ as odoo_translate
# -*- encoding: utf-8 -*-
import re
from urllib.parse import urlparse

from .message_renderer import _source_text
from odoo.exceptions import ValidationError


GIT_REF_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9._/-]*$')


def validate_http_url(value, label, https_only=False, env=None):
    _ = odoo_translate if env is not None else _source_text
    parsed = urlparse(value or '')
    valid_schemes = ('https',) if https_only else ('http', 'https')
    if parsed.scheme not in valid_schemes or not parsed.netloc:
        if https_only:
            raise ValidationError(_('%s must be an absolute HTTPS URL.', label))
        raise ValidationError(_('%s must be an absolute HTTP or HTTPS URL.', label))
    if parsed.username or parsed.password:
        raise ValidationError(_('%s must not contain credentials.', label))
    return value.rstrip('/')


def validate_git_ref(value, env=None):
    _ = odoo_translate if env is not None else _source_text
    value = (value or '').strip()
    invalid = (
        not GIT_REF_PATTERN.fullmatch(value)
        or value.startswith('-')
        or value.endswith(('/', '.'))
        or '..' in value
        or '@{' in value
        or '//' in value
        or '/.' in value
        or '.lock' in value
    )
    if invalid:
        raise ValidationError(_(
            'Developers base branch must be a valid Git branch name.'))
    return value
