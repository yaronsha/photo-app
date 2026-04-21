from .openai import OpenAIProvider


def get_caption_provider():
    return OpenAIProvider()


def get_embed_provider():
    return OpenAIProvider()
