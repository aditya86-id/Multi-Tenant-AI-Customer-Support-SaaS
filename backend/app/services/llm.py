import logging

import anthropic

from app.core.config import get_settings
from app.models.chunk import Chunk

logger = logging.getLogger("support_saas.llm")
settings = get_settings()

# Pinned to a specific model rather than a generic alias so behavior can't
# shift under you between deploys. Check
# https://docs.claude.com/en/docs/about-claude/models before changing this.
ANSWER_MODEL = "claude-sonnet-5"

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        if not settings.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set -- cannot generate answers. "
                "Set it in your .env file."
            )
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


class AnswerGenerationError(Exception):
    pass


def build_context_block(scored_chunks: list[tuple[Chunk, float]]) -> str:
    if not scored_chunks:
        return "(no knowledge base content is available for this tenant)"
    parts = [f"[Source {i}]\n{chunk.content}" for i, (chunk, _score) in enumerate(scored_chunks, start=1)]
    return "\n\n".join(parts)


SYSTEM_PROMPT = (
    "You are a customer support assistant answering questions using ONLY the "
    "knowledge base excerpts provided below. Follow these rules strictly:\n"
    "1. Answer only from the provided sources. Do not use outside knowledge.\n"
    "2. When you use a source, cite it inline like [Source 1], [Source 2].\n"
    "3. If the sources don't contain enough information to answer confidently, "
    "say so plainly instead of guessing.\n"
    "4. Keep answers concise and directly useful to the customer."
)


def generate_answer(query: str, scored_chunks: list[tuple[Chunk, float]]) -> str:
    """
    Generates a grounded answer from retrieved chunks. This is deliberately
    NOT the agentic escalation flow (phase 4) -- it always returns a plain
    text answer. Deciding whether to escalate instead of, or alongside,
    answering is handled one layer up once Claude tool use is wired in.
    """
    client = _get_client()
    context = build_context_block(scored_chunks)

    try:
        response = client.messages.create(
            model=ANSWER_MODEL,
            max_tokens=1024,
            system=f"{SYSTEM_PROMPT}\n\n--- Knowledge base excerpts ---\n{context}",
            messages=[{"role": "user", "content": query}],
        )
    except Exception as exc:  # noqa: BLE001 -- surfaced to the caller as AnswerGenerationError
        logger.exception("generate_answer: Anthropic call failed")
        raise AnswerGenerationError(f"Failed to generate an answer: {exc}") from exc

    text_blocks = [block.text for block in response.content if block.type == "text"]
    return "\n".join(text_blocks).strip()
