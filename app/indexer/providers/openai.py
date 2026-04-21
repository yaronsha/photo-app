import asyncio
import base64
import io
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


class OpenAIProvider:
    async def caption(self, image_path: Path, location_hint: str | None = None) -> dict:
        raw = image_path.read_bytes()
        data, mime = _resize(raw)
        b64 = base64.b64encode(data).decode()

        location_line = (
            f"Location hint: {location_hint}. If you can identify the specific place, mention it in the caption.\n"
            if location_hint else ""
        )

        model = get_settings().caption_model
        t0 = time.monotonic()
        resp = await _get_async_client().chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "low"},
                        },
                        {
                            "type": "text",
                            "text": (
                                f"{location_line}"
                                "Describe this photo in one clear, descriptive sentence. "
                                "Then list up to 8 tags (comma-separated) that describe the scene, "
                                "setting, activity, mood, and objects — do NOT include people's names. "
                                "Format:\nCaption: <sentence>\nTags: <tag1>, <tag2>, ..."
                            ),
                        },
                    ],
                }
            ],
            max_tokens=256,
        )
        elapsed = time.monotonic() - t0
        usage = resp.usage
        print(
            f"  [{elapsed:.1f}s] {image_path.name}"
            + (f" | loc: {location_hint}" if location_hint else "")
            + (f" | tokens in={usage.prompt_tokens} out={usage.completion_tokens}" if usage else "")
        )

        text = resp.choices[0].message.content or ""
        return _parse_caption_response(text)


    def embed(self, text: str) -> list[float]:
        model = get_settings().embed_model
        resp = _get_sync_client().embeddings.create(model=model, input=text)
        return resp.data[0].embedding


def _parse_caption_response(text: str) -> dict:
    caption = ""
    tags: list[str] = []
    for line in text.strip().splitlines():
        if line.lower().startswith("caption:"):
            caption = line.split(":", 1)[1].strip()
        elif line.lower().startswith("tags:"):
            raw = line.split(":", 1)[1].strip()
            tags = [t.strip() for t in raw.split(",") if t.strip()]
    if not caption:
        caption = text.strip().splitlines()[0] if text.strip() else ""
    return {"caption": caption, "tags": tags[:8]}
