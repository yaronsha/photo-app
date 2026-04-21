from ..chroma import get_collection
from ..db import get_conn, row_to_dict
from ..indexer.providers import get_embed_provider
from ..models import SearchResult


def search(
    query: str,
    limit: int = 50,
    year_from: int | None = None,
    year_to: int | None = None,
) -> list[SearchResult]:
    provider = get_embed_provider()
    qvec = provider.embed(query)

    where: dict = {}
    if year_from is not None and year_to is not None:
        where = {"$and": [{"year": {"$gte": year_from}}, {"year": {"$lte": year_to}}]}
    elif year_from is not None:
        where = {"year": {"$gte": year_from}}
    elif year_to is not None:
        where = {"year": {"$lte": year_to}}

    collection = get_collection()
    query_kwargs: dict = {
        "query_embeddings": [qvec],
        "n_results": min(limit, collection.count() or 1),
    }
    if where:
        query_kwargs["where"] = where

    chroma_results = collection.query(**query_kwargs)

    ids: list[str] = chroma_results["ids"][0] if chroma_results["ids"] else []
    distances: list[float] = (
        chroma_results["distances"][0] if chroma_results["distances"] else []
    )

    if not ids:
        return []

    placeholders = ",".join("?" * len(ids))
    conn = get_conn()
    rows = conn.execute(
        f"SELECT * FROM photos WHERE id IN ({placeholders})", ids
    ).fetchall()
    conn.close()

    by_id = {r["id"]: row_to_dict(r) for r in rows}

    results = []
    for photo_id, dist in zip(ids, distances):
        if photo_id not in by_id:
            continue
        row = by_id[photo_id]
        results.append(
            SearchResult(
                id=photo_id,
                caption=row.get("caption"),
                taken_at=row.get("taken_at"),
                storage_path=row["storage_path"],
                score=1.0 - dist,
            )
        )
    return results
