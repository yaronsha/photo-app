"""Tests for app/indexer/merge.py — Google Takeout merge step."""
import hashlib
import json
import sqlite3
from pathlib import Path

from .conftest import make_png


def _sha256_id(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()[:16]


def _make_takeout(takeout_dir: Path, photo_name: str, year: int, sidecar: dict | None = None,
                  sidecar_suffix: str = ".supplemental-metadata.json"):
    folder = takeout_dir / f"Photos from {year}"
    folder.mkdir(parents=True, exist_ok=True)
    photo_path = folder / photo_name
    make_png(photo_path)
    if sidecar is not None:
        sidecar_path = folder / (photo_name + sidecar_suffix)
        sidecar_path.write_text(json.dumps(sidecar))
    return photo_path


def test_merge_copies_to_year_folder(tmp_env, tmp_path):
    takeout = tmp_path / "Takeout"
    _make_takeout(takeout, "img.png", 2018,
                  sidecar={"photoTakenTime": {"timestamp": "1530000000"}})

    from app.indexer.merge import run_merge
    result = run_merge([takeout])

    assert result["merged"] == 1
    photos_dir = tmp_env["photos_dir"]
    # Year from sidecar timestamp 1530000000 = 2018-06-26
    assert (photos_dir / "2018" / "img.png").exists()


def test_merge_year_from_folder_name_when_no_sidecar(tmp_env, tmp_path):
    takeout = tmp_path / "Takeout"
    _make_takeout(takeout, "img.png", 2010, sidecar=None)

    from app.indexer.merge import run_merge
    result = run_merge([takeout])

    assert result["merged"] == 1
    assert result["no_sidecar"] == 1
    assert (tmp_env["photos_dir"] / "2010" / "img.png").exists()


def test_merge_unknown_year_when_no_clue(tmp_env, tmp_path):
    takeout = tmp_path / "Takeout"
    weird = takeout / "Random Folder"
    weird.mkdir(parents=True)
    photo = weird / "img.png"
    make_png(photo)

    from app.indexer.merge import run_merge
    run_merge([takeout])

    assert (tmp_env["photos_dir"] / "unknown" / "img.png").exists()


def test_merge_dedup_within_run(tmp_env, tmp_path):
    """Two folders containing the same photo bytes — only one is copied."""
    takeout1 = tmp_path / "Takeout1"
    takeout2 = tmp_path / "Takeout2"
    p1 = _make_takeout(takeout1, "img.png", 2020,
                       sidecar={"photoTakenTime": {"timestamp": "1577880000"}})
    # Identical bytes in second takeout
    folder2 = takeout2 / "Photos from 2020"
    folder2.mkdir(parents=True)
    (folder2 / "img.png").write_bytes(p1.read_bytes())

    from app.indexer.merge import run_merge
    result = run_merge([takeout1, takeout2])

    assert result["merged"] == 1
    assert result["skipped_dupe"] == 1


def test_merge_dedup_against_existing_db(tmp_env, tmp_path):
    """Photo already in DB should be skipped."""
    takeout = tmp_path / "Takeout"
    photo = _make_takeout(takeout, "img.png", 2020,
                          sidecar={"photoTakenTime": {"timestamp": "1577880000"}})
    photo_id = _sha256_id(photo)

    # Pre-seed DB with that photo_id (simulating a prior scan)
    db_path = tmp_env["data_dir"] / "photos.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE photos (id TEXT PRIMARY KEY, storage_path TEXT NOT NULL UNIQUE, "
        "original_filename TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO photos (id, storage_path, original_filename) VALUES (?, ?, ?)",
        (photo_id, "/old/path/img.png", "img.png"),
    )
    conn.commit()
    conn.close()

    from app.indexer.merge import run_merge
    result = run_merge([takeout])

    assert result["merged"] == 0
    assert result["skipped_dupe"] == 1


def test_merge_dry_run_copies_nothing(tmp_env, tmp_path):
    takeout = tmp_path / "Takeout"
    _make_takeout(takeout, "img.png", 2020,
                  sidecar={"photoTakenTime": {"timestamp": "1577880000"}})

    from app.indexer.merge import run_merge
    result = run_merge([takeout], dry_run=True)

    assert result["merged"] == 1  # counted, but...
    assert not (tmp_env["photos_dir"] / "2020" / "img.png").exists()  # ...not copied
    assert not (tmp_env["data_dir"] / "sidecars").exists()


def test_merge_writes_sidecar_under_photo_id(tmp_env, tmp_path):
    takeout = tmp_path / "Takeout"
    sidecar = {"photoTakenTime": {"timestamp": "1577880000"}, "description": "test note"}
    photo = _make_takeout(takeout, "img.png", 2020, sidecar=sidecar)
    photo_id = _sha256_id(photo)

    from app.indexer.merge import run_merge
    run_merge([takeout])

    sidecar_path = tmp_env["data_dir"] / "sidecars" / f"{photo_id}.json"
    assert sidecar_path.exists()
    saved = json.loads(sidecar_path.read_text())
    assert saved["description"] == "test note"


def test_merge_skips_unsupported_extensions(tmp_env, tmp_path):
    takeout = tmp_path / "Takeout"
    folder = takeout / "Photos from 2020"
    folder.mkdir(parents=True)
    make_png(folder / "img.png")
    (folder / "movie.mp4").write_bytes(b"fake video")
    (folder / "anim.gif").write_bytes(b"fake gif")

    from app.indexer.merge import run_merge
    result = run_merge([takeout])

    assert result["merged"] == 1


def test_merge_handles_filename_collision_in_year_folder(tmp_env, tmp_path):
    """Two different photos with same filename — second renamed with photo_id prefix."""
    takeout = tmp_path / "Takeout"
    folder1 = takeout / "Photos from 2020"
    folder2 = takeout / "Photos from 2020 (other)"
    folder1.mkdir(parents=True)
    folder2.mkdir(parents=True)
    sidecar = {"photoTakenTime": {"timestamp": "1577880000"}}
    p1 = folder1 / "img.png"
    p2 = folder2 / "img.png"
    make_png(p1)
    make_png(p2)
    (folder1 / "img.png.supplemental-metadata.json").write_text(json.dumps(sidecar))
    (folder2 / "img.png.supplemental-metadata.json").write_text(json.dumps(sidecar))

    from app.indexer.merge import run_merge
    result = run_merge([takeout])

    assert result["merged"] == 2
    year_dir = tmp_env["photos_dir"] / "2020"
    files = sorted(p.name for p in year_dir.iterdir())
    assert "img.png" in files
    # Second file should be renamed with photo_id prefix
    assert any(f.endswith("_img.png") and f != "img.png" for f in files)
