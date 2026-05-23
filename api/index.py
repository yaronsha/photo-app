# Vercel Python entry point. Vercel auto-detects the ASGI `app` and serves it.
# All routes (frontend static, /search, /photo, /thumb, /people, /api/*) are
# handled by this single FastAPI app — see vercel.json rewrites.
from app.api.main import app

__all__ = ["app"]
