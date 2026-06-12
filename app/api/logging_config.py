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

# Attributes present on every LogRecord — anything *not* here was passed via
# `extra=` and is worth surfacing as a top-level JSON field.
_RESERVED = set(
    logging.makeLogRecord({}).__dict__
) | {"message", "asctime", "taskName"}


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
        # Promote `extra=` fields (e.g. path/method) to top level.
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
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
