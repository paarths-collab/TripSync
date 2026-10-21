# backend/app/core/log_redaction.py

import logging
import re

REDACTED = "[REDACTED]"

# api_key=<value> in URLs / query strings (value ends at &, whitespace or a quote)
_QUERY_KEY_RE = re.compile(r"(api_key=)[^&\s'\"]+")
# 'api_key': 'value' or "api_key": "value" (dict repr or JSON)
_DICT_KEY_RE = re.compile(r"(['\"]api_key['\"]\s*:\s*(['\"]))[^'\"]*")


def redact_text(text: str, secret_values=()) -> str:
    """Return text with api_key values and the given literal secrets replaced."""
    text = _QUERY_KEY_RE.sub(lambda m: m.group(1) + REDACTED, text)
    text = _DICT_KEY_RE.sub(lambda m: m.group(1) + REDACTED, text)
    for secret in secret_values:
        if secret:
            text = text.replace(secret, REDACTED)
    return text


class RedactSecretsFilter(logging.Filter):
    """Formats each record and scrubs API keys before any handler writes it.

    secret_values: literal secrets to scrub. If None, the configured
    settings.OLA_MAPS_API_KEY is read on each call.
    """

    def __init__(self, secret_values=None):
        super().__init__()
        self._secret_values = secret_values

    def _secrets(self):
        if self._secret_values is not None:
            return self._secret_values
        from app.core.config import settings

        value = getattr(settings, "OLA_MAPS_API_KEY", None)
        return [value] if value else []

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            message = str(record.msg)
        record.msg = redact_text(message, self._secrets())
        record.args = ()
        if record.exc_info:
            # Formatter uses exc_text when present, so scrub the rendered traceback too.
            rendered = logging.Formatter().formatException(record.exc_info)
            record.exc_text = redact_text(rendered, self._secrets())
        return True
