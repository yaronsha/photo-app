from abc import ABC, abstractmethod
from typing import BinaryIO, Iterator


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
