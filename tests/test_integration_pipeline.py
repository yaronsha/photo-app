"""Integration tests — multi-step indexing pipeline.

Each test chains 2+ pipeline steps and verifies cross-step data contracts.
External providers (caption API, embed API, geocoder) are mocked.
SQLite and filesystem are real (tmp_path isolation via pipeline_env fixture).
"""
import json
from unittest.mock import AsyncMock, patch

from sqlalchemy import select, update

from app.db import Photo, get_session

from .conftest import FAKE_EMBED_VEC, FULL_CAPTION_RESPONSE, make_png


def _photo_row():
    """Read the (single) photos row in the current test DB."""
    with get_session() as s:
        return s.query(Photo).first()


def test_full_pipeline_scan_to_embed(pipeline_env):
    """scan → google_metadata → location → caption → embed all populate expected DB columns."""
    env = pipeline_env
    make_png(env["photos_dir"] / "family.png")
    (env["data_dir"] / "sidecars").mkdir(parents=True, exist_ok=True)

    import app.indexer.scan as scan_mod
    import app.indexer.google_metadata as gm_mod
    import app.indexer.location as loc_mod
    import app.indexer.caption as caption_mod
    import app.indexer.embed as embed_mod
    import app.chroma as chroma_mod

    scan_mod.run_scan()
    gm_mod.run_google_metadata()

    with patch("app.indexer.location.reverse_geocoder.search", return_value=[]):
        loc_mod.run_location()

    with patch.object(caption_mod, "get_caption_provider", return_value=env["mock_caption_provider"]):
        caption_mod.run_caption(limit=10)

    with (
        patch.object(embed_mod, "get_embed_provider", return_value=env["mock_embed_provider"]),
        patch.object(embed_mod, "get_collection", return_value=env["mock_collection"]),
        patch.object(embed_mod, "assert_embed_model"),
        patch.object(chroma_mod, "get_collection", return_value=env["mock_collection"]),
    ):
        embed_mod.run_embed()

    row = _photo_row()
    assert row.scan_indexed_at is not None
    assert row.google_metadata_indexed_at is not None
    assert row.caption_indexed_at is not None
    assert row.vector_indexed_at is not None
    assert row.caption == "A sunny outdoor scene"
    assert row.tags == ["sunny", "outdoor", "nature"]
    assert row.content_type == "photo"
    assert row.caption_schema_version == caption_mod.CAPTION_SCHEMA_VERSION
    assert row.embed_schema_version == caption_mod.CAPTION_SCHEMA_VERSION
    assert env["mock_caption_provider"].caption.call_count == 1
    assert env["mock_embed_provider"].embed.call_count == 1
    assert env["mock_collection"].upsert.call_count == 1


def test_pipeline_idempotent_no_api_calls_on_second_run(pipeline_env):
    """Running all steps twice makes 0 API calls on the second run."""
    env = pipeline_env
    make_png(env["photos_dir"] / "family.png")
    (env["data_dir"] / "sidecars").mkdir(parents=True, exist_ok=True)

    import app.indexer.scan as scan_mod
    import app.indexer.google_metadata as gm_mod
    import app.indexer.location as loc_mod
    import app.indexer.caption as caption_mod
    import app.indexer.embed as embed_mod
    import app.chroma as chroma_mod

    def run_pipeline():
        scan_mod.run_scan()
        gm_mod.run_google_metadata()
        with patch("app.indexer.location.reverse_geocoder.search", return_value=[]):
            loc_mod.run_location()
        with patch.object(caption_mod, "get_caption_provider", return_value=env["mock_caption_provider"]):
            caption_mod.run_caption(limit=10)
        with (
            patch.object(embed_mod, "get_embed_provider", return_value=env["mock_embed_provider"]),
            patch.object(embed_mod, "get_collection", return_value=env["mock_collection"]),
            patch.object(embed_mod, "assert_embed_model"),
            patch.object(chroma_mod, "get_collection", return_value=env["mock_collection"]),
        ):
            embed_mod.run_embed()

    run_pipeline()
    assert env["mock_caption_provider"].caption.call_count == 1
    assert env["mock_embed_provider"].embed.call_count == 1

    env["mock_caption_provider"].caption.reset_mock()
    env["mock_embed_provider"].embed.reset_mock()
    env["mock_collection"].upsert.reset_mock()

    run_pipeline()
    assert env["mock_caption_provider"].caption.call_count == 0, "caption re-called on 2nd run"
    assert env["mock_embed_provider"].embed.call_count == 0, "embed re-called on 2nd run"
    assert env["mock_collection"].upsert.call_count == 0, "chroma upsert re-called on 2nd run"


