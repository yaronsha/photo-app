import io
import os
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps
from sqlalchemy import select

from ..config import get_settings
from ..db import Person, Photo, PhotoPerson, get_session, init_schema
from ..search.query import search as do_search
from ..storage import get_storage
from ..storage.base import KeyNotFound
from .auth import _auth_enabled, require_auth, require_cron


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
_FRONTEND_NOT_BUILT_HTML = (
    "<!doctype html><meta charset=utf-8><title>Frontend not built</title>"
    "<body style='font-family:sans-serif;padding:2rem'>"
    "<h1>Frontend not built</h1>"
    "<p>Run <code>cd app/web && npm install && npm run build</code> "
    "then reload.</p></body>"
)


def _ensure_dist() -> None:
    """Ensure app/web/dist/index.html exists.

    Prod fails loud: if the frontend is not built, raise at import so the
    deploy never silently serves a placeholder. Tests / local dev opt out
    by setting FAMILY_PHOTOS_ALLOW_MISSING_FRONTEND=1, which writes a
    visible "frontend not built" stub instead.
    """
    index = _DIST_DIR / "index.html"
    if index.exists():
        return
    if os.environ.get("FAMILY_PHOTOS_ALLOW_MISSING_FRONTEND") != "1":
        raise RuntimeError(
            f"Frontend not built: {index} missing. "
            "Run `cd app/web && npm install && npm run build`, "
            "or set FAMILY_PHOTOS_ALLOW_MISSING_FRONTEND=1 for dev/test."
        )
    _DIST_DIR.mkdir(parents=True, exist_ok=True)
    index.write_text(_FRONTEND_NOT_BUILT_HTML, encoding="utf-8")


_ensure_dist()


@app.on_event("startup")
def startup():
    init_schema()
    settings = get_settings()
    # Local-dev scratch dirs only. With STORAGE_BACKEND=r2 these are unused,
    # and the host FS may be read-only (e.g. Vercel) — skip to avoid crashing
    # startup on an mkdir against a read-only path.
    if settings.storage_backend == "local":
        (settings.data_dir / "photos").mkdir(parents=True, exist_ok=True)
        (settings.data_dir / "thumbs").mkdir(parents=True, exist_ok=True)


@app.get("/people")
def people_endpoint(_user=Depends(require_auth)):
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
    _user=Depends(require_auth),
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
def thumb(photo_id: str, _user=Depends(require_auth)):
    with get_session() as session:
        db_photo = session.get(Photo, photo_id)

    if db_photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")

    _check_key(db_photo.storage_path)
    storage = get_storage()
    thumb_key = f"thumbs/{photo_id}.jpg"

    try:
        if not storage.exists(thumb_key):
            src_bytes = storage.read_bytes(db_photo.storage_path)
            thumb_bytes = _make_thumb(src_bytes)
            storage.write_bytes(thumb_key, thumb_bytes, "image/jpeg")
        url = storage.presign_get(thumb_key, expires=3600)
        return RedirectResponse(url, status_code=302)
    except KeyNotFound:
        raise HTTPException(status_code=404, detail="Photo bytes not found")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="Storage backend error")


@app.get("/photo/{photo_id}/info")
def photo_info(photo_id: str, _user=Depends(require_auth)):
    with get_session() as session:
        photo = session.get(Photo, photo_id)
        if photo is None:
            raise HTTPException(status_code=404, detail="Photo not found")

        people_rows = session.execute(
            select(Person.id, Person.name)
            .join(PhotoPerson, PhotoPerson.person_id == Person.id)
            .where(PhotoPerson.photo_id == photo_id)
        ).all()

        return {
            "id": photo_id,
            "caption": photo.caption,
            "taken_at": photo.taken_at,
            "location_name": photo.location_name,
            "description": photo.description,
            "tags": photo.tags or [],
            "people": [{"id": pid, "name": pname} for pid, pname in people_rows],
            "activities": photo.activities or [],
            "content_type": photo.content_type,
            "subject_type": photo.subject_type,
            "primary_focus": photo.primary_focus,
            "indoor_outdoor": photo.indoor_outdoor,
            "setting_type": photo.setting_type,
            "sharpness": photo.sharpness,
            "face_clarity_score": photo.face_clarity_score,
        }


@app.get("/photo/{photo_id}")
def photo(photo_id: str, _user=Depends(require_auth)):
    with get_session() as session:
        db_photo = session.get(Photo, photo_id)

    if db_photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")

    key = db_photo.storage_path
    _check_key(key)
    storage = get_storage()
    try:
        if not storage.exists(key):
            raise HTTPException(status_code=404, detail="Photo bytes not found")
        url = storage.presign_get(key, expires=3600)
        return RedirectResponse(url, status_code=302)
    except HTTPException:
        raise
    except KeyNotFound:
        raise HTTPException(status_code=404, detail="Photo bytes not found")
    except Exception:
        raise HTTPException(status_code=502, detail="Storage backend error")


@app.post("/auth/exchange")
def auth_exchange(claims: dict = Depends(require_auth)):
    """Cookie-exchange path (fallback for proxy mode); not used by default
    signed-URL redirect flow but exposed so frontend can opt in.
    """
    return {"ok": True, "email": claims.get("email")}


@app.get("/api/me")
def me(claims: dict = Depends(require_auth)):
    """Return the caller's authenticated identity. Useful for frontend sanity check."""
    return {
        "email": claims.get("email"),
        "sub": claims.get("sub"),
        "auth_enabled": _auth_enabled(),
    }


# `require_cron` is exported here so phase 4 (compute refactor) can attach
# it to `/api/index-batch` without re-importing auth machinery.
__all__ = ["app", "require_cron"]


# storage_path is written by our own indexer, but treat it as untrusted in case
# a row was hand-edited or restored from a stale dump. Reject anything that
# isn't a clean key under the photos/ namespace.
def _check_key(key: str | None) -> None:
    if not key:
        raise HTTPException(status_code=404, detail="Photo not found")
    if not key.startswith("photos/"):
        raise HTTPException(status_code=403, detail="Access denied")
    if ".." in key.split("/"):
        raise HTTPException(status_code=403, detail="Access denied")
    if "\\" in key:
        raise HTTPException(status_code=403, detail="Access denied")


# HEIC originals (merge.py accepts .heic) reach _make_thumb when a thumb is
# generated on demand. Pillow needs the HEIF opener registered to decode them;
# scan.py does this for the indexer, but the API serving path imports neither.
# Best-effort: if pillow-heif is absent, JPEG/PNG thumbs still work.
try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:
    pass


def _make_thumb(src_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(src_bytes))
    img = ImageOps.exif_transpose(img)
    img.thumbnail((400, 400))
    img = img.convert("RGB")
    out = io.BytesIO()
    img.save(out, "JPEG", quality=85)
    return out.getvalue()


app.mount("/static", StaticFiles(directory=str(_DIST_DIR)), name="static")


# Local-dev only: serve files referenced by LocalStorage.presign_get
# (which returns "/local/<key>"). In prod with STORAGE_BACKEND=r2 the
# presign URLs point at R2 directly and this mount is irrelevant.
# Skipped when auth is enabled — /local/ is unauthenticated by design, so
# we refuse to expose it alongside JWT-gated endpoints.
if (
    os.environ.get("STORAGE_BACKEND", "local") == "local"
    and not _auth_enabled()
):
    _local_root = get_settings().data_dir
    _local_root.mkdir(parents=True, exist_ok=True)
    app.mount("/local", StaticFiles(directory=str(_local_root)), name="local")


@app.get("/")
def index():
    return FileResponse(str(_DIST_DIR / "index.html"))


@app.get("/games")
def games_route():
    return FileResponse(str(_DIST_DIR / "index.html"))
