"""ChromaDB-backed vector store — wraps app/chroma.py."""
from __future__ import annotations


class ChromaBackend:
    def __init__(self, chroma_path: str) -> None:
        import chromadb

        self._client = chromadb.PersistentClient(path=chroma_path)
        self._collection = self._client.get_or_create_collection(
            name="photos",
            metadata={"hnsw:space": "cosine"},
        )

    def upsert(
        self,
        photo_id: str,
        vec: list[float],
        embed_model: str,
        year: int | None,
    ) -> None:
        self._collection.upsert(
            ids=[photo_id],
            embeddings=[vec],
            metadatas=[{"year": year or 0, "embed_model": embed_model}],
        )

    def query(
        self,
        qvec: list[float],
        n: int,
        year_filter: int | None = None,
    ) -> list[tuple[str, float]]:
        where = {"year": year_filter} if year_filter is not None else None
        results = self._collection.query(
            query_embeddings=[qvec],
            n_results=n,
            where=where,
        )
        ids: list[str] = results["ids"][0] if results["ids"] else []
        distances: list[float] = results["distances"][0] if results["distances"] else []
        return list(zip(ids, distances))

    def distinct_embed_models(self) -> set[str]:
        meta = self._collection.metadata or {}
        model = meta.get("embed_model")
        return {model} if model else set()

    def count(self) -> int:
        return self._collection.count()

    def assert_embed_model(self, model: str) -> None:
        """Record embed model on first use; raise if it changed."""
        stored = (self._collection.metadata or {}).get("embed_model")
        if stored is None:
            self._collection.modify(metadata={"embed_model": model})
        elif stored != model:
            raise RuntimeError(
                f"Corpus embed model mismatch: stored={stored!r}, requested={model!r}. "
                "Delete data/chroma/ to start fresh or use the same model."
            )
