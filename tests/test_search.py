from pathlib import Path
from unittest.mock import MagicMock, patch

from app.db import Person, Photo, PhotoPerson, get_session, init_schema
from app.vectordb.base import VectorBackend


def _seed_db(photos_dir: Path) -> str:
    init_schema()
    photo_id = "abc123def456abc1"
    with get_session() as s:
        s.add(Photo(
            id=photo_id,
            storage_path="photos/beach.jpg",
            original_filename="beach.jpg",
            caption="A sunny day at the beach",
            tags=["beach", "sunny", "ocean"],
            taken_at="2022-07-15T12:00:00+00:00",
            scan_indexed_at="2022-07-15T12:00:00+00:00",
            caption_indexed_at="2022-07-15T12:00:00+00:00",
            vector_indexed_at="2022-07-15T12:00:00+00:00",
        ))
    return photo_id


def test_search_returns_results(tmp_env):
    photo_id = _seed_db(tmp_env["photos_dir"])

    mock_embed_provider = MagicMock()
    query_vec = [0.1] * 1536
    mock_embed_provider.embed.return_value = query_vec

    mock_vector_db = MagicMock(spec=VectorBackend)
    mock_vector_db.count.return_value = 1
    mock_vector_db.query.return_value = [(photo_id, 0.1)]

    import app.search.query as query_mod

    with patch.object(query_mod, "get_embed_provider", return_value=mock_embed_provider):
        results, _ = query_mod.search("beach", limit=10, vector_db=mock_vector_db)

    assert len(results) == 1
    assert results[0].id == photo_id
    assert results[0].caption == "A sunny day at the beach"
    assert abs(results[0].score - 0.9) < 0.001


def test_search_empty_collection(tmp_env):
    _seed_db(tmp_env["photos_dir"])

    mock_embed_provider = MagicMock()
    mock_embed_provider.embed.return_value = [0.0] * 1536

    mock_vector_db = MagicMock(spec=VectorBackend)
    mock_vector_db.count.return_value = 0
    mock_vector_db.query.return_value = []

    import app.search.query as query_mod

    with patch.object(query_mod, "get_embed_provider", return_value=mock_embed_provider):
        results, _ = query_mod.search("anything", vector_db=mock_vector_db)

    assert results == []


def _seed_multi(photos_dir: Path) -> list[str]:
    init_schema()
    rows = [
        ("id_feb2015", "feb15.jpg", "2015-02-10T12:00:00+00:00", "feb 2015"),
        ("id_mar2015", "mar15.jpg", "2015-03-15T12:00:00+00:00", "mar 2015"),
        ("id_mar2015b", "mar15b.jpg", "2015-03-28T12:00:00+00:00", "mar 2015 late"),
        ("id_apr2015", "apr15.jpg", "2015-04-05T12:00:00+00:00", "apr 2015"),
    ]
    with get_session() as s:
        for pid, fname, taken, cap in rows:
            s.add(Photo(
                id=pid,
                storage_path=f"photos/{fname}",
                original_filename=fname,
                caption=cap,
                taken_at=taken,
                scan_indexed_at=taken,
                caption_indexed_at=taken,
                vector_indexed_at=taken,
            ))
    return [r[0] for r in rows]


def test_browse_by_date_range_no_query(tmp_env):
    _seed_multi(tmp_env["photos_dir"])

    import app.search.query as query_mod

    mock_vector_db = MagicMock(spec=VectorBackend)

    results, _ = query_mod.search(
        None, date_from="2015-03-01", date_to="2015-03-31", vector_db=mock_vector_db
    )

    result_ids = {r.id for r in results}
    assert result_ids == {"id_mar2015", "id_mar2015b"}
    assert results[0].taken_at > results[1].taken_at  # DESC
    mock_vector_db.query.assert_not_called()


def test_browse_empty_returns_nothing(tmp_env):
    _seed_multi(tmp_env["photos_dir"])

    import app.search.query as query_mod

    assert query_mod.search(None) == ([], False)
    assert query_mod.search("") == ([], False)


def test_vector_search_filters_by_date(tmp_env):
    ids = _seed_multi(tmp_env["photos_dir"])

    mock_embed_provider = MagicMock()
    mock_embed_provider.embed.return_value = [0.1] * 1536

    mock_vector_db = MagicMock(spec=VectorBackend)
    mock_vector_db.count.return_value = 4
    mock_vector_db.query.return_value = [
        (ids[0], 0.1), (ids[1], 0.2), (ids[2], 0.3), (ids[3], 0.4)
    ]

    import app.search.query as query_mod

    with patch.object(query_mod, "get_embed_provider", return_value=mock_embed_provider):
        results, _ = query_mod.search(
            "anything", date_from="2015-03-01", date_to="2015-03-31",
            vector_db=mock_vector_db,
        )

    assert {r.id for r in results} == {"id_mar2015", "id_mar2015b"}


def test_date_to_inclusive(tmp_env):
    _seed_multi(tmp_env["photos_dir"])

    import app.search.query as query_mod

    # date_to inclusive — 2015-03-28 should include the 2015-03-28T12:00 photo
    results, _ = query_mod.search(
        None, date_from="2015-03-28", date_to="2015-03-28"
    )

    assert {r.id for r in results} == {"id_mar2015b"}


def _seed_people_db(photos_dir: Path) -> dict:
    """3 photos: photo_ab (alice+bob), photo_a (alice only), photo_b (bob only)."""
    init_schema()
    with get_session() as s:
        for pid, fname, taken in [
            ("photo_ab", "ab.jpg", "2020-01-01T12:00:00+00:00"),
            ("photo_a",  "a.jpg",  "2020-01-02T12:00:00+00:00"),
            ("photo_b",  "b.jpg",  "2020-01-03T12:00:00+00:00"),
        ]:
            s.add(Photo(
                id=pid,
                storage_path=f"photos/{fname}",
                original_filename=fname,
                caption="caption",
                taken_at=taken,
                scan_indexed_at=taken,
                caption_indexed_at=taken,
                vector_indexed_at=taken,
            ))
        s.add(Person(id="alice", name="Alice"))
        s.add(Person(id="bob", name="Bob"))
        for photo_id, person_id in [
            ("photo_ab", "alice"), ("photo_ab", "bob"),
            ("photo_a",  "alice"),
            ("photo_b",  "bob"),
        ]:
            s.add(PhotoPerson(photo_id=photo_id, person_id=person_id))
    return {"photo_ab": "photo_ab", "photo_a": "photo_a", "photo_b": "photo_b"}


def test_browse_people_any_mode(tmp_env):
    _seed_people_db(tmp_env["photos_dir"])

    import app.search.query as query_mod

    results, _ = query_mod.search(
        None,
        date_from="2020-01-01",
        date_to="2020-01-03",
        person_ids=["alice", "bob"],
        people_mode="any",
    )

    assert {r.id for r in results} == {"photo_ab", "photo_a", "photo_b"}


def test_browse_people_all_mode(tmp_env):
    _seed_people_db(tmp_env["photos_dir"])

    import app.search.query as query_mod

    results, _ = query_mod.search(
        None,
        date_from="2020-01-01",
        date_to="2020-01-03",
        person_ids=["alice", "bob"],
        people_mode="all",
    )

    assert {r.id for r in results} == {"photo_ab"}


def test_vector_search_people_all_mode(tmp_env):
    _seed_people_db(tmp_env["photos_dir"])

    mock_embed_provider = MagicMock()
    mock_embed_provider.embed.return_value = [0.1] * 1536

    mock_vector_db = MagicMock(spec=VectorBackend)
    mock_vector_db.count.return_value = 3
    mock_vector_db.query.return_value = [
        ("photo_ab", 0.1), ("photo_a", 0.2), ("photo_b", 0.3)
    ]

    import app.search.query as query_mod

    with patch.object(query_mod, "get_embed_provider", return_value=mock_embed_provider):
        results, _ = query_mod.search(
            "family",
            person_ids=["alice", "bob"],
            people_mode="all",
            vector_db=mock_vector_db,
        )

    assert {r.id for r in results} == {"photo_ab"}


def test_browse_people_all_mode_single_person(tmp_env):
    """all mode with N=1 should behave identically to any mode."""
    _seed_people_db(tmp_env["photos_dir"])

    import app.search.query as query_mod

    results, _ = query_mod.search(
        None,
        date_from="2020-01-01",
        date_to="2020-01-03",
        person_ids=["alice"],
        people_mode="all",
    )

    assert {r.id for r in results} == {"photo_ab", "photo_a"}


def _seed_mixed_content(photos_dir: Path) -> list[str]:
    """3 rows: photo, document, pre-migration (NULL content_type)."""
    init_schema()
    rows = [
        ("id_photo", "p.jpg", "photo", "a beach photo"),
        ("id_doc", "d.jpg", "document", "a receipt scan"),
        ("id_legacy", "l.jpg", None, "old un-migrated row"),
    ]
    taken = "2021-06-01T12:00:00+00:00"
    with get_session() as s:
        for pid, fname, ctype, cap in rows:
            s.add(Photo(
                id=pid,
                storage_path=f"photos/{fname}",
                original_filename=fname,
                caption=cap,
                content_type=ctype,
                taken_at=taken,
                scan_indexed_at=taken,
                caption_indexed_at=taken,
                vector_indexed_at=taken,
            ))
    return [r[0] for r in rows]


def test_browse_excludes_documents_by_default(tmp_env):
    _seed_mixed_content(tmp_env["photos_dir"])

    import app.search.query as query_mod

    results, _ = query_mod.search(
        None, date_from="2021-06-01", date_to="2021-06-01"
    )

    assert {r.id for r in results} == {"id_photo", "id_legacy"}


def test_browse_include_docs_returns_everything(tmp_env):
    _seed_mixed_content(tmp_env["photos_dir"])

    import app.search.query as query_mod

    results, _ = query_mod.search(
        None,
        date_from="2021-06-01",
        date_to="2021-06-01",
        include_docs=True,
    )

    assert {r.id for r in results} == {"id_photo", "id_doc", "id_legacy"}


def test_vector_search_excludes_documents_by_default(tmp_env):
    ids = _seed_mixed_content(tmp_env["photos_dir"])

    mock_embed_provider = MagicMock()
    mock_embed_provider.embed.return_value = [0.1] * 1536

    mock_vector_db = MagicMock(spec=VectorBackend)
    mock_vector_db.count.return_value = len(ids)
    mock_vector_db.query.return_value = [
        (ids[0], 0.1), (ids[1], 0.2), (ids[2], 0.3)
    ]

    import app.search.query as query_mod

    with patch.object(query_mod, "get_embed_provider", return_value=mock_embed_provider):
        results, _ = query_mod.search("anything", vector_db=mock_vector_db)

    assert {r.id for r in results} == {"id_photo", "id_legacy"}


def test_browse_people_default_mode_is_any(tmp_env):
    """Default people_mode should be 'any' (no explicit argument)."""
    _seed_people_db(tmp_env["photos_dir"])

    import app.search.query as query_mod

    results, _ = query_mod.search(
        None,
        date_from="2020-01-01",
        date_to="2020-01-03",
        person_ids=["alice", "bob"],
        # no people_mode argument — default should be "any"
    )

    assert {r.id for r in results} == {"photo_ab", "photo_a", "photo_b"}


def test_browse_offset(tmp_env):
    _seed_multi(tmp_env["photos_dir"])
    # ids ordered DESC by taken_at: apr, mar-late, mar, feb

    import app.search.query as query_mod

    results, _ = query_mod.search(
        None, date_from="2015-02-01", date_to="2015-04-30", limit=2, offset=2
    )

    # first 2 (offset=0) would be apr and mar-late; offset=2 gives mar and feb
    assert [r.id for r in results] == ["id_mar2015", "id_feb2015"]


def test_browse_has_more_true(tmp_env):
    _seed_multi(tmp_env["photos_dir"])

    import app.search.query as query_mod

    results, has_more = query_mod.search(
        None, date_from="2015-02-01", date_to="2015-04-30", limit=2
    )

    assert len(results) == 2
    assert has_more is True


def test_browse_has_more_false(tmp_env):
    _seed_multi(tmp_env["photos_dir"])

    import app.search.query as query_mod

    results, has_more = query_mod.search(
        None, date_from="2015-02-01", date_to="2015-04-30", limit=10
    )

    assert len(results) == 4
    assert has_more is False
