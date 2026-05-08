from dataclasses import dataclass
from datetime import datetime


@dataclass
class Photo:
    id: str
    storage_path: str
    original_filename: str
    taken_at: datetime | None
    location_name: str | None
    lat: float | None
    lng: float | None
    caption: str | None
    tags: list[str] | None
    scan_indexed_at: datetime | None
    caption_indexed_at: datetime | None
    vector_indexed_at: datetime | None


@dataclass
class SearchResult:
    id: str
    caption: str | None
    taken_at: datetime | None
    storage_path: str
    score: float
    location_name: str | None = None
    tags: list[str] | None = None
    people: list[dict] | None = None
    activities: list[str] | None = None
    content_type: str | None = None
    subject_type: str | None = None
    setting_type: str | None = None
    sharpness: str | None = None
    face_clarity_score: int | None = None
    primary_focus: str | None = None
    indoor_outdoor: str | None = None
