"""Structured application logging with secret redaction.

Rules: log events by name plus small key/value fields. Never log request bodies,
Authorization headers, passwords, tokens, keys or database credentials. Redaction is
applied in two places (defence in depth): field names in `log_event`, and credential-looking
text in the final formatted line.
"""
import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Optional

request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)

_SENSITIVE_KEY = re.compile(r"pass(word)?|secret|token|authorization|api[_-]?key|database_url|credential|cookie", re.I)
_URL_CREDENTIALS = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*://[^:/\s@]+:)([^@\s]+)(@)")
_BEARER = re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/=-]+", re.I)
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]*")
REDACTED = "[REDACTED]"
ROOT_LOGGER_NAME = "modelmind"


def scrub_text(text: str) -> str:
    text = _URL_CREDENTIALS.sub(rf"\1{REDACTED}\3", text)
    text = _BEARER.sub(rf"\1{REDACTED}", text)
    return _JWT.sub(REDACTED, text)


def redact_fields(fields: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in fields.items():
        out[key] = REDACTED if _SENSITIVE_KEY.search(key) else (scrub_text(value) if isinstance(value, str) else value)
    return out


def log_event(logger: logging.Logger, event: str, level: int = logging.INFO, **fields: Any) -> None:
    logger.log(level, event, extra={"fields": redact_fields(fields)})


def _timestamp(record: logging.LogRecord) -> str:
    return datetime.fromtimestamp(record.created, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _fields(record: logging.LogRecord) -> dict[str, Any]:
    fields = dict(getattr(record, "fields", {}) or {})
    rid = request_id_ctx.get()
    if rid:
        fields.setdefault("request_id", rid)
    return fields


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        parts = [_timestamp(record), f"{record.levelname:<7}", record.name, record.getMessage()]
        parts += [f"{k}={v}" for k, v in _fields(record).items()]
        line = " ".join(parts)
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return scrub_text(line)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "ts": _timestamp(record),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            **_fields(record),
        }
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        return scrub_text(json.dumps(data, default=str))


def configure_logging(level: str = "INFO", fmt: str = "text") -> None:
    """Idempotent: safe to call on every app creation (e.g. in tests)."""
    logger = logging.getLogger(ROOT_LOGGER_NAME)
    logger.setLevel(level)
    for h in list(logger.handlers):
        if getattr(h, "_modelmind", False):
            logger.removeHandler(h)
    handler = logging.StreamHandler(sys.stderr)
    handler._modelmind = True  # type: ignore[attr-defined]
    handler.setFormatter(JsonFormatter() if fmt == "json" else TextFormatter())
    logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")
