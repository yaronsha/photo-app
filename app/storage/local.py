from __future__ import annotations

from pathlib import Path
from typing import BinaryIO, Iterator

from .base import KeyNotFound, Storage


class LocalStorage(Storage):
    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, key: str) -> Path:
        return self.root / key

    def read_bytes(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError as exc:
            raise KeyNotFound(key) from exc

    def open_stream(self, key: str) -> BinaryIO:
        try:
            return self._path(key).open("rb")  # type: ignore[return-value]
        except FileNotFoundError as exc:
            raise KeyNotFound(key) from exc

    def write_bytes(self, key: str, data: bytes, content_type: str | None = None) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def iter_prefix(self, prefix: str) -> Iterator[str]:
        base = self._path(prefix)
        if not base.exists():
            return
        for p in base.rglob("*"):
            if p.is_file():
                yield str(p.relative_to(self.root))

    def presign_get(self, key: str, expires: int = 3600) -> str:
        return f"/local/{key}"
