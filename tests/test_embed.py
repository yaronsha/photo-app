from unittest.mock import MagicMock, patch

from sqlalchemy import update

from app.db import Photo, get_session, init_schema


def _seed(rows: list[tuple]):
    init_schema()
    with get_session() as s:
        for pid, caption, activities, content_type, *rest in rows:
            csv = rest[0] if rest else 1
            s.add(Photo(
                id=pid,
                storage_path=f"/tmp/{pid}.jpg",
                original_filename=f"{pid}.jpg",
                caption=caption,
                activities=activities,
                content_type=content_type,
                taken_at="2022-01-01T00:00:00+00:00",
                scan_indexed_at="2022-01-01T00:00:00+00:00",
                caption_indexed_at="2022-01-01T00:00:00+00:00",
                caption_schema_version=csv,
            ))


def test_embed_skips_documents(tmp_env):
    _seed([
        ("p_photo", "a beach", ["swimming"], "photo"),
        ("p_doc", "a receipt", [], "document"),
        ("p_other", "a meme", [], "other"),
    ])

    mock_provider = MagicMock()
    mock_provider.embed.return_value = [0.1] * 1536

    mock_collection = MagicMock()

    import app.indexer.embed as embed_mod
    import app.chroma as chroma_mod

    with (
        patch.object(embed_mod, "get_embed_provider", return_value=mock_provider),
        patch.object(embed_mod, "get_collection", return_value=mock_collection),
        patch.object(embed_mod, "assert_embed_model"),
        patch.object(chroma_mod, "get_collection", return_value=mock_collection),
    ):
        count = embed_mod.run_embed()

    assert count == 1
    upsert_calls = mock_collection.upsert.call_args_list
    upserted_ids = [call.kwargs["ids"][0] for call in upsert_calls]
    assert upserted_ids == ["p_photo"]


def test_embed_text_includes_activities(tmp_env):
    _seed([
        ("p1", "kids on beach", ["swimming", "playing"], "photo"),
    ])

    mock_provider = MagicMock()
    mock_provider.embed.return_value = [0.1] * 1536

    mock_collection = MagicMock()

    import app.indexer.embed as embed_mod
    import app.chroma as chroma_mod

    with (
        patch.object(embed_mod, "get_embed_provider", return_value=mock_provider),
        patch.object(embed_mod, "get_collection", return_value=mock_collection),
        patch.object(embed_mod, "assert_embed_model"),
        patch.object(chroma_mod, "get_collection", return_value=mock_collection),
    ):
        embed_mod.run_embed()

    assert mock_provider.embed.call_count == 1
    text = mock_provider.embed.call_args.args[0]
    assert "kids on beach" in text
    assert "swimming" in text
    assert "playing" in text


def test_embed_text_omits_tags(tmp_env):
    """Tags column should NOT be part of embed text — only caption + activities."""
    init_schema()
    with get_session() as s:
        s.add(Photo(
            id="p1",
            storage_path="/tmp/p1.jpg",
            original_filename="p1.jpg",
            caption="two children running",
            tags=["zebrazebra", "yellowbananatag", "purpleorchid"],
            activities=[],
            content_type="photo",
            taken_at="2022-01-01T00:00:00+00:00",
            scan_indexed_at="2022-01-01T00:00:00+00:00",
            caption_indexed_at="2022-01-01T00:00:00+00:00",
        ))

    mock_provider = MagicMock()
    mock_provider.embed.return_value = [0.1] * 1536
    mock_collection = MagicMock()

    import app.indexer.embed as embed_mod
    import app.chroma as chroma_mod

    with (
        patch.object(embed_mod, "get_embed_provider", return_value=mock_provider),
        patch.object(embed_mod, "get_collection", return_value=mock_collection),
        patch.object(embed_mod, "assert_embed_model"),
        patch.object(chroma_mod, "get_collection", return_value=mock_collection),
    ):
        embed_mod.run_embed()

    text = mock_provider.embed.call_args.args[0]
    assert "two children running" in text
    for tag in ("zebrazebra", "yellowbananatag", "purpleorchid"):
        assert tag not in text, f"tag {tag!r} should not be in embed text"


def test_embed_reruns_when_caption_version_advances(tmp_env):
    _seed([("p1", "a beach", ["swimming"], "photo", 2)])

    with get_session() as s:
        s.execute(update(Photo).where(Photo.id == "p1").values(embed_schema_version=1))

    mock_provider = MagicMock()
    mock_provider.embed.return_value = [0.1] * 1536
    mock_collection = MagicMock()

    import app.indexer.embed as embed_mod
    import app.chroma as chroma_mod

    with (
        patch.object(embed_mod, "get_embed_provider", return_value=mock_provider),
        patch.object(embed_mod, "get_collection", return_value=mock_collection),
        patch.object(embed_mod, "assert_embed_model"),
        patch.object(chroma_mod, "get_collection", return_value=mock_collection),
    ):
        count = embed_mod.run_embed()

    assert count == 1  # re-embedded because embed_schema_version(1) < caption_schema_version(2)


def test_embed_skips_when_already_current(tmp_env):
    _seed([("p1", "a beach", ["swimming"], "photo", 2)])

    with get_session() as s:
        s.execute(update(Photo).where(Photo.id == "p1").values(embed_schema_version=2))

    mock_provider = MagicMock()
    mock_provider.embed.return_value = [0.1] * 1536
    mock_collection = MagicMock()

    import app.indexer.embed as embed_mod
    import app.chroma as chroma_mod

    with (
        patch.object(embed_mod, "get_embed_provider", return_value=mock_provider),
        patch.object(embed_mod, "get_collection", return_value=mock_collection),
        patch.object(embed_mod, "assert_embed_model"),
        patch.object(chroma_mod, "get_collection", return_value=mock_collection),
    ):
        count = embed_mod.run_embed()

    assert count == 0  # already current
