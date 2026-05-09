"""Tests for app/indexer/location.py — offline reverse geocoding."""
from unittest.mock import patch

from sqlalchemy import select, update

from app.db import Photo, get_session

from .conftest import make_png


def _scan_with_gps(tmp_env, name: str, lat: float | None, lng: float | None) -> str:
    """Scan a PNG, then manually set GPS as if it came from EXIF."""
    photo_path = tmp_env["photos_dir"] / name
    make_png(photo_path)

    import app.indexer.scan as scan_mod
    scan_mod.run_scan()

    with get_session() as s:
        pid = s.execute(
            select(Photo.id).where(Photo.original_filename == name)
        ).scalar_one()
        if lat is not None and lng is not None:
            s.execute(
                update(Photo).where(Photo.id == pid).values(lat=lat, lng=lng)
            )
    return pid


def test_location_populates_name(tmp_env):
    _scan_with_gps(tmp_env, "img.png", 32.0853, 34.7818)

    fake_results = [{"name": "Tel Aviv-Yafo", "cc": "IL"}]
    with patch("app.indexer.location.reverse_geocoder.search", return_value=fake_results):
        from app.indexer.location import run_location
        count = run_location()

    assert count == 1
    with get_session() as s:
        row = s.query(Photo).first()
    assert row.location_name == "Tel Aviv-Yafo, IL"


def test_location_skips_photos_without_gps(tmp_env):
    _scan_with_gps(tmp_env, "no_gps.png", None, None)

    with patch("app.indexer.location.reverse_geocoder.search") as mock_search:
        from app.indexer.location import run_location
        count = run_location()

    assert count == 0
    mock_search.assert_not_called()


def test_location_skips_already_geocoded(tmp_env):
    pid = _scan_with_gps(tmp_env, "img.png", 32.0853, 34.7818)
    with get_session() as s:
        s.execute(
            update(Photo).where(Photo.id == pid).values(location_name="Pre-set")
        )

    with patch("app.indexer.location.reverse_geocoder.search") as mock_search:
        from app.indexer.location import run_location
        count = run_location()

    assert count == 0
    mock_search.assert_not_called()


def test_location_reindex_overwrites(tmp_env):
    pid = _scan_with_gps(tmp_env, "img.png", 32.0853, 34.7818)
    with get_session() as s:
        s.execute(
            update(Photo).where(Photo.id == pid).values(location_name="Stale")
        )

    fake_results = [{"name": "Updated City", "cc": "US"}]
    with patch("app.indexer.location.reverse_geocoder.search", return_value=fake_results):
        from app.indexer.location import run_location
        run_location(reindex=True)

    with get_session() as s:
        row = s.query(Photo).first()
    assert row.location_name == "Updated City, US"


def test_location_handles_missing_country_code(tmp_env):
    _scan_with_gps(tmp_env, "img.png", 0.0, 0.0)

    fake_results = [{"name": "Some Place", "cc": ""}]
    with patch("app.indexer.location.reverse_geocoder.search", return_value=fake_results):
        from app.indexer.location import run_location
        run_location()

    with get_session() as s:
        row = s.query(Photo).first()
    assert row.location_name == "Some Place"


def test_location_batches_all_coords_in_one_call(tmp_env):
    """The whole point of reverse_geocoder is batch — verify single call for N photos."""
    _scan_with_gps(tmp_env, "a.png", 32.0, 34.0)
    _scan_with_gps(tmp_env, "b.png", 51.5, -0.1)
    _scan_with_gps(tmp_env, "c.png", 40.7, -74.0)

    fake_results = [
        {"name": "TLV", "cc": "IL"},
        {"name": "London", "cc": "GB"},
        {"name": "NYC", "cc": "US"},
    ]
    with patch("app.indexer.location.reverse_geocoder.search", return_value=fake_results) as mock_search:
        from app.indexer.location import run_location
        run_location()

    assert mock_search.call_count == 1
