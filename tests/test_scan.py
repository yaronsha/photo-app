from app.db import Photo, get_session

from .conftest import make_png as _make_png


def test_scan_indexes_png(tmp_env):
    photos_dir = tmp_env["photos_dir"]
    _make_png(photos_dir / "test.png")

    import app.indexer.scan as scan_mod
    scan_mod.run_scan()

    with get_session() as s:
        rows = s.query(Photo).all()
    assert len(rows) == 1
    assert rows[0].original_filename == "test.png"
    assert rows[0].scan_indexed_at is not None


def test_scan_idempotent(tmp_env):
    photos_dir = tmp_env["photos_dir"]
    _make_png(photos_dir / "a.png")
    _make_png(photos_dir / "b.png")

    import app.indexer.scan as scan_mod

    scan_mod.run_scan()
    scan_mod.run_scan()

    with get_session() as s:
        rows = s.query(Photo).all()
    assert len(rows) == 2


def test_scan_dedup_by_content(tmp_env):
    photos_dir = tmp_env["photos_dir"]
    img_bytes_path = photos_dir / "orig.png"
    _make_png(img_bytes_path)
    copy_path = photos_dir / "copy.png"
    copy_path.write_bytes(img_bytes_path.read_bytes())

    import app.indexer.scan as scan_mod

    scan_mod.run_scan()

    with get_session() as s:
        rows = s.query(Photo).all()
    assert len(rows) == 1
