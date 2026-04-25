from datetime import date, timedelta
from typing import Literal

from ..chroma import get_collection
from ..db import get_conn, row_to_dict
from ..indexer.providers import get_embed_provider
from ..models import SearchResult


def _parse_iso_date(s: str | None) -> date | None:
    if not s:
        return None
    return date.fromisoformat(s)


def _date_bounds(date_from: str | None, date_to: str | None) -> tuple[str | None, str | None]:
    """Return (lo_inclusive, hi_exclusive) ISO strings for taken_at compare."""
    lo = _parse_iso_date(date_from)
    hi = _parse_iso_date(date_to)
    lo_s = lo.isoformat() if lo else None
    hi_s = (hi + timedelta(days=1)).isoformat() if hi else None
    return lo_s, hi_s


def search(
    query: str | None = None,
    limit: int = 50,
    date_from: str | None = None,
    date_to: str | None = None,
    person_ids: list[str] | None = None,
    people_mode: Literal["any", "all"] = "any",
) -> list[SearchResult]:
    lo, hi = _date_bounds(date_from, date_to)
    has_date = lo is not None or hi is not None
    has_query = bool(query and query.strip())
    has_person = bool(person_ids)

    if not has_query and not has_date and not has_person:
        return []

    conn = get_conn()

    if not has_query:
        results = _browse(conn, lo, hi, person_ids, limit, people_mode)
    else:
        results = _vector_search(conn, query, lo, hi, person_ids, limit, people_mode)

    conn.close()
    return results


def _attach_people(conn, photo_ids: list[str]) -> dict[str, list[dict]]:
    people_by_photo: dict[str, list[dict]] = {pid: [] for pid in photo_ids}
    if not photo_ids:
        return people_by_photo
    pp_placeholders = ",".join("?" * len(photo_ids))
    pp_rows = conn.execute(
        f"""
        SELECT pp.photo_id, p.id, p.name
        FROM photo_people pp
        JOIN people p ON p.id = pp.person_id
        WHERE pp.photo_id IN ({pp_placeholders})
        """,
        photo_ids,
    ).fetchall()
    for pp in pp_rows:
        people_by_photo[pp["photo_id"]].append({"id": pp["id"], "name": pp["name"]})
    return people_by_photo


def _browse(
    conn,
    lo: str | None,
    hi: str | None,
    person_ids: list[str] | None,
    limit: int,
    people_mode: Literal["any", "all"] = "any",
) -> list[SearchResult]:
    where: list[str] = ["taken_at IS NOT NULL"]
    params: list = []

    if lo is not None:
        where.append("taken_at >= ?")
        params.append(lo)
    if hi is not None:
        where.append("taken_at < ?")
        params.append(hi)
    if person_ids:
        person_placeholders = ",".join("?" * len(person_ids))
        if people_mode == "all":
            where.append(
                f"id IN (SELECT photo_id FROM photo_people "
                f"WHERE person_id IN ({person_placeholders}) "
                f"GROUP BY photo_id HAVING COUNT(DISTINCT person_id) = {len(person_ids)})"
            )
        else:
            where.append(
                f"id IN (SELECT photo_id FROM photo_people WHERE person_id IN ({person_placeholders}))"
            )
        params.extend(person_ids)

    sql = (
        f"SELECT * FROM photos WHERE {' AND '.join(where)} "
        f"ORDER BY taken_at DESC LIMIT ?"
    )
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    by_id = {r["id"]: row_to_dict(r) for r in rows}
    ids = list(by_id.keys())
    people_by_photo = _attach_people(conn, ids)

    results = []
    for pid in ids:
        row = by_id[pid]
        results.append(
            SearchResult(
                id=pid,
                caption=row.get("caption"),
                taken_at=row.get("taken_at"),
                storage_path=row["storage_path"],
                score=0.0,
                location_name=row.get("location_name"),
                tags=row.get("tags") or [],
                people=people_by_photo.get(pid, []),
            )
        )
    return results


def _vector_search(
    conn,
    query: str,
    lo: str | None,
    hi: str | None,
    person_ids: list[str] | None,
    limit: int,
    people_mode: Literal["any", "all"] = "any",
) -> list[SearchResult]:
    provider = get_embed_provider()
    qvec = provider.embed(query)

    collection = get_collection()
    has_filter = lo is not None or hi is not None or bool(person_ids)
    # "all" mode is far more selective than "any"; overfetch may still under-return
    # for very strict multi-person intersections in large collections.
    overfetch = min(limit * 4, 200) if has_filter else limit
    n = min(overfetch, collection.count() or 1)

    chroma_results = collection.query(query_embeddings=[qvec], n_results=n)

    ids: list[str] = chroma_results["ids"][0] if chroma_results["ids"] else []
    distances: list[float] = (
        chroma_results["distances"][0] if chroma_results["distances"] else []
    )
    if not ids:
        return []

    id_placeholders = ",".join("?" * len(ids))
    where: list[str] = [f"id IN ({id_placeholders})"]
    params: list = list(ids)

    if lo is not None:
        where.append("taken_at >= ?")
        params.append(lo)
    if hi is not None:
        where.append("taken_at < ?")
        params.append(hi)
    if person_ids:
        person_placeholders = ",".join("?" * len(person_ids))
        if people_mode == "all":
            where.append(
                f"id IN (SELECT photo_id FROM photo_people "
                f"WHERE person_id IN ({person_placeholders}) "
                f"GROUP BY photo_id HAVING COUNT(DISTINCT person_id) = {len(person_ids)})"
            )
        else:
            where.append(
                f"id IN (SELECT photo_id FROM photo_people WHERE person_id IN ({person_placeholders}))"
            )
        params.extend(person_ids)

    sql = f"SELECT * FROM photos WHERE {' AND '.join(where)}"
    rows = conn.execute(sql, params).fetchall()
    by_id = {r["id"]: row_to_dict(r) for r in rows}

    returned_ids = list(by_id.keys())
    people_by_photo = _attach_people(conn, returned_ids)

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
                location_name=row.get("location_name"),
                tags=row.get("tags") or [],
                people=people_by_photo.get(photo_id, []),
            )
        )
        if len(results) >= limit:
            break
    return results
