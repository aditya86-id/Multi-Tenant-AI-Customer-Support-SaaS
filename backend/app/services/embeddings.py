import voyageai
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import get_settings

settings = get_settings()

_client: voyageai.Client | None = None


def _get_client() -> voyageai.Client:
    global _client
    if _client is None:
        if not settings.voyage_api_key:
            raise RuntimeError(
                "VOYAGE_API_KEY is not set -- embeddings cannot be generated. "
                "Set it in your .env file."
            )
        _client = voyageai.Client(api_key=settings.voyage_api_key)
    return _client


class EmbeddingError(Exception):
    pass


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=20),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def _embed_batch(texts: list[str], input_type: str) -> list[list[float]]:
    client = _get_client()
    result = client.embed(
        texts,
        model=settings.embedding_model,
        input_type=input_type,
        output_dimension=settings.embedding_dimension,
    )
    return result.embeddings


def embed_documents(texts: list[str]) -> list[list[float]]:
    """
    Embeds a batch of document chunks for storage. Voyage distinguishes
    "document" vs "query" embeddings -- using the right input_type improves
    retrieval quality, so ingestion and querying MUST NOT share one helper
    with a default value that's easy to leave unset by accident.
    """
    if not texts:
        return []
    try:
        return _embed_batch(texts, input_type="document")
    except Exception as exc:  # noqa: BLE001 -- surfaced to the caller as EmbeddingError
        raise EmbeddingError(f"Failed to embed document chunks: {exc}") from exc


def embed_query(text: str) -> list[float]:
    """Embeds a single end-user query for retrieval (phase 3)."""
    try:
        return _embed_batch([text], input_type="query")[0]
    except Exception as exc:  # noqa: BLE001
        raise EmbeddingError(f"Failed to embed query: {exc}") from exc
