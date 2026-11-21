"""Tests for app/indexer/google_metadata.py — sidecar enrichment + people aliases."""
import json

from sqlalchemy import select, update

from app.db import Person, Photo, PhotoPerson, get_session

from .conftest import make_png, write_config


def _scan_photo(tmp_env, name: str = "img.png") -> str:
    """Drop a PNG in photos_dir, run scan, return its photo_id."""
    photo_path = tmp_env["photos_dir"] / name
    make_png(photo_path)
    import app.indexer.scan as scan_mod
    scan_mod.run_scan()

    with get_session() as s:
        photo_id = s.execute(
            select(Photo.id).where(Photo.original_filename == name)
        ).scalar_one()
    return photo_id


def _write_sidecar(tmp_env, photo_id: str, payload: dict) -> None:
    sidecars_dir = tmp_env["data_dir"] / "sidecars"
    sidecars_dir.mkdir(parents=True, exist_ok=True)
    (sidecars_dir / f"{photo_id}.json").write_text(json.dumps(payload, ensure_ascii=False))


def test_google_metadata_sets_taken_at_when_exif_missing(tmp_env):
    photo_id = _scan_photo(tmp_env)
    _write_sidecar(tmp_env, photo_id, {"photoTakenTime": {"timestamp": "1577880000"}})

    from app.indexer.google_metadata import run_google_metadata
    run_google_metadata()

    with get_session() as s:
        row = s.query(Photo).first()
    assert row.taken_at is not None
    assert "2020" in row.taken_at
    assert row.google_metadata_indexed_at is not None


def test_google_metadata_fills_lat_lng(tmp_env):
    photo_id = _scan_photo(tmp_env)
    _write_sidecar(tmp_env, photo_id, {
        "geoData": {"latitude": 32.0853, "longitude": 34.7818},
    })

    from app.indexer.google_metadata import run_google_metadata
    run_google_metadata()

    with get_session() as s:
        row = s.query(Photo).first()
    assert row.lat == 32.0853
    assert row.lng == 34.7818


def test_google_metadata_stores_description(tmp_env):
    photo_id = _scan_photo(tmp_env)
    _write_sidecar(tmp_env, photo_id, {"description": "birthday party"})

    from app.indexer.google_metadata import run_google_metadata
    run_google_metadata()

    with get_session() as s:
        row = s.query(Photo).first()
    assert row.description == "birthday party"


def test_google_metadata_populates_photo_people_via_aliases(tmp_env):
    write_config(
        tmp_env["cfg_path"],
        people=[
            {"id": "yaron", "name": "Yaron Shapira"},
            {"id": "noa", "name": "Noa Shapira"},
        ],
        google_name_aliases={
            "yaron shapira": "yaron",
            "נוי שפירא": "noa",
        },
    )
    photo_id = _scan_photo(tmp_env)
    _write_sidecar(tmp_env, photo_id, {
        "people": [{"name": "Yaron Shapira"}, {"name": "נוי שפירא"}],
    })

    from app.indexer.google_metadata import run_google_metadata
    run_google_metadata()

    with get_session() as s:
        rows = s.execute(
            select(PhotoPerson.person_id)
            .where(PhotoPerson.photo_id == photo_id)
            .order_by(PhotoPerson.person_id)
        ).all()
    assert {r[0] for r in rows} == {"yaron", "noa"}


def test_google_metadata_ignores_unknown_alias(tmp_env):
    write_config(tmp_env["cfg_path"],
                 people=[{"id": "yaron", "name": "Yaron Shapira"}],
                 google_name_aliases={"yaron shapira": "yaron"})
    photo_id = _scan_photo(tmp_env)
    _write_sidecar(tmp_env, photo_id, {
        "people": [{"name": "Random Stranger"}],
    })

    from app.indexer.google_metadata import run_google_metadata
    run_google_metadata()

    with get_session() as s:
        rows = s.query(PhotoPerson).all()
    assert rows == []


def test_google_metadata_no_sidecar_still_stamps(tmp_env):
    """Photos without matching sidecar file should still get google_metadata_indexed_at."""
    _scan_photo(tmp_env)
    # Create empty sidecars dir so the step runs (it early-returns if dir is missing)
    (tmp_env["data_dir"] / "sidecars").mkdir(parents=True, exist_ok=True)

    from app.indexer.google_metadata import run_google_metadata
    run_google_metadata()

    with get_session() as s:
        row = s.query(Photo).first()
    assert row.google_metadata_indexed_at is not None
    assert row.description is None


