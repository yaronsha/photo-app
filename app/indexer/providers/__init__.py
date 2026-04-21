from ...config import get_settings, require_openai_key
from .openai import OpenAIProvider


def get_caption_provider():
    require_openai_key(get_settings())
    return OpenAIProvider()


def get_embed_provider():
    require_openai_key(get_settings())
    return OpenAIProvider()
