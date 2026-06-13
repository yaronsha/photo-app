"""Single-line JSON logging.

Cloudflare Workers Logs splits container stdout per line, so a multi-line
traceback becomes one entry per frame. Emitting one JSON record per line
keeps each traceback to a single entry (json escapes the newlines).
"""
from __future__ import annotations

import json
import logging
import sys
import time

_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")

# Promoted to top-level JSON keys when passed via logging's extra=.
_EXTRA_FIELDS = ("path", "method")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
        payload: dict[str, object] = {
            "ts": f"{ts}.{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in _EXTRA_FIELDS:
            if key in record.__dict__:
                payload[key] = record.__dict__[key]
        if record.exc_info:
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

    # Detach uvicorn's own handlers so records reach root's JSON one.
    for name in _UVICORN_LOGGERS:
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
