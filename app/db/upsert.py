"""Tiny dialect dispatcher for the 3 ON CONFLICT sites.

Picks `sqlalchemy.dialects.sqlite.insert` vs
`sqlalchemy.dialects.postgresql.insert` based on the bound session's
dialect name. Both dialects expose `on_conflict_do_update` /
`on_conflict_do_nothing` with the same shape.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .orm import Person, Photo, PhotoPerson


def _insert(session: Session):
    name = session.bind.dialect.name  # type: ignore[union-attr]
    if name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
        return insert
    # sqlite (and any other) → use sqlite dialect insert
    from sqlalchemy.dialects.sqlite import insert
    return insert


def upsert_photo_scan(
    session: Session,
    *,
    id: str,
    storage_path: str,
    original_filename: str,
    taken_at: str | None,
    lat: float | None,
    lng: float | None,
    scan_indexed_at: str,
) -> None:
    """Mirrors the previous scan.py ON CONFLICT(id) DO UPDATE.

    `storage_path` is a backend-agnostic key (e.g. "photos/2018/img.jpg"),
    not an absolute filesystem path.
    """
    insert = _insert(session)
    stmt = insert(Photo).values(
        id=id,
        storage_path=storage_path,
        original_filename=original_filename,
        taken_at=taken_at,
        lat=lat,
        lng=lng,
        scan_indexed_at=scan_indexed_at,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[Photo.id],
        set_={
            "storage_path": stmt.excluded.storage_path,
            "taken_at": stmt.excluded.taken_at,
            "lat": stmt.excluded.lat,
            "lng": stmt.excluded.lng,
            "scan_indexed_at": stmt.excluded.scan_indexed_at,
        },
    )
    session.execute(stmt)


def upsert_person(
    session: Session, *, id: str, name: str, family_id: str | None
) -> None:
    """Mirrors the previous google_metadata.py people seeding upsert."""
    insert = _insert(session)
    stmt = insert(Person).values(id=id, name=name, family_id=family_id)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Person.id],
        set_={"name": stmt.excluded.name},
    )
    session.execute(stmt)


def upsert_photo_person(
    session: Session,
    *,
    photo_id: str,
    person_id: str,
    face_bbox=None,
    confidence: float | None = None,
) -> None:
    """ON CONFLICT(photo_id, person_id) DO NOTHING."""
    insert = _insert(session)
    stmt = insert(PhotoPerson).values(
        photo_id=photo_id,
        person_id=person_id,
        face_bbox=face_bbox,
        confidence=confidence,
    )
    stmt = stmt.on_conflict_do_nothing(
        index_elements=[PhotoPerson.photo_id, PhotoPerson.person_id]
    )
    session.execute(stmt)
