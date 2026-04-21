import base64
from pathlib import Path

from openai import OpenAI

from ...config import get_settings

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=get_settings().openai_api_key)
    return _client


class OpenAIProvider:
    def caption(self, image_path: Path) -> dict:
        data = image_path.read_bytes()
        b64 = base64.b64encode(data).decode()
        ext = image_path.suffix.lower().lstrip(".")
        mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"

        model = get_settings().caption_model
        resp = _get_client().chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}"},
                        },
                        {
                            "type": "text",
                            "text": (
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
        text = resp.choices[0].message.content or ""
        return _parse_caption_response(text)

    def embed(self, text: str) -> list[float]:
        model = get_settings().embed_model
        resp = _get_client().embeddings.create(model=model, input=text)
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
