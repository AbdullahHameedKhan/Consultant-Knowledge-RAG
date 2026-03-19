"""Generator: build grounded prompts and stream/call Kimi via Ollama."""
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass

from ollama import AsyncClient

from rag_engine.config import settings
from rag_engine.retriever import SourceContext

logger = logging.getLogger(__name__)

_STREAM_UNSUPPORTED = False

_SYSTEM_PROMPT = """You are a helpful, professional management consultant assistant.

If the user is simply greeting you (e.g., "hello", "hi") or asking about your identity/capabilities (e.g., "who are you", "what can you do"), respond naturally and politely in 1-2 sentences. You do not need to use context for these types of questions.

For all other questions, you MUST answer using ONLY the provided context excerpts.

STRICT RULES FOR FACTUAL QUESTIONS:
- DO NOT show your internal thought process.
- DO NOT start with "Based on the context" or "The user is asking".
- DO NOT use phrases like "Based on the provided context".
- DO NOT provide a draft or analysis.
- START your response immediately with the facts.

Output rules:
- Return only the final answer. Do not include analysis, deliberation, or drafting notes.
- Keep answers short, direct, and in the same order as requested.
- Use clear bullets or numbered steps when the user asks for process/steps.
- Do not repeat the question.
- Do not mention scoring, retrieval mechanics, or missing metadata unless explicitly asked.

Grounding rules:
- Do not fabricate facts, numbers, or steps.
- If the question requires knowledge from the documents but the context is insufficient, say: "I don't have enough information in the knowledge base to answer this confidently."
"""



_USER_TEMPLATE = """Context Excerpts:
{context_block}

---
User Question: {question}

Return a concise final answer only, grounded strictly in the context above, with inline citations."""


@dataclass
class GeneratedAnswer:
    answer: str
    sources: list[SourceContext]
    model_used: str


def _build_context_block(sources: list[SourceContext]) -> str:
    blocks: list[str] = []
    for i, src in enumerate(sources, 1):
        excerpt = src.text.strip()[: settings.max_source_chars]
        blocks.append(
            f"[{i}] Source: {src.source_file} | {src.page_label} | Score: {src.score}\n"
            f"{excerpt}"
        )
    return "\n\n".join(blocks)


def _client() -> AsyncClient:
    headers = None
    if settings.ollama_api_key:
        headers = {"Authorization": f"Bearer {settings.ollama_api_key}"}
    return AsyncClient(host=settings.ollama_base_url, headers=headers)


def _as_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(_as_text(v) for v in value)
    if isinstance(value, dict):
        # Dynamically ignore the "thinking" field by excluding it here
        for key in ("content", "text", "response", "delta"):
            text = _as_text(value.get(key))
            if text:
                return text
    if hasattr(value, "model_dump"):
        return _as_text(value.model_dump())
    return ""


def _extract_content(part: object) -> str:
    payload = part if isinstance(part, dict) else None
    if payload is None and hasattr(part, "model_dump"):
        payload = part.model_dump()

    if isinstance(payload, dict):
        # Dynamically ignore the "thinking" field by excluding it here
        for key in ("message", "content", "response", "delta", "text"):
            text = _as_text(payload.get(key))
            if text:
                return text

    message = getattr(part, "message", None)
    # Dynamically ignore the "thinking" field by excluding it here
    for value in (
        message,
        getattr(part, "content", None),
        getattr(part, "response", None),
        getattr(part, "delta", None),
        getattr(part, "text", None),
    ):
        text = _as_text(value)
        if text:
            return text

    return ""


async def generate_answer(
    question: str,
    sources: list[SourceContext],
) -> GeneratedAnswer:
    """Call Ollama with grounded context and return a structured answer."""
    if not sources:
        return GeneratedAnswer(
            answer=(
                "No relevant documents found in the knowledge base. "
                "Please ensure reports are ingested and try rephrasing your query."
            ),
            sources=[],
            model_used=settings.model_name,
        )

    selected_sources = sources[: settings.generation_top_k]
    context_block = _build_context_block(selected_sources)
    user_message = _USER_TEMPLATE.format(
        context_block=context_block,
        question=question,
    )

    client = _client()
    response = await client.chat(
        model=settings.model_name,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        options={
            "temperature": 0.1,
            "num_ctx": settings.llm_num_ctx,
            "num_predict": settings.max_output_tokens,
        },
    )

    answer_text = _extract_content(response) or "No response generated."

    logger.info("Generated answer (%d chars).", len(answer_text))

    return GeneratedAnswer(
        answer=answer_text,
        sources=selected_sources,
        model_used=settings.model_name,
    )


async def stream_answer(
    question: str,
    sources: list[SourceContext],
) -> AsyncIterator[str]:
    if not sources:
        # If sources are empty here, it means the router classified it as generic
        context_block = "No context needed for this query."
        user_message = f"User Question: {question}\n\nRespond naturally and politely."
    else:
        selected_sources = sources[: settings.generation_top_k]
        context_block = _build_context_block(selected_sources)
        user_message = _USER_TEMPLATE.format(
            context_block=context_block,
            question=question,
        )

    client = _client()
    global _STREAM_UNSUPPORTED

    if _STREAM_UNSUPPORTED:
        fallback = await client.chat(
            model=settings.model_name,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            options={
                "temperature": 0.1,
                "num_ctx": settings.llm_num_ctx,
                "num_predict": settings.max_output_tokens,
            },
        )
        fallback_text = _extract_content(fallback)
        if fallback_text:
            for i in range(0, len(fallback_text), 120):
                yield fallback_text[i : i + 120]
        return

    stream = await client.chat(
        model=settings.model_name,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        options={
            "temperature": 0.1,
            "num_ctx": settings.llm_num_ctx,
            "num_predict": settings.max_output_tokens,
        },
        stream=True,
    )

    emitted = False
    async for part in stream:
        chunk = _extract_content(part)
        if chunk:
            emitted = True
            yield chunk

    if not emitted:
        _STREAM_UNSUPPORTED = True
        logger.warning("Cloud stream returned no text; switching to pseudo-stream mode.")
        fallback = await client.chat(
            model=settings.model_name,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            options={
                "temperature": 0.1,
                "num_ctx": settings.llm_num_ctx,
                "num_predict": settings.max_output_tokens,
            },
        )
        fallback_text = _extract_content(fallback)
        if fallback_text:
            for i in range(0, len(fallback_text), 120):
                yield fallback_text[i : i + 120]