def test_sidecar_gps_flows_to_location_hint_in_caption(pipeline_env):
    """No EXIF GPS → sidecar geoData → location geocodes → caption receives location_name as hint."""
    env = pipeline_env
    make_png(env["photos_dir"] / "telav.png")

    import app.indexer.scan as scan_mod
    import app.indexer.google_metadata as gm_mod
    import app.indexer.location as loc_mod
    import app.indexer.caption as caption_mod

    scan_mod.run_scan()

    with get_session() as s:
        photo_id = s.execute(select(Photo.id)).scalar_one()

    sidecars_dir = env["data_dir"] / "sidecars"
    sidecars_dir.mkdir(parents=True, exist_ok=True)
    (sidecars_dir / f"{photo_id}.json").write_text(json.dumps({
        "geoData": {"latitude": 32.0853, "longitude": 34.7818},
    }))

    gm_mod.run_google_metadata()

    fake_geocode = [{"name": "Tel Aviv-Yafo", "cc": "IL"}]
    with patch("app.indexer.location.reverse_geocoder.search", return_value=fake_geocode):
        loc_mod.run_location()

    row = _photo_row()
    assert row.location_name == "Tel Aviv-Yafo, IL"

    with patch.object(caption_mod, "get_caption_provider", return_value=env["mock_caption_provider"]):
        caption_mod.run_caption(limit=10)

    call_args = env["mock_caption_provider"].caption.call_args
    assert call_args.kwargs.get("location_hint") == "Tel Aviv-Yafo, IL"


def test_document_content_type_blocks_embed(pipeline_env):
    """Photos captioned as 'document' or 'other' must not reach embed."""
    env = pipeline_env
    make_png(env["photos_dir"] / "receipt.png")
    make_png(env["photos_dir"] / "meme.png")
    make_png(env["photos_dir"] / "photo.png")
    (env["data_dir"] / "sidecars").mkdir(parents=True, exist_ok=True)

    import app.indexer.scan as scan_mod
    import app.indexer.google_metadata as gm_mod
    import app.indexer.caption as caption_mod
    import app.indexer.embed as embed_mod
    import app.chroma as chroma_mod

    scan_mod.run_scan()
    gm_mod.run_google_metadata()

    responses_by_name = {
        "receipt.png": dict(FULL_CAPTION_RESPONSE, content_type="document"),
        "meme.png": dict(FULL_CAPTION_RESPONSE, content_type="other"),
        "photo.png": dict(FULL_CAPTION_RESPONSE, content_type="photo"),
    }

    async def caption_by_name(path, location_hint=None):
        return responses_by_name[path.name]

    env["mock_caption_provider"].caption = AsyncMock(side_effect=caption_by_name)

    with patch.object(caption_mod, "get_caption_provider", return_value=env["mock_caption_provider"]):
        caption_count = caption_mod.run_caption(limit=10)

    assert caption_count == 3

    with (
        patch.object(embed_mod, "get_embed_provider", return_value=env["mock_embed_provider"]),
        patch.object(embed_mod, "get_collection", return_value=env["mock_collection"]),
        patch.object(embed_mod, "assert_embed_model"),
        patch.object(chroma_mod, "get_collection", return_value=env["mock_collection"]),
    ):
        embedded_count = embed_mod.run_embed()

    assert embedded_count == 1, "only 'photo' content_type should be embedded"
    assert env["mock_collection"].upsert.call_count == 1

    upserted_id = env["mock_collection"].upsert.call_args.kwargs["ids"][0]
    with get_session() as s:
        photo_id = s.execute(
            select(Photo.id).where(Photo.original_filename == "photo.png")
        ).scalar_one()
    assert upserted_id == photo_id


