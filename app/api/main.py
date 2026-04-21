import io
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

from ..config import get_settings
from ..db import get_conn, init_schema
from ..search.query import search as do_search

app = FastAPI(title="Family Photos")

_WEB_DIR = Path(__file__).parent.parent / "web"


@app.on_event("startup")
def startup():
    conn = get_conn()
    init_schema(conn)
    conn.close()
    get_settings().thumbs_path.mkdir(parents=True, exist_ok=True)


@app.get("/search")
def search_endpoint(
    q: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=200),
    year_from: int | None = Query(None),
    year_to: int | None = Query(None),
):
    results = do_search(q, limit=limit, year_from=year_from, year_to=year_to)
    return {
        "results": [
            {
                "id": r.id,
                "caption": r.caption,
                "taken_at": r.taken_at,
                "thumb_url": f"/thumb/{r.id}",
                "score": r.score,
            }
            for r in results
        ]
    }


@app.get("/thumb/{photo_id}")
def thumb(photo_id: str):
    settings = get_settings()
    thumb_path = settings.thumbs_path / f"{photo_id}.jpg"

    if not thumb_path.exists():
        storage_path = _resolve_photo_path(photo_id)
        _generate_thumb(storage_path, thumb_path)

    return FileResponse(str(thumb_path), media_type="image/jpeg")


@app.get("/photo/{photo_id}")
def photo(photo_id: str):
    storage_path = _resolve_photo_path(photo_id)
    suffix = storage_path.suffix.lower()
    media_type = "image/jpeg" if suffix in (".jpg", ".jpeg") else f"image/{suffix.lstrip('.')}"
    return FileResponse(str(storage_path), media_type=media_type)


def _resolve_photo_path(photo_id: str) -> Path:
    conn = get_conn()
    row = conn.execute(
        "SELECT storage_path FROM photos WHERE id = ?", (photo_id,)
    ).fetchone()
    conn.close()

    if row is None:
        raise HTTPException(status_code=404, detail="Photo not found")

    settings = get_settings()
    storage = Path(row["storage_path"])
    real_storage = Path(os.path.realpath(storage))
    real_photos = Path(os.path.realpath(settings.photos_dir))

    if not str(real_storage).startswith(str(real_photos)):
        raise HTTPException(status_code=403, detail="Access denied")

    if not storage.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    return storage


def _generate_thumb(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    img = Image.open(src)
    img.thumbnail((400, 400))
    img = img.convert("RGB")
    img.save(str(dest), "JPEG", quality=85)


app.mount("/static", StaticFiles(directory=str(_WEB_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(str(_WEB_DIR / "index.html"))
