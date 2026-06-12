"""Single-line JSON logging for the container.

Cloudflare Workers Logs captures container stdout **per physical line** —
a multi-line Python traceback becomes one log entry per frame, which is
unreadable and unsearchable. We emit one JSON object per record instead:
the traceback lives in a single string field, so `json.dumps` escapes its
newlines to `\\n` and the whole record stays on one line = one entry.

`configure_logging()` is idempotent and must run before uvicorn installs
its own handlers (call it at import time in `main`).
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

# uvicorn attaches its own StreamHandlers to these; we replace them so every
# record flows through the JSON formatter (otherwise access/error logs stay
# multi-line text).
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")

# Structured fields callers attach via logging's `extra=`; promoted to
# top-level JSON keys when present. Add new keys here as call sites grow —
# cheaper than scanning every record's __dict__ on the logging hot path.
_EXTRA_FIELDS = ("path", "method")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in _EXTRA_FIELDS:
            if key in record.__dict__:
                payload[key] = record.__dict__[key]
        if record.exc_info:
            # Single string — json.dumps escapes the embedded newlines.
            payload["traceback"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # Detach uvicorn's text handlers; let records propagate to root's JSON one.
    for name in _UVICORN_LOGGERS:
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
