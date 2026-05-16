"""Pre-generate thumbnails for all indexed photos and store via storage backend."""
import io

from PIL import Image, ImageOps
from sqlalchemy import select

from ..db import Photo, get_session
from ..storage import get_storage

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

    generated = skipped = already_exists = 0

    for row in rows:
        thumb_key = f"thumbs/{row.id}.jpg"

        if not reindex and storage.exists(thumb_key):
            already_exists += 1
            continue

        try:
            src_bytes = storage.read_bytes(row.storage_path)
        except FileNotFoundError:
            print(f"  missing: {row.storage_path} — skip")
            skipped += 1
            continue
        except Exception as e:
            print(f"  read error {row.id}: {e}")
            skipped += 1
            continue

        try:
            thumb_bytes = _make_thumb(src_bytes)
            storage.write_bytes(thumb_key, thumb_bytes, "image/jpeg")
            generated += 1
        except Exception as e:
            print(f"  thumb error {row.id}: {e}")
            skipped += 1

    print(f"thumb: {generated} generated, {already_exists} cached, {skipped} errors")
    return generated
