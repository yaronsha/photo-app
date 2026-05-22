"""Pre-generate thumbnails for all indexed photos and store via storage backend."""
import io

from PIL import Image, ImageOps
from sqlalchemy import select

from ..db import Photo, get_session
from ..storage import get_storage
from ..storage.base import KeyNotFound

THUMB_SIZE = (400, 400)
THUMB_QUALITY = 85


def _make_thumb(src_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(src_bytes))
    img = ImageOps.exif_transpose(img)
    img.thumbnail(THUMB_SIZE)
    img = img.convert("RGB")
    out = io.BytesIO()
    img.save(out, "JPEG", quality=THUMB_QUALITY)
    return out.getvalue()


def run_thumb(reindex: bool = False, limit: int | None = None) -> int:
    storage = get_storage()

    with get_session() as session:
        stmt = select(Photo.id, Photo.storage_path).where(
            Photo.scan_indexed_at.is_not(None)
        )
        if limit is not None and limit > 0:
            stmt = stmt.limit(limit)
        rows = session.execute(stmt).all()

    generated = skipped = already_exists = transient_errors = 0

    for row in rows:
        thumb_key = f"thumbs/{row.id}.jpg"

        if not reindex and storage.exists(thumb_key):
            already_exists += 1
            continue

        try:
            src_bytes = storage.read_bytes(row.storage_path)
        except KeyNotFound:
            print(f"  missing: {row.storage_path} — skip")
            skipped += 1
            continue
        except Exception as e:
            print(f"  TRANSIENT read error {row.id}: {type(e).__name__}: {e}")
            transient_errors += 1
            continue

        # Decode + thumbnail (deterministic on the bytes — permanent skip on failure).
        try:
            thumb_bytes = _make_thumb(src_bytes)
        except Exception as e:
            print(f"  decode error {row.id}: {type(e).__name__}: {e}")
            skipped += 1
            continue

        # Write (storage-side — transient).
        try:
            storage.write_bytes(thumb_key, thumb_bytes, "image/jpeg")
            generated += 1
        except Exception as e:
            print(f"  TRANSIENT write error {row.id}: {type(e).__name__}: {e}")
            transient_errors += 1

    print(
        f"thumb: {generated} generated, {already_exists} cached, "
        f"{skipped} skipped, {transient_errors} transient (re-run to retry)"
    )
    return generated
