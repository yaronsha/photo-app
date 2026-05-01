"""Tests for app/indexer/google_metadata.py — sidecar enrichment + people aliases."""
import json
import sqlite3
from pathlib import Path

from .conftest import make_png, write_config


def _scan_photo(tmp_env, name: str = "img.png") -> str:
    """Drop a PNG in photos_dir, run scan, return its photo_id."""
    photo_path = tmp_env["photos_dir"] / name
    make_png(photo_path)
    import app.indexer.scan as scan_mod
    scan_mod.run_scan()

    conn = sqlite3.connect(str(tmp_env["data_dir"] / "photos.db"))
    photo_id = conn.execute(
        "SELECT id FROM photos WHERE original_filename = ?", (name,)
    ).fetchone()[0]
    conn.close()
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

    conn = sqlite3.connect(str(tmp_env["data_dir"] / "photos.db"))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT taken_at, google_metadata_indexed_at FROM photos").fetchone()
    conn.close()

    assert row["taken_at"] is not None
    assert "2020" in row["taken_at"]
    assert row["google_metadata_indexed_at"] is not None


def test_google_metadata_fills_lat_lng(tmp_env):
    photo_id = _scan_photo(tmp_env)
    _write_sidecar(tmp_env, photo_id, {
        "geoData": {"latitude": 32.0853, "longitude": 34.7818},
    })

    from app.indexer.google_metadata import run_google_metadata
    run_google_metadata()

    conn = sqlite3.connect(str(tmp_env["data_dir"] / "photos.db"))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT lat, lng FROM photos").fetchone()
    conn.close()

    assert row["lat"] == 32.0853
    assert row["lng"] == 34.7818


def test_google_metadata_stores_description(tmp_env):
    photo_id = _scan_photo(tmp_env)
    _write_sidecar(tmp_env, photo_id, {"description": "birthday party"})

    from app.indexer.google_metadata import run_google_metadata
    run_google_metadata()

    conn = sqlite3.connect(str(tmp_env["data_dir"] / "photos.db"))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT description FROM photos").fetchone()
    conn.close()

    assert row["description"] == "birthday party"


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

    conn = sqlite3.connect(str(tmp_env["data_dir"] / "photos.db"))
    rows = conn.execute(
        "SELECT person_id FROM photo_people WHERE photo_id = ? ORDER BY person_id", (photo_id,)
    ).fetchall()
    conn.close()

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

    conn = sqlite3.connect(str(tmp_env["data_dir"] / "photos.db"))
    rows = conn.execute("SELECT * FROM photo_people").fetchall()
    conn.close()

    assert rows == []


def test_google_metadata_no_sidecar_still_stamps(tmp_env):
    """Photos without matching sidecar file should still get google_metadata_indexed_at."""
    _scan_photo(tmp_env)
    # Create empty sidecars dir so the step runs (it early-returns if dir is missing)
    (tmp_env["data_dir"] / "sidecars").mkdir(parents=True, exist_ok=True)

    from app.indexer.google_metadata import run_google_metadata
    run_google_metadata()

    conn = sqlite3.connect(str(tmp_env["data_dir"] / "photos.db"))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT google_metadata_indexed_at, description FROM photos").fetchone()
    conn.close()

    assert row["google_metadata_indexed_at"] is not None
    assert row["description"] is None


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

    conn = sqlite3.connect(str(tmp_env["data_dir"] / "photos.db"))
    rows = conn.execute("SELECT id, name FROM people ORDER BY id").fetchall()
    conn.close()

    assert rows == [("noa", "Noa Shapira"), ("yaron", "Yaron Shapira")]


def test_google_metadata_does_not_overwrite_existing_taken_at(tmp_env):
    """If EXIF gave us a taken_at, sidecar should not overwrite."""
    photo_id = _scan_photo(tmp_env)
    # Manually set taken_at as if from EXIF
    db_path = tmp_env["data_dir"] / "photos.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE photos SET taken_at = ? WHERE id = ?",
        ("2015-05-15T10:00:00+00:00", photo_id),
    )
    conn.commit()
    conn.close()

    _write_sidecar(tmp_env, photo_id, {"photoTakenTime": {"timestamp": "1577880000"}})

    from app.indexer.google_metadata import run_google_metadata
    run_google_metadata()

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT taken_at FROM photos").fetchone()
    conn.close()

    assert "2015" in row["taken_at"]
