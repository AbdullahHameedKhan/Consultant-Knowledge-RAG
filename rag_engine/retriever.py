"""Retriever: embed queries/chunks via Ollama and run similarity search."""
import logging
import re
from dataclasses import dataclass

from ollama import AsyncClient

from rag_engine.config import settings
from rag_engine.data_loader import DocumentChunk
from rag_engine.vector_store import similarity_search, upsert_chunks

logger = logging.getLogger(__name__)


@dataclass
class SourceContext:
    source_file: str
    page_label: str
    text: str
    score: float


def _embed_client() -> AsyncClient:
    headers = None
    token = settings.embed_api_key or settings.ollama_api_key
    if token:
        headers = {"Authorization": f"Bearer {token}"}
    return AsyncClient(host=settings.embed_base_url, headers=headers)


async def _embed(texts: list[str]) -> list[list[float]]:
    """Generate embeddings using configured embedding endpoint/model."""
    client = _embed_client()
    vectors: list[list[float]] = []
    for text in texts:
        resp = await client.embeddings(model=settings.embed_model, prompt=text)
        vectors.append(resp["embedding"])
    return vectors


async def embed_and_store(chunks: list[DocumentChunk]) -> None:
    """Embed chunks in batches and upsert into Qdrant."""
    if not chunks:
        return

    BATCH = 16
    for i in range(0, len(chunks), BATCH):
        batch = chunks[i : i + BATCH]
        texts = [c.text for c in batch]
        logger.info(
            "Embedding batch %d/%d (%d chunks)",
            i // BATCH + 1,
            -(-len(chunks) // BATCH),
            len(batch),
        )
        embeddings = await _embed(texts)
        await upsert_chunks(batch, embeddings)


def _tokenize(text: str) -> set[str]:
    # Replace punctuation (including underscores) with spaces, lowercase it, and split
    clean_text = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    tokens = {t for t in clean_text.split() if len(t) > 2}
    
    # Add a concatenated version of the whole string to catch "media x" == "mediax"
    no_space_text = re.sub(r"\s+", "", clean_text)
    if len(no_space_text) > 2:
        tokens.add(no_space_text)
        
    return tokens


def _hybrid_score(query_tokens: set[str], result: dict) -> float:
    vector_score = float(result.get("score", 0.0))
    text_tokens = _tokenize(result.get("text", ""))
    filename_tokens = _tokenize(result.get("source_file", ""))

    text_overlap = len(query_tokens & text_tokens) / max(1, len(query_tokens))
    
    # Give a massive boost if the query explicitly mentions words in the filename
    filename_overlap = len(query_tokens & filename_tokens) / max(1, len(query_tokens))
    filename_boost = 1.5 if filename_overlap > 0 else 0.0

    return round(vector_score + 0.25 * text_overlap + filename_boost, 4)


def _rerank(query: str, results: list[dict], top_k: int) -> list[dict]:
    if not results:
        return []
    query_tokens = _tokenize(query)
    scored = []
    for r in results:
        item = dict(r)
        item["hybrid_score"] = _hybrid_score(query_tokens, r)
        scored.append(item)
        
    scored.sort(key=lambda x: x.get("hybrid_score", 0.0), reverse=True)
    
    # If the top result has a strong filename match, filter out unrelated documents
    if scored and scored[0]["hybrid_score"] > 1.0:
        top_doc = scored[0]["source_file"]
        scored = [s for s in scored if s["source_file"] == top_doc or s["hybrid_score"] > 1.0]

    return scored[:top_k]



async def retrieve(query: str, top_k: int | None = None) -> list[SourceContext]:
    try:
        query_vectors = await _embed([query])
    except Exception as exc:
        logger.exception(
            "Query embedding failed via %s (model=%s): %s",
            settings.embed_base_url,
            settings.embed_model,
            exc,
        )
        raise

    if not query_vectors:
        return []

    k = top_k or settings.top_k
    initial_results = await similarity_search(
        query_vector=query_vectors[0],
        top_k=max(k * 4, 12),
        score_threshold=settings.similarity_threshold,
    )

    raw_results = initial_results
    if len(initial_results) < min(3, k):
        fallback_results = await similarity_search(
            query_vector=query_vectors[0],
            top_k=max(k * 4, 12),
            score_threshold=0.0,
        )
        raw_results = fallback_results if fallback_results else initial_results

    reranked = _rerank(query, raw_results, k)

    return [
        SourceContext(
            source_file=r.get("source_file", "unknown"),
            page_label=r.get("page_label", ""),
            text=r.get("text", ""),
            score=r.get("hybrid_score", r.get("score", 0.0)),
        )
        for r in reranked
    ]
