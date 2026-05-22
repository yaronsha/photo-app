"""Contract tests for app/storage — runs LocalStorage against tmp_path."""
import io

import pytest

from app.storage.local import LocalStorage


@pytest.fixture()
def local(tmp_path):
    return LocalStorage(tmp_path)


def test_write_and_read_bytes(local):
    local.write_bytes("photos/a.jpg", b"hello")
    assert local.read_bytes("photos/a.jpg") == b"hello"


def test_write_creates_parent_dirs(local, tmp_path):
    local.write_bytes("deep/nested/dir/file.jpg", b"data")
    assert (tmp_path / "deep" / "nested" / "dir" / "file.jpg").exists()


def test_exists_true(local):
    local.write_bytes("test.jpg", b"x")
    assert local.exists("test.jpg") is True


def test_exists_false(local):
    assert local.exists("nonexistent.jpg") is False


def test_open_stream(local):
    local.write_bytes("stream.jpg", b"streamdata")
    with local.open_stream("stream.jpg") as f:
        assert f.read() == b"streamdata"


def test_delete(local):
    local.write_bytes("todelete.jpg", b"bye")
    local.delete("todelete.jpg")
    assert local.exists("todelete.jpg") is False


def test_delete_missing_is_noop(local):
    local.delete("does_not_exist.jpg")  # should not raise


def test_iter_prefix(local):
    local.write_bytes("photos/2020/a.jpg", b"a")
    local.write_bytes("photos/2020/b.jpg", b"b")
    local.write_bytes("thumbs/a.jpg", b"t")

    keys = sorted(local.iter_prefix("photos"))
    assert keys == ["photos/2020/a.jpg", "photos/2020/b.jpg"]


def test_iter_prefix_missing_returns_empty(local):
    assert list(local.iter_prefix("nonexistent")) == []


def test_presign_get_returns_local_url(local):
    url = local.presign_get("photos/2020/img.jpg")
    assert url == "/local/photos/2020/img.jpg"


def test_write_bytes_with_content_type(local):
    # content_type is a hint — LocalStorage stores the bytes regardless
    local.write_bytes("sidecars/abc.json", b'{"x": 1}', content_type="application/json")
    assert local.read_bytes("sidecars/abc.json") == b'{"x": 1}'


def test_storage_factory_local(tmp_path, monkeypatch):
    """get_storage() returns LocalStorage when STORAGE_BACKEND=local."""
    import json

    cfg = {
        "family_name": "Test",
        "data_dir": str(tmp_path / "data"),
        "caption_model": "gpt-4o",
        "embed_model": "text-embedding-3-small",
    }
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(cfg))
    (tmp_path / "data").mkdir()

    monkeypatch.setenv("STORAGE_BACKEND", "local")
    import app.config as config_mod
    monkeypatch.setattr(config_mod, "_CONFIG_PATH", cfg_path)
    monkeypatch.setattr(config_mod, "_settings", None)

    import app.storage as storage_mod
    storage_mod.reset_storage()

    storage = storage_mod.get_storage()
    from app.storage.local import LocalStorage
    assert isinstance(storage, LocalStorage)

    storage_mod.reset_storage()
    config_mod._settings = None


def test_storage_factory_unknown_backend(monkeypatch):
    import app.storage as storage_mod
    storage_mod.reset_storage()
    monkeypatch.setenv("STORAGE_BACKEND", "gcs")

    with pytest.raises(ValueError, match="STORAGE_BACKEND"):
        storage_mod.get_storage()

    storage_mod.reset_storage()
