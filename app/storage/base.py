from abc import ABC, abstractmethod
from typing import BinaryIO, Iterator


class KeyNotFound(Exception):
    """Raised when a key has no object in the storage backend.

    Backends translate their native missing-object error (FileNotFoundError
    for LocalStorage, botocore.ClientError with a NoSuchKey/404 code for
    R2Storage) to this single type so callers can distinguish "object is
    gone" from "infrastructure failure" portably.
    """


class Storage(ABC):
    @abstractmethod
    def read_bytes(self, key: str) -> bytes: ...

    @abstractmethod
    def open_stream(self, key: str) -> BinaryIO: ...

    @abstractmethod
    def write_bytes(self, key: str, data: bytes, content_type: str | None = None) -> None: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def iter_prefix(self, prefix: str) -> Iterator[str]: ...

    @abstractmethod
    def presign_get(self, key: str, expires: int = 3600) -> str: ...
