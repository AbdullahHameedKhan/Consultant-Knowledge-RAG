"""Services layer — orchestrates rag_engine calls for FastAPI routes."""
import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path

from ollama import AsyncClient

from fastapi_app.schemas import (
    FeedbackRequest, FeedbackResponse,
    IngestResponse, KnowledgeBaseStatus,
    QueryRequest, QueryResponse, SourceContextSchema,
    HealthResponse,
)
from rag_engine import (
    collection_count, embed_and_store, ensure_collection,
    generate_answer, load_documents, retrieve, settings,
)
from rag_engine.generator import stream_answer, _extract_content

logger = logging.getLogger(__name__)

# In-memory hash cache (persists for process lifetime)
_processed_hashes: dict[str, str] = {}
_feedback_log: list[dict] = []


async def ingest_documents(force_reload: bool = False) -> IngestResponse:
    global _processed_hashes

    await ensure_collection()
    hashes = {} if force_reload else _processed_hashes

    new_chunks, updated_hashes = load_documents(hashes)
    _processed_hashes = updated_hashes

    await embed_and_store(new_chunks)

    total = await collection_count()
    return IngestResponse(
        status="ok",
        files_processed=len({c.source_file for c in new_chunks}),
        chunks_added=len(new_chunks),
        total_vectors=total,
    )


async def _classify_query(question: str) -> bool:
    """Uses only the router agent to classify generic (True) vs factual (False)."""
    try:
        headers = None
        if settings.ollama_api_key:
            headers = {"Authorization": f"Bearer {settings.ollama_api_key}"}
        client = AsyncClient(host=settings.ollama_base_url, headers=headers)

        prompt = (
            "You are a strict query router.\n"
            "Classify the input into exactly one label:\n"
            "- GENERIC: greeting, small talk, identity/capabilities, or conversational messages that do not require document facts.\n"
            "- FACTUAL: questions that require knowledge retrieval from the knowledge base.\n"
            "Output exactly one token: GENERIC or FACTUAL.\n"
            f"User input: {question}"
        )

        resp = await client.chat(
            model=settings.model_name,
            messages=[{"role": "system", "content": "Return only GENERIC or FACTUAL."}, {"role": "user", "content": prompt}],
            options={"temperature": 0.0, "num_predict": 5},
        )

        content = (_extract_content(resp) or "").strip().upper()
        if content.startswith("GENERIC"):
            return True
        if content.startswith("FACTUAL"):
            return False

        logger.warning("Unexpected router output '%s', defaulting to factual RAG", content)
        return False
    except Exception as e:
        logger.warning("Router failed, defaulting to factual RAG: %s", e)
        return False


async def query_knowledge_base_stream(req: QueryRequest) -> AsyncIterator[str]:
    # Route query dynamically
    is_generic = await _classify_query(req.question)

    if is_generic:
        async for chunk in stream_answer(req.question, []):
            yield json.dumps({"type": "chunk", "content": chunk}) + "\n"
            
        yield json.dumps({
            "type": "meta",
            "sources": [],
            "model_used": settings.model_name,
            "chunks_retrieved": 0,
        }) + "\n"
        return

    source_schemas: list[SourceContextSchema] = []
    try:
        sources = await retrieve(req.question, top_k=req.top_k)
        source_schemas = [
            SourceContextSchema(
                source_file=s.source_file,
                page_label=s.page_label,
                relevance_score=s.score,
                excerpt=s.text[:300].strip(),
            )
            for s in sources[: settings.generation_top_k]
        ]

        async for chunk in stream_answer(req.question, sources):
            yield json.dumps({"type": "chunk", "content": chunk}) + "\n"

        yield json.dumps(
            {
                "type": "meta",
                "sources": [s.model_dump() for s in source_schemas],
                "model_used": settings.model_name,
                "chunks_retrieved": len(source_schemas),
            }
        ) + "\n"
    except Exception as exc:
        logger.exception("Streaming pipeline failed: %s", exc)
        yield json.dumps(
            {
                "type": "error",
                "content": "Backend streaming failed. Check FastAPI logs for details.",
            }
        ) + "\n"
        yield json.dumps(
            {
                "type": "meta",
                "sources": [s.model_dump() for s in source_schemas],
                "model_used": settings.model_name,
                "chunks_retrieved": len(source_schemas),
            }
        ) + "\n"


async def get_kb_status() -> KnowledgeBaseStatus:
    total = await collection_count()
    return KnowledgeBaseStatus(
        total_vectors=total,
        document_dir=settings.document_dir,
        embed_model=settings.embed_model,
        llm_model=settings.model_name,
        collection_name=settings.qdrant_collection,
    )


async def log_feedback(req: FeedbackRequest) -> FeedbackResponse:
    entry = req.model_dump()
    _feedback_log.append(entry)

    log_path = Path("feedback_log.jsonl")
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    logger.info("Feedback logged: rating=%d", req.rating)
    return FeedbackResponse(status="ok", message="Feedback recorded. Thank you!")


async def check_health() -> HealthResponse:
    ollama_ok = False
    try:
        headers = None
        if settings.ollama_api_key:
            headers = {"Authorization": f"Bearer {settings.ollama_api_key}"}
        client = AsyncClient(host=settings.ollama_base_url, headers=headers)
        models_resp = await client.list()
        ollama_ok = bool(models_resp)
    except Exception:
        pass

    qdrant_ok = False
    try:
        count = await collection_count()
        qdrant_ok = count >= 0
    except Exception:
        pass

    return HealthResponse(
        status="ok" if ollama_ok else "degraded",
        ollama_reachable=ollama_ok,
        qdrant_ready=qdrant_ok,
    )
