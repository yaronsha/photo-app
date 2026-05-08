# Embed Schema Version Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement task-by-task.

**Goal:** Track which caption version was embedded per photo so re-captioned photos are automatically re-embedded.

**Architecture:** Add `embed_schema_version INTEGER` to `photos`. When embedding, write the photo's current `caption_schema_version` into it. Skip predicate becomes `embed_schema_version IS NULL OR embed_schema_version < caption_schema_version` instead of `vector_indexed_at IS NULL`. `--reindex` bypasses the predicate as before.

---

### Task 1: Add column to schema

**Files:**
- Modify: `app/db.py` — add to `PHOTOS_ATTRIBUTE_COLUMNS`

- [ ] Add `("embed_schema_version", "INTEGER")` to `PHOTOS_ATTRIBUTE_COLUMNS`:

```python
PHOTOS_ATTRIBUTE_COLUMNS: list[tuple[str, str]] = [
    ("activities", "TEXT"),
    ("content_type", "TEXT"),
    ("subject_type", "TEXT"),
    ("primary_focus", "TEXT"),
    ("indoor_outdoor", "TEXT"),
    ("setting_type", "TEXT"),
    ("sharpness", "TEXT"),
    ("face_clarity_score", "INTEGER"),
    ("caption_schema_version", "INTEGER"),
    ("embed_schema_version", "INTEGER"),
]
```

The ALTER TABLE pattern in `init_schema` handles adding it to existing DBs automatically.

- [ ] Commit: `git commit -m "feat(embed): add embed_schema_version column"`

---

### Task 2: Update embed step

**Files:**
- Modify: `app/indexer/embed.py`

- [ ] Update SELECT to include `caption_schema_version` and update skip predicate:

```python
base = (
    "SELECT id, caption, activities, content_type, taken_at, caption_schema_version FROM photos "
    "WHERE caption IS NOT NULL "
    "AND (content_type IS NULL OR content_type NOT IN ('document', 'other'))"
)
stale = (
    " AND (embed_schema_version IS NULL"
    " OR embed_schema_version < caption_schema_version)"
)
query = base if reindex else base + stale
```

- [ ] Write `embed_schema_version` on successful embed (replace the existing `UPDATE photos SET vector_indexed_at` line):

```python
conn.execute(
    "UPDATE photos SET vector_indexed_at = ?, embed_schema_version = ? WHERE id = ?",
    (now, row["caption_schema_version"], row["id"]),
)
```

- [ ] Commit: `git commit -m "feat(embed): re-embed when caption_schema_version advances"`

---

### Task 3: Update tests

**Files:**
- Modify: `tests/test_embed.py`

- [ ] Update `_seed` helper to accept optional `caption_schema_version` (default `1`):

```python
def _seed(db_path: Path, rows: list[tuple]):
    conn = sqlite3.connect(str(db_path))
    from app.db import init_schema
    init_schema(conn)
    for pid, caption, activities, content_type, *rest in rows:
        csv = rest[0] if rest else 1
        conn.execute(
            "INSERT INTO photos (id, storage_path, original_filename, caption, "
            "activities, content_type, taken_at, scan_indexed_at, caption_indexed_at, "
            "caption_schema_version) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (pid, f"/tmp/{pid}.jpg", f"{pid}.jpg",
             caption, json.dumps(activities), content_type,
             "2022-01-01T00:00:00+00:00",
             "2022-01-01T00:00:00+00:00",
             "2022-01-01T00:00:00+00:00",
             csv),
        )
    conn.commit()
    conn.close()
```

- [ ] Add test for stale-embed detection:

```python
def test_embed_reruns_when_caption_version_advances(tmp_env):
    db_path = tmp_env["data_dir"] / "photos.db"
    _seed(db_path, [("p1", "a beach", ["swimming"], "photo", 2)])

    # simulate already embedded at caption_schema_version=1
    conn = sqlite3.connect(str(db_path))
    conn.execute("UPDATE photos SET embed_schema_version=1 WHERE id='p1'")
    conn.commit()
    conn.close()

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
```

- [ ] Add test that up-to-date embed is skipped:

```python
def test_embed_skips_when_already_current(tmp_env):
    db_path = tmp_env["data_dir"] / "photos.db"
    _seed(db_path, [("p1", "a beach", ["swimming"], "photo", 2)])

    conn = sqlite3.connect(str(db_path))
    conn.execute("UPDATE photos SET embed_schema_version=2 WHERE id='p1'")
    conn.commit()
    conn.close()

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
```

- [ ] Run all embed tests: `uv run pytest tests/test_embed.py -v`
- [ ] Commit: `git commit -m "test(embed): cover embed_schema_version staleness logic"`
