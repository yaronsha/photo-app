"""Protocol interface for vector backends."""
from __future__ import annotations

from typing import Protocol


class VectorBackend(Protocol):
    def upsert(
        self,
        photo_id: str,
        vec: list[float],
        embed_model: str,
        year: int | None,
    ) -> None: ...

    def update_year(self, photo_id: str, year: int | None) -> bool:
        """Change the stored year of an existing vector without re-embedding.

        Returns False (and does nothing) if the photo has no vector yet.
        """
        ...

    def query(
        self,
        qvec: list[float],
        n: int,
        year_filter: int | None = None,
    ) -> list[tuple[str, float]]: ...

    def distinct_embed_models(self) -> set[str]: ...

    def count(self) -> int: ...