def test_google_metadata_idempotent(tmp_env):
    photo_id = _scan_photo(tmp_env)
    _write_sidecar(tmp_env, photo_id, {"description": "hi"})

    from app.indexer.google_metadata import run_google_metadata
    run_google_metadata()

    # Second run: no rows match `WHERE google_metadata_indexed_at IS NULL`
    count = run_google_metadata()
    assert count == 0


def test_google_metadata_seeds_people_table(tmp_env):
    """People from config should be inserted into people table."""
    write_config(tmp_env["cfg_path"],
                 people=[
                     {"id": "yaron", "name": "Yaron Shapira"},
                     {"id": "noa", "name": "Noa Shapira"},
                 ])
    _scan_photo(tmp_env)
    (tmp_env["data_dir"] / "sidecars").mkdir(parents=True, exist_ok=True)

    from app.indexer.google_metadata import run_google_metadata
    run_google_metadata()

    with get_session() as s:
        rows = s.execute(select(Person.id, Person.name).order_by(Person.id)).all()
    assert rows == [("noa", "Noa Shapira"), ("yaron", "Yaron Shapira")]


def _set_taken_at(photo_id: str, value: str) -> None:
    with get_session() as s:
        s.execute(update(Photo).where(Photo.id == photo_id).values(taken_at=value))


def _taken_at() -> str:
    with get_session() as s:
        return s.query(Photo).first().taken_at


def test_google_metadata_sidecar_overrides_exif_scan_date(tmp_env):
    """Scan: EXIF holds the scan time, sidecar holds the corrected older date."""
    photo_id = _scan_photo(tmp_env)
    _set_taken_at(photo_id, "2021-03-10T14:22:05+00:00")  # scan time from EXIF
    # 1985-06-15T12:00:00Z, the date corrected in Google Photos
    _write_sidecar(tmp_env, photo_id, {"photoTakenTime": {"timestamp": "487684800"}})

    from app.indexer.google_metadata import run_google_metadata
    run_google_metadata()

    assert _taken_at().startswith("1985-06-15T12:00:00")


def test_google_metadata_keeps_exif_when_only_timezone_differs(tmp_env):
    """Digital photo: EXIF local time vs sidecar UTC differ by hours only."""
    photo_id = _scan_photo(tmp_env)
    # Taken 2015-05-15 10:00 local in UTC-7 → 17:00 UTC in the sidecar
    _set_taken_at(photo_id, "2015-05-15T10:00:00+00:00")
    _write_sidecar(tmp_env, photo_id, {"photoTakenTime": {"timestamp": "1431709200"}})

    from app.indexer.google_metadata import run_google_metadata
    run_google_metadata()

    assert _taken_at() == "2015-05-15T10:00:00+00:00"


def test_google_metadata_keeps_exif_when_sidecar_has_no_date(tmp_env):
    photo_id = _scan_photo(tmp_env)
    _set_taken_at(photo_id, "2015-05-15T10:00:00+00:00")
    _write_sidecar(tmp_env, photo_id, {"description": "no date here"})

    from app.indexer.google_metadata import run_google_metadata
    run_google_metadata()

    assert _taken_at() == "2015-05-15T10:00:00+00:00"


def test_resolve_taken_at_edge_cases():
    from app.indexer.google_metadata import _resolve_taken_at

    # naive EXIF string is treated as UTC for comparison
    assert _resolve_taken_at("2015-05-15T10:00:00", "1431709200") == "2015-05-15T10:00:00"
    # unparseable sidecar timestamp keeps the current value
    assert _resolve_taken_at("2015-05-15T10:00:00+00:00", "abc") == "2015-05-15T10:00:00+00:00"
    # unparseable current value falls back to the sidecar
    assert _resolve_taken_at("garbage", "1431709200").startswith("2015-05-15T17:00:00")
    # exactly one day apart is still treated as the same date
    assert _resolve_taken_at("2015-05-14T17:00:00+00:00", "1431709200") == "2015-05-14T17:00:00+00:00"