def test_reindex_forces_full_pipeline_reprocess(pipeline_env):
    """reindex=True causes every step to re-process already-indexed photos."""
    env = pipeline_env
    make_png(env["photos_dir"] / "family.png")
    (env["data_dir"] / "sidecars").mkdir(parents=True, exist_ok=True)

    import app.indexer.scan as scan_mod
    import app.indexer.google_metadata as gm_mod
    import app.indexer.location as loc_mod
    import app.indexer.caption as caption_mod
    import app.indexer.embed as embed_mod
    import app.chroma as chroma_mod

    def run_pipeline(reindex=False):
        scan_mod.run_scan(reindex=reindex)
        gm_mod.run_google_metadata(reindex=reindex)
        with patch("app.indexer.location.reverse_geocoder.search", return_value=[]):
            loc_mod.run_location(reindex=reindex)
        with patch.object(caption_mod, "get_caption_provider", return_value=env["mock_caption_provider"]):
            caption_mod.run_caption(limit=10, reindex=reindex)
        with (
            patch.object(embed_mod, "get_embed_provider", return_value=env["mock_embed_provider"]),
            patch.object(embed_mod, "get_collection", return_value=env["mock_collection"]),
            patch.object(embed_mod, "assert_embed_model"),
            patch.object(chroma_mod, "get_collection", return_value=env["mock_collection"]),
        ):
            embed_mod.run_embed(reindex=reindex)

    run_pipeline(reindex=False)
    assert env["mock_caption_provider"].caption.call_count == 1
    assert env["mock_embed_provider"].embed.call_count == 1

    env["mock_caption_provider"].caption.reset_mock()
    env["mock_embed_provider"].embed.reset_mock()
    env["mock_collection"].upsert.reset_mock()

    run_pipeline(reindex=True)
    assert env["mock_caption_provider"].caption.call_count == 1, "reindex=True must re-caption"
    assert env["mock_embed_provider"].embed.call_count == 1, "reindex=True must re-embed"
    assert env["mock_collection"].upsert.call_count == 1, "reindex=True must re-upsert to chroma"


def test_merge_autoscan_feeds_downstream_steps(pipeline_env, tmp_path):
    """run_merge → run_scan(prehashed=result['items']) → caption → embed: photo fully indexed."""
    env = pipeline_env

    import app.indexer.merge as merge_mod
    import app.indexer.scan as scan_mod
    import app.indexer.caption as caption_mod
    import app.indexer.embed as embed_mod
    import app.chroma as chroma_mod

    takeout = tmp_path / "Takeout"
    folder = takeout / "Photos from 2022"
    folder.mkdir(parents=True)
    photo = folder / "vacation.png"
    make_png(photo)
    sidecar = {"photoTakenTime": {"timestamp": "1640000000"}}
    (folder / "vacation.png.supplemental-metadata.json").write_text(json.dumps(sidecar))

    result = merge_mod.run_merge([takeout])
    assert result["merged"] == 1
    assert len(result["items"]) == 1

    scan_mod.run_scan(prehashed=result["items"])

    with patch.object(caption_mod, "get_caption_provider", return_value=env["mock_caption_provider"]):
        caption_count = caption_mod.run_caption(limit=10)

    assert caption_count == 1
    env["mock_caption_provider"].caption.assert_called_once()

    with (
        patch.object(embed_mod, "get_embed_provider", return_value=env["mock_embed_provider"]),
        patch.object(embed_mod, "get_collection", return_value=env["mock_collection"]),
        patch.object(embed_mod, "assert_embed_model"),
        patch.object(chroma_mod, "get_collection", return_value=env["mock_collection"]),
    ):
        embedded = embed_mod.run_embed()

    assert embedded == 1

    row = _photo_row()
    assert row.original_filename == "vacation.png"
    assert row.scan_indexed_at is not None
    assert row.caption_indexed_at is not None
    assert row.vector_indexed_at is not None


