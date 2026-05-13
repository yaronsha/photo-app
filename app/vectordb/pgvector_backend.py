"""pgvector-backed vector store via SQLAlchemy + Supabase Postgres."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import sessionmaker

from ..db.orm import Embedding


class PgvectorBackend:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._sf = session_factory

    def upsert(
        self,
        photo_id: str,
        vec: list[float],
        embed_model: str,
        year: int | None,
    ) -> None:
        stmt = pg_insert(Embedding).values(
            photo_id=photo_id,
            embedding=vec,
            embed_model=embed_model,
            year=year,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["photo_id"],
            set_={
                "embedding": stmt.excluded.embedding,
                "embed_model": stmt.excluded.embed_model,
                "year": stmt.excluded.year,
            },
        )
        with self._sf() as session:
            session.execute(stmt)
            session.commit()

    def query(
        self,
        qvec: list[float],
        n: int,
        year_filter: int | None = None,
    ) -> list[tuple[str, float]]:
        stmt = (
            select(
                Embedding.photo_id,
                Embedding.embedding.cosine_distance(qvec).label("dist"),
            )
            .order_by("dist")
            .limit(n)
        )
        if year_filter is not None:
            stmt = stmt.where(Embedding.year == year_filter)
        with self._sf() as session:
            rows = session.execute(stmt).all()
        return [(r.photo_id, r.dist) for r in rows]

    def distinct_embed_models(self) -> set[str]:
        with self._sf() as session:
            rows = session.execute(
                select(Embedding.embed_model).distinct()
            ).scalars().all()
        return set(rows)

    def count(self) -> int:
        with self._sf() as session:
            result = session.execute(
                select(func.count()).select_from(Embedding)
            ).scalar()
        return result or 0
