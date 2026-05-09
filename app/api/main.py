import os
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps

from ..config import get_settings
from ..db import get_conn, init_schema, row_to_dict
from ..search.query import search as do_search


def _validate_iso_date(value: str | None, field: str) -> str | None:
    if value is None or value == "":
        return None
    try:
        date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"invalid {field}: expected YYYY-MM-DD")
    return value

app = FastAPI(title="Family Photos")

_WEB_DIR = Path(__file__).parent.parent / "web"
_DIST_DIR = _WEB_DIR / "dist"


@app.on_event("startup")
def startup():
    conn = get_conn()
    init_schema(conn)
    conn.close()
    get_settings().thumbs_path.mkdir(parents=True, exist_ok=True)


@app.get("/people")
def people_endpoint():
    return [{"id": p.id, "name": p.name} for p in get_settings().people]


@app.get("/search")
def search_endpoint(
    q: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    person_id: list[str] = Query(default=[]),
    people_mode: str = Query("any"),
    include_docs: bool = Query(False),
):
    lo = _validate_iso_date(date_from, "date_from")
    hi = _validate_iso_date(date_to, "date_to")
    if people_mode not in ("any", "all"):
        raise HTTPException(status_code=400, detail="people_mode must be 'any' or 'all'")
    results, has_more = do_search(
        q,
        limit=limit,
        offset=offset,
        date_from=lo,
        date_to=hi,
        person_ids=person_id or None,
        people_mode=people_mode,
        include_docs=include_docs,
    )
    return {
        "results": [
            {
                "id": r.id,
                "caption": r.caption,
                "taken_at": r.taken_at,
                "thumb_url": f"/thumb/{r.id}",
                "score": r.score,
                "location_name": r.location_name,
                "tags": r.tags or [],
                "people": r.people or [],
                "activities": r.activities or [],
                "content_type": r.content_type,
                "subject_type": r.subject_type,
                "setting_type": r.setting_type,
                "sharpness": r.sharpness,
                "face_clarity_score": r.face_clarity_score,
                "primary_focus": r.primary_focus,
                "indoor_outdoor": r.indoor_outdoor,
            }
            for r in results
        ],
        "has_more": has_more,
    }


@app.get("/thumb/{photo_id}")
def thumb(photo_id: str):
    storage_path = _resolve_photo_path(photo_id)
    settings = get_settings()
    thumb_path = settings.thumbs_path / f"{photo_id}.jpg"

    if not thumb_path.exists():
        _generate_thumb(storage_path, thumb_path)

    return FileResponse(str(thumb_path), media_type="image/jpeg")


@app.get("/photo/{photo_id}/info")
def photo_info(photo_id: str):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM photos WHERE id = ?", (photo_id,)
    ).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Photo not found")

    data = row_to_dict(row)

    pp_rows = conn.execute(
        """
        SELECT p.id, p.name
        FROM photo_people pp
        JOIN people p ON p.id = pp.person_id
        WHERE pp.photo_id = ?
        """,
        (photo_id,),
    ).fetchall()
    conn.close()

    return {
        "id": photo_id,
        "caption": data.get("caption"),
        "taken_at": data.get("taken_at"),
        "location_name": data.get("location_name"),
        "description": data.get("description"),
        "tags": data.get("tags") or [],
        "people": [{"id": r["id"], "name": r["name"]} for r in pp_rows],
        "activities": data.get("activities") or [],
        "content_type": data.get("content_type"),
        "subject_type": data.get("subject_type"),
        "primary_focus": data.get("primary_focus"),
        "indoor_outdoor": data.get("indoor_outdoor"),
        "setting_type": data.get("setting_type"),
        "sharpness": data.get("sharpness"),
        "face_clarity_score": data.get("face_clarity_score"),
    }


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

    if real_storage != real_photos and real_photos not in real_storage.parents:
        raise HTTPException(status_code=403, detail="Access denied")

    if not storage.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    return storage


def _generate_thumb(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    img = Image.open(src)
    img = ImageOps.exif_transpose(img)
    img.thumbnail((400, 400))
    img = img.convert("RGB")
    img.save(str(dest), "JPEG", quality=85)


app.mount("/static", StaticFiles(directory=str(_DIST_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(str(_DIST_DIR / "index.html"))


@app.get("/games")
def games_route():
    return FileResponse(str(_DIST_DIR / "index.html"))
