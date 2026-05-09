"""Custom SQLAlchemy types used by the ORM models."""
from __future__ import annotations

import json

import sqlalchemy as sa
from sqlalchemy.types import TypeDecorator


class JSONString(TypeDecorator):
    """Encode JSON values as TEXT.

    Round-trips the existing TEXT-as-JSON encoding used by the previous
    sqlite3 layer:
      - None  → SQL NULL  (NOT the string "null")
      - empty/""  → None  (defensive — old data may have empty strings)
      - any other value → json.dumps(value, ensure_ascii=False)
    """

    impl = sa.Text
    cache_ok = True

    def process_bind_param(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        return json.dumps(value, ensure_ascii=False)

    def process_result_value(self, value, dialect):  # type: ignore[override]
        if value is None or value == "":
            return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return None
