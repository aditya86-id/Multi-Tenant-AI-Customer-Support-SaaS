import logging
from dataclasses import dataclass, field

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
    parts = [
        f"[Source {i}]\n{chunk.content}" for i, (chunk, _score) in enumerate(scored_chunks, start=1)
    ]
    return "\n\n".join(parts)


# Escalation is modeled as a real tool the model can choose to call --
# NOT an if/else on the retrieval confidence score. The score is only
# passed in as context for the model's own judgment; it never gates
# whether generate_answer_and_maybe_escalate() is allowed to escalate.
CREATE_TICKET_TOOL = {
    "name": "create_ticket",
    "description": (
        "Open a support ticket so a human agent follows up with the customer. "
        "Call this when the knowledge base sources don't contain enough "
        "information to answer confidently, OR when the customer explicitly "
        "asks to speak with a human. You should still answer the customer's "
        "message as best you can in the same turn -- calling this tool "
        "supplements your answer with human follow-up, it doesn't replace it."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "subject": {
                "type": "string",
                "description": "Short subject line summarizing the customer's issue.",
            },
            "summary": {
                "type": "string",
                "description": (
                    "A few sentences summarizing the customer's question and "
                    "why it needs human follow-up (e.g. missing KB coverage, "
                    "customer explicitly requested a human, account-specific "
                    "issue)."
                ),
            },
            "priority": {
                "type": "string",
                "enum": ["low", "normal", "high", "urgent"],
                "description": "Urgency of the issue as you judge it from the conversation.",
            },
            "escalation_reason": {
                "type": "string",
                "enum": ["low_confidence", "user_requested", "out_of_scope"],
                "description": "Why this needs a human: insufficient KB coverage, the "
                "customer asked for one, or the request is outside what this bot handles.",
            },
        },
        "required": ["subject", "summary", "priority", "escalation_reason"],
    },
}


def _build_system_prompt(context: str, retrieval_confidence: float) -> str:
    return (
        "You are a customer support assistant answering questions using the "
        "knowledge base excerpts provided below. Follow these rules:\n"
        "1. Answer from the provided sources whenever they cover the question. "
        "Do not invent information that isn't in the sources.\n"
        "2. When you use a source, cite it inline like [Source 1], [Source 2].\n"
        "3. You have a create_ticket tool available. Use your own judgment -- "
        "informed by the sources' relevance, not a fixed rule -- to decide "
        "whether this question needs human follow-up. Always give the "
        "customer your best answer in the same turn even if you also open a "
        "ticket.\n"
        "4. If the customer explicitly asks for a human agent, call "
        "create_ticket regardless of how confident your answer is.\n"
        "5. Keep answers concise and directly useful to the customer.\n\n"
        f"(Internal signal, not shown to the customer: automated retrieval "
        f"similarity for this query was {retrieval_confidence:.2f} on a 0-1 "
        f"scale. Treat this as one input among several, not a hard rule.)\n\n"
        f"--- Knowledge base excerpts ---\n{context}"
    )


@dataclass
class AnswerResult:
    answer: str
    escalated: bool = False
    ticket_subject: str | None = None
    ticket_summary: str | None = None
    ticket_priority: str = "normal"
    escalation_reason: str | None = None
    raw_tool_inputs: dict = field(default_factory=dict)


def generate_answer_and_maybe_escalate(
    query: str, scored_chunks: list[tuple[Chunk, float]], retrieval_confidence: float
) -> AnswerResult:
    """
    Single Claude call that both answers the customer and decides -- via real
    tool use, not a similarity threshold -- whether to escalate. Escalation
    happens ALONGSIDE the answer: the model is instructed to always attempt
    an answer even when it also opens a ticket, so the customer is never
    left with silence while waiting on a human.
    """
    client = _get_client()
    context = build_context_block(scored_chunks)
    system_prompt = _build_system_prompt(context, retrieval_confidence)

    try:
        response = client.messages.create(
            model=ANSWER_MODEL,
            max_tokens=1024,
            system=system_prompt,
            tools=[CREATE_TICKET_TOOL],
            messages=[{"role": "user", "content": query}],
        )
    except Exception as exc:  # noqa: BLE001 -- surfaced to the caller as AnswerGenerationError
        logger.exception("generate_answer_and_maybe_escalate: Anthropic call failed")
        raise AnswerGenerationError(f"Failed to generate an answer: {exc}") from exc

    text_blocks = [block.text for block in response.content if block.type == "text"]
    answer = "\n".join(text_blocks).strip()

    tool_call = next(
        (block for block in response.content if block.type == "tool_use" and block.name == "create_ticket"),
        None,
    )

    if tool_call is None:
        return AnswerResult(answer=answer)

    tool_input = tool_call.input or {}

    if not answer:
        # The model escalated without producing any customer-facing text --
        # still guarantee the customer gets something rather than silence.
        answer = (
            "I've opened a support ticket so a member of our team can help "
            "you with this directly."
        )

    return AnswerResult(
        answer=answer,
        escalated=True,
        ticket_subject=tool_input.get("subject", "Customer support request"),
        ticket_summary=tool_input.get("summary", query[:500]),
        ticket_priority=tool_input.get("priority", "normal"),
        escalation_reason=tool_input.get("escalation_reason", "low_confidence"),
        raw_tool_inputs=tool_input,
    )