def test_embed_schema_version_tracks_caption_schema_version(pipeline_env):
    """embed_schema_version equals caption_schema_version after embed; reindex re-embeds after advance."""
    env = pipeline_env
    make_png(env["photos_dir"] / "family.png")
    (env["data_dir"] / "sidecars").mkdir(parents=True, exist_ok=True)

    import app.indexer.scan as scan_mod
    import app.indexer.google_metadata as gm_mod
    import app.indexer.caption as caption_mod
    import app.indexer.embed as embed_mod
    import app.chroma as chroma_mod

    scan_mod.run_scan()
    gm_mod.run_google_metadata()

    with patch.object(caption_mod, "get_caption_provider", return_value=env["mock_caption_provider"]):
        caption_mod.run_caption(limit=10)

    with (
        patch.object(embed_mod, "get_embed_provider", return_value=env["mock_embed_provider"]),
        patch.object(embed_mod, "get_collection", return_value=env["mock_collection"]),
        patch.object(embed_mod, "assert_embed_model"),
        patch.object(chroma_mod, "get_collection", return_value=env["mock_collection"]),
    ):
        embed_mod.run_embed()

    row = _photo_row()
    csv = row.caption_schema_version
    assert row.embed_schema_version == csv

    # Simulate schema bump
    with get_session() as s:
        s.execute(update(Photo).values(caption_schema_version=csv + 1))

    env["mock_embed_provider"].embed.reset_mock()
    env["mock_collection"].upsert.reset_mock()

    with (
        patch.object(embed_mod, "get_embed_provider", return_value=env["mock_embed_provider"]),
        patch.object(embed_mod, "get_collection", return_value=env["mock_collection"]),
        patch.object(embed_mod, "assert_embed_model"),
        patch.object(chroma_mod, "get_collection", return_value=env["mock_collection"]),
    ):
        count = embed_mod.run_embed(reindex=True)

    assert count == 1
    assert env["mock_embed_provider"].embed.call_count == 1

    row = _photo_row()
    assert row.embed_schema_version == csv + 1


def test_pre_caption_chains_scan_google_metadata_location(pipeline_env):
    """pre_caption = scan + google_metadata + location populates all three upstream columns."""
    env = pipeline_env
    make_png(env["photos_dir"] / "beach.png")

    import app.indexer.scan as scan_mod
    import app.indexer.google_metadata as gm_mod
    import app.indexer.location as loc_mod

    scan_mod.run_scan()
    with get_session() as s:
        photo_id = s.execute(select(Photo.id)).scalar_one()

    sidecars_dir = env["data_dir"] / "sidecars"
    sidecars_dir.mkdir(parents=True, exist_ok=True)
    (sidecars_dir / f"{photo_id}.json").write_text(json.dumps({
        "photoTakenTime": {"timestamp": "1577880000"},
        "geoData": {"latitude": 51.5074, "longitude": -0.1278},
    }))

    # Reset so pre_caption runs scan fresh
    with get_session() as s:
        s.execute(update(Photo).values(scan_indexed_at=None))

    fake_geocode = [{"name": "London", "cc": "GB"}]
    with patch("app.indexer.location.reverse_geocoder.search", return_value=fake_geocode):
        scan_mod.run_scan()
        gm_mod.run_google_metadata()
        loc_mod.run_location()

    row = _photo_row()
    assert row.scan_indexed_at is not None
    assert row.google_metadata_indexed_at is not None
    assert row.location_name == "London, GB"
    assert row.taken_at is not None
    assert "2020" in row.taken_at


def test_caption_limit_restricts_downstream_embed(pipeline_env):
    """caption(limit=2) → only 2 photos captioned → embed processes exactly 2."""
    env = pipeline_env
    for i in range(5):
        make_png(env["photos_dir"] / f"photo_{i}.png")
    (env["data_dir"] / "sidecars").mkdir(parents=True, exist_ok=True)

    import app.indexer.scan as scan_mod
    import app.indexer.google_metadata as gm_mod
    import app.indexer.caption as caption_mod
    import app.indexer.embed as embed_mod
    import app.chroma as chroma_mod

    scan_mod.run_scan()
    gm_mod.run_google_metadata()

    with patch.object(caption_mod, "get_caption_provider", return_value=env["mock_caption_provider"]):
        captioned = caption_mod.run_caption(limit=2)

    assert captioned == 2
    assert env["mock_caption_provider"].caption.call_count == 2

    with (
        patch.object(embed_mod, "get_embed_provider", return_value=env["mock_embed_provider"]),
        patch.object(embed_mod, "get_collection", return_value=env["mock_collection"]),
        patch.object(embed_mod, "assert_embed_model"),
        patch.object(chroma_mod, "get_collection", return_value=env["mock_collection"]),
    ):
        embedded = embed_mod.run_embed()

    assert embedded == 2
    assert env["mock_collection"].upsert.call_count == 2

    with get_session() as s:
        not_embedded = s.query(Photo).filter(Photo.vector_indexed_at.is_(None)).count()
    assert not_embedded == 3
