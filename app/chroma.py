import chromadb

from .config import get_settings

COLLECTION_NAME = "photos"
_client: chromadb.PersistentClient | None = None
_collection: chromadb.Collection | None = None


def get_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        settings = get_settings()
        settings.chroma_path.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(settings.chroma_path))
    return _client


def get_collection() -> chromadb.Collection:
    global _collection
    if _collection is None:
        client = get_client()
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def assert_embed_model(model: str) -> None:
    col = get_collection()
    stored = col.metadata.get("embed_model") if col.metadata else None
    if stored is None:
        col.modify(metadata={"embed_model": model})
    elif stored != model:
        raise RuntimeError(
            f"Corpus embed model mismatch: stored={stored!r}, requested={model!r}. "
            "Delete data/chroma/ to start fresh or use the same model."
        )
