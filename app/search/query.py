from datetime import date, timedelta
from typing import Literal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import Person, Photo, PhotoPerson, get_session
from ..indexer.providers import get_embed_provider
from ..vectordb import get_vector_backend
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
    offset: int = 0,
    date_from: str | None = None,
    date_to: str | None = None,
    person_ids: list[str] | None = None,
    people_mode: Literal["any", "all"] = "any",
    include_docs: bool = False,
) -> tuple[list[SearchResult], bool]:
    lo, hi = _date_bounds(date_from, date_to)
    has_date = lo is not None or hi is not None
    has_query = bool(query and query.strip())
    has_person = bool(person_ids)

    if not has_query and not has_date and not has_person:
        return [], False

    with get_session() as session:
        if not has_query:
            return _browse(
                session, lo, hi, person_ids, limit, offset, people_mode, include_docs
            )
        return _vector_search(
            session, query, lo, hi, person_ids, limit, offset, people_mode, include_docs
        )


def _attach_people(session: Session, photo_ids: list[str]) -> dict[str, list[dict]]:
    people_by_photo: dict[str, list[dict]] = {pid: [] for pid in photo_ids}
    if not photo_ids:
        return people_by_photo
    rows = session.execute(
        select(PhotoPerson.photo_id, Person.id, Person.name)
        .join(Person, Person.id == PhotoPerson.person_id)
        .where(PhotoPerson.photo_id.in_(photo_ids))
    ).all()
    for photo_id, pid, pname in rows:
        people_by_photo[photo_id].append({"id": pid, "name": pname})
    return people_by_photo


def _photo_to_result(photo: Photo, people: list[dict], score: float) -> SearchResult:
    return SearchResult(
        id=photo.id,
        caption=photo.caption,
        taken_at=photo.taken_at,
        storage_path=photo.storage_path,
        score=score,
        location_name=photo.location_name,
        tags=photo.tags or [],
        people=people,
        activities=photo.activities or [],
        content_type=photo.content_type,
        subject_type=photo.subject_type,
        setting_type=photo.setting_type,
        sharpness=photo.sharpness,
        face_clarity_score=photo.face_clarity_score,
        primary_focus=photo.primary_focus,
        indoor_outdoor=photo.indoor_outdoor,
    )


def _people_filter_clause(person_ids: list[str], people_mode: str):
    """Return a clause restricting Photo.id to rows matching the people filter."""
    if people_mode == "all":
        subq = (
            select(PhotoPerson.photo_id)
            .where(PhotoPerson.person_id.in_(person_ids))
            .group_by(PhotoPerson.photo_id)
            .having(func.count(func.distinct(PhotoPerson.person_id)) == len(person_ids))
        )
    else:
        subq = (
            select(PhotoPerson.photo_id)
            .where(PhotoPerson.person_id.in_(person_ids))
        )
    return Photo.id.in_(subq)


def _browse(
    session: Session,
    lo: str | None,
    hi: str | None,
    person_ids: list[str] | None,
    limit: int,
    offset: int = 0,
    people_mode: Literal["any", "all"] = "any",
    include_docs: bool = False,
) -> tuple[list[SearchResult], bool]:
    stmt = select(Photo).where(Photo.taken_at.is_not(None))

    if not include_docs:
        stmt = stmt.where(or_(Photo.content_type == "photo", Photo.content_type.is_(None)))
    if lo is not None:
        stmt = stmt.where(Photo.taken_at >= lo)
    if hi is not None:
        stmt = stmt.where(Photo.taken_at < hi)
    if person_ids:
        stmt = stmt.where(_people_filter_clause(person_ids, people_mode))

    # fetch limit+1 to detect has_more without a separate COUNT query
    stmt = stmt.order_by(Photo.taken_at.desc()).limit(limit + 1).offset(offset)

    photos = session.execute(stmt).scalars().all()
    has_more = len(photos) > limit
    photos = photos[:limit]

    ids = [p.id for p in photos]
    people_by_photo = _attach_people(session, ids)

    results = [_photo_to_result(p, people_by_photo.get(p.id, []), 0.0) for p in photos]
    return results, has_more


def _vector_search(
    session: Session,
    query: str,
    lo: str | None,
    hi: str | None,
    person_ids: list[str] | None,
    limit: int,
    offset: int = 0,
    people_mode: Literal["any", "all"] = "any",
    include_docs: bool = False,
) -> tuple[list[SearchResult], bool]:
    provider = get_embed_provider()
    qvec = provider.embed(query)

    backend = get_vector_backend()
    has_filter = (
        lo is not None or hi is not None or bool(person_ids) or not include_docs
    )
    # "all" mode is far more selective than "any"; overfetch may still under-return
    # for very strict multi-person intersections in large collections.
    overfetch = min((limit + offset) * 4, 200) if has_filter else min(limit + offset, 200)
    n = min(overfetch, backend.count() or 1)

    pairs = backend.query(qvec, n)

    ids: list[str] = [p[0] for p in pairs]
    distances: list[float] = [p[1] for p in pairs]
    if not ids:
        return [], False

    stmt = select(Photo).where(Photo.id.in_(ids))

    if not include_docs:
        stmt = stmt.where(or_(Photo.content_type == "photo", Photo.content_type.is_(None)))
    if lo is not None:
        stmt = stmt.where(Photo.taken_at >= lo)
    if hi is not None:
        stmt = stmt.where(Photo.taken_at < hi)
    if person_ids:
        stmt = stmt.where(_people_filter_clause(person_ids, people_mode))

    photos = session.execute(stmt).scalars().all()
    by_id = {p.id: p for p in photos}

    returned_ids = list(by_id.keys())
    people_by_photo = _attach_people(session, returned_ids)

    # collect all filtered results in chroma rank order
    all_results = [
        _photo_to_result(by_id[pid], people_by_photo.get(pid, []), 1.0 - dist)
        for pid, dist in zip(ids, distances)
        if pid in by_id
    ]

    has_more = len(all_results) > offset + limit
    return all_results[offset : offset + limit], has_more
