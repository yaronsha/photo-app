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


def test_google_metadata_does_not_overwrite_existing_taken_at(tmp_env):
    """If EXIF gave us a taken_at, sidecar should not overwrite."""
    photo_id = _scan_photo(tmp_env)
    # Manually set taken_at as if from EXIF
    with get_session() as s:
        s.execute(
            update(Photo)
            .where(Photo.id == photo_id)
            .values(taken_at="2015-05-15T10:00:00+00:00")
        )

    _write_sidecar(tmp_env, photo_id, {"photoTakenTime": {"timestamp": "1577880000"}})

    from app.indexer.google_metadata import run_google_metadata
    run_google_metadata()

    with get_session() as s:
        row = s.query(Photo).first()
    assert "2015" in row.taken_at
