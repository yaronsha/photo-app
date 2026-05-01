import base64
import io
import json
import time
from pathlib import Path

from openai import AsyncOpenAI, OpenAI
from PIL import Image

from ...config import get_settings

_async_client: AsyncOpenAI | None = None
_sync_client: OpenAI | None = None


def _get_async_client() -> AsyncOpenAI:
    global _async_client
    if _async_client is None:
        _async_client = AsyncOpenAI(api_key=get_settings().openai_api_key)
    return _async_client


def _get_sync_client() -> OpenAI:
    global _sync_client
    if _sync_client is None:
        _sync_client = OpenAI(api_key=get_settings().openai_api_key)
    return _sync_client


MAX_SIDE = 512


def _resize(data: bytes) -> tuple[bytes, str]:
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85)
    return out.getvalue(), "image/jpeg"


PHOTO_ATTRIBUTES_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "caption",
        "tags",
        "activities",
        "content_type",
        "subject_type",
        "primary_focus",
        "indoor_outdoor",
        "setting_type",
        "sharpness",
        "face_clarity_score",
    ],
    "properties": {
        "caption": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
        "activities": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
        "content_type": {"enum": ["photo", "document", "other"]},
        "subject_type": {
            "enum": [
                "portrait",
                "group",
                "candid_people",
                "landscape",
                "cityscape",
                "food",
                "object",
                "pet",
                "mixed",
                "other",
                "unclear",
            ]
        },
        "primary_focus": {"enum": ["people", "place", "object", "activity", "unclear"]},
        "indoor_outdoor": {"enum": ["indoor", "outdoor", "mixed", "unclear"]},
        "setting_type": {
            "enum": [
                "domestic_interior",
                "restaurant_cafe",
                "nature",
                "beach",
                "urban_street",
                "landmark",
                "event_venue",
                "vehicle",
                "workplace",
                "other",
                "unclear",
            ]
        },
        "sharpness": {"enum": ["sharp", "slightly_blurry", "very_blurry"]},
        "face_clarity_score": {
            "type": ["integer", "null"],
            "minimum": 1,
            "maximum": 5,
        },
    },
}


_PROMPT_TEMPLATE = (
    "You are tagging a family photo. Be conservative — when unsure, use "
    '"unclear" / "other" / null / empty list.\n'
    "{location_line}"
    "Rules:\n"
    "- caption: one descriptive sentence. Do NOT name people. If content_type=document, "
    "briefly say what kind (receipt, screenshot, scan, etc.).\n"
    "- tags: <=8 short scene/object/mood words. No names. No action verbs.\n"
    "- activities: visible ongoing actions as verbs only (dancing, eating, swimming). "
    "Empty list if posed or no clear action.\n"
    "- face_clarity_score: 1-5 only when faces visible. null otherwise.\n"
    '- Prefer "unclear" / "other" over guessing.'
)


class OpenAIProvider:
    async def caption(self, image_path: Path, location_hint: str | None = None) -> dict:
        raw = image_path.read_bytes()
        data, mime = _resize(raw)
        b64 = base64.b64encode(data).decode()

        location_line = (
            f"Location hint: {location_hint}. If you can identify the specific place, "
            f"mention it in the caption.\n"
            if location_hint
            else ""
        )
        prompt = _PROMPT_TEMPLATE.format(location_line=location_line)

        model = get_settings().caption_model
        t0 = time.monotonic()
        resp = await _get_async_client().chat.completions.create(
            model=model,
            temperature=0,
            max_tokens=400,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "photo_attributes",
                    "strict": True,
                    "schema": PHOTO_ATTRIBUTES_SCHEMA,
                },
            },
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime};base64,{b64}",
                                "detail": "low",
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        elapsed = time.monotonic() - t0
        usage = resp.usage
        print(
            f"  [{elapsed:.1f}s] {image_path.name}"
            + (f" | loc: {location_hint}" if location_hint else "")
            + (
                f" | tokens in={usage.prompt_tokens} out={usage.completion_tokens}"
                if usage
                else ""
            )
        )

        text = resp.choices[0].message.content or "{}"
        return json.loads(text)

    def embed(self, text: str) -> list[float]:
        model = get_settings().embed_model
        resp = _get_sync_client().embeddings.create(model=model, input=text)
        return resp.data[0].embedding
