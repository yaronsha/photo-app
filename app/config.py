import json
import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, model_validator

# Load env file only when ENV_FILE is explicitly set — no implicit .env fallback.
_env_file = os.environ.get("ENV_FILE")
if _env_file:
    _env_path = Path(__file__).parent.parent / _env_file
    load_dotenv(dotenv_path=_env_path, override=False)

_CONFIG_PATH = Path(__file__).parent.parent / "config.json"


class Person(BaseModel):
    id: str
    name: str
    family_id: str | None = None


class Settings(BaseModel):
    # Ignore deprecated keys (e.g. legacy `photos_dir`) instead of failing.
    model_config = ConfigDict(extra="ignore")

    family_name: str
    data_dir: Path
    caption_model: str = "gpt-4o"
    embed_model: str = "text-embedding-3-small"
    face_tolerance: float = 0.5
    storage_backend: str = "local"
    people: list[Person] = []
    google_name_aliases: dict[str, str] = {}
    openai_api_key: str = ""

    @model_validator(mode="after")
    def resolve_paths(self) -> "Settings":
        base = _CONFIG_PATH.parent
        if not self.data_dir.is_absolute():
            self.data_dir = (base / self.data_dir).resolve()
        return self

    @property
    def db_path(self) -> Path:
        return self.data_dir / "photos.db"

    @property
    def chroma_path(self) -> Path:
        return self.data_dir / "chroma"

    @property
    def thumbs_path(self) -> Path:
        return self.data_dir / "thumbs"

    @property
    def anchors_path(self) -> Path:
        return self.data_dir / "anchors"


def load_settings() -> Settings:
    raw = json.loads(_CONFIG_PATH.read_text())
    return Settings(**raw, openai_api_key=os.environ.get("OPENAI_API_KEY", ""))


def require_openai_key(settings: Settings) -> str:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY not set — add to .env or environment")
    return settings.openai_api_key


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings
