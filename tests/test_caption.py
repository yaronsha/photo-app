import json
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import update

from app.db import Photo, get_session

from .conftest import make_png as _make_png


_FULL_RESPONSE = {
    "caption": "A sunny beach scene",
    "tags": ["beach", "sunny", "ocean"],
    "activities": ["swimming", "playing"],
    "content_type": "photo",
    "subject_type": "candid_people",
    "primary_focus": "people",
    "indoor_outdoor": "outdoor",
    "setting_type": "beach",
    "sharpness": "sharp",
    "face_clarity_score": 4,
}


def _minimal_response(**overrides):
    out = dict(_FULL_RESPONSE)
    out.update(overrides)
    return out


def test_caption_mocked_provider(tmp_env):
    photos_dir = tmp_env["photos_dir"]
    img = photos_dir / "photo.png"
    _make_png(img)

    import app.indexer.scan as scan_mod
    scan_mod.run_scan()

    mock_provider = MagicMock()
    mock_provider.caption = AsyncMock(return_value=_FULL_RESPONSE)

    import app.indexer.caption as caption_mod

    with patch.object(caption_mod, "get_caption_provider", return_value=mock_provider):
        count = caption_mod.run_caption(limit=50)

    assert count == 1
    mock_provider.caption.assert_called_once()

    with get_session() as s:
        row = s.query(Photo).first()
    assert row.caption == "A sunny beach scene"
    assert row.tags == ["beach", "sunny", "ocean"]
    assert row.activities == ["swimming", "playing"]
    assert row.content_type == "photo"
    assert row.subject_type == "candid_people"
    assert row.primary_focus == "people"
    assert row.indoor_outdoor == "outdoor"
    assert row.setting_type == "beach"
    assert row.sharpness == "sharp"
    assert row.face_clarity_score == 4
    assert row.caption_schema_version == caption_mod.CAPTION_SCHEMA_VERSION


def test_caption_face_clarity_null_when_no_faces(tmp_env):
    photos_dir = tmp_env["photos_dir"]
    _make_png(photos_dir / "photo.png")

    import app.indexer.scan as scan_mod
    scan_mod.run_scan()

    mock_provider = MagicMock()
    mock_provider.caption = AsyncMock(
        return_value=_minimal_response(
            subject_type="landscape",
            primary_focus="place",
            face_clarity_score=None,
        )
    )

    import app.indexer.caption as caption_mod

    with patch.object(caption_mod, "get_caption_provider", return_value=mock_provider):
        caption_mod.run_caption(limit=1)

    with get_session() as s:
        row = s.query(Photo).first()
    assert row.face_clarity_score is None


def test_caption_skips_already_captioned(tmp_env):
    photos_dir = tmp_env["photos_dir"]
    _make_png(photos_dir / "photo.png")

    import app.indexer.scan as scan_mod
    scan_mod.run_scan()

    mock_provider = MagicMock()
    mock_provider.caption = AsyncMock(return_value=_FULL_RESPONSE)

    import app.indexer.caption as caption_mod

    with patch.object(caption_mod, "get_caption_provider", return_value=mock_provider):
        caption_mod.run_caption(limit=50)

    mock_provider.caption.reset_mock()

    with patch.object(caption_mod, "get_caption_provider", return_value=mock_provider):
        caption_mod.run_caption(limit=50)

    mock_provider.caption.assert_not_called()


def test_caption_picks_up_stale_schema_version(tmp_env):
    photos_dir = tmp_env["photos_dir"]
    _make_png(photos_dir / "photo.png")

    import app.indexer.scan as scan_mod
    scan_mod.run_scan()

    with get_session() as s:
        s.execute(
            update(Photo).values(
                caption="old",
                caption_indexed_at="2020-01-01T00:00:00",
                caption_schema_version=1,
            )
        )

    mock_provider = MagicMock()
    mock_provider.caption = AsyncMock(return_value=_FULL_RESPONSE)

    import app.indexer.caption as caption_mod

    with patch.object(caption_mod, "get_caption_provider", return_value=mock_provider):
        count = caption_mod.run_caption(limit=10)

    assert count == 1
    mock_provider.caption.assert_called_once()


def test_caption_limit_respected(tmp_env):
    photos_dir = tmp_env["photos_dir"]
    for i in range(5):
        _make_png(photos_dir / f"photo_{i}.png")

    import app.indexer.scan as scan_mod
    scan_mod.run_scan()

    mock_provider = MagicMock()
    mock_provider.caption = AsyncMock(return_value=_FULL_RESPONSE)

    import app.indexer.caption as caption_mod

    with patch.object(caption_mod, "get_caption_provider", return_value=mock_provider):
        count = caption_mod.run_caption(limit=3)

    assert count == 3
    assert mock_provider.caption.call_count == 3
