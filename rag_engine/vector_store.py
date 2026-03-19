"""Qdrant in-memory vector store — collection lifecycle and upsert logic."""
import logging
from typing import Any

from qdrant_client import AsyncQdrantClient, models
from qdrant_client.models import Distance, VectorParams, PointStruct

from rag_engine.config import settings
from rag_engine.data_loader import DocumentChunk

logger = logging.getLogger(__name__)

_client: AsyncQdrantClient | None = None


def get_client() -> AsyncQdrantClient:
    global _client
    if _client is None:
        if settings.qdrant_url:
            logger.info("Connecting to Qdrant at %s", settings.qdrant_url)
            _client = AsyncQdrantClient(url=settings.qdrant_url)
        elif settings.qdrant_path:
            logger.info("Using local Qdrant at %s", settings.qdrant_path)
            _client = AsyncQdrantClient(path=settings.qdrant_path)
        else:
            logger.warning("Using in-memory Qdrant (data will be lost on restart)")
            _client = AsyncQdrantClient(location=":memory:")
    return _client


async def ensure_collection() -> None:
    client = get_client()
    collections = await client.get_collections()
    names = [c.name for c in collections.collections]

    if settings.qdrant_collection not in names:
        await client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(
                size=settings.vector_size,
                distance=Distance.COSINE,
            ),
        )
        logger.info("Created Qdrant collection: %s", settings.qdrant_collection)


async def upsert_chunks(
    chunks: list[DocumentChunk],
    embeddings: list[list[float]],
) -> None:
    """Upsert document chunks alongside their embedding vectors."""
    if not chunks:
        return

    client = get_client()
    points: list[PointStruct] = []

    for chunk, vector in zip(chunks, embeddings):
        points.append(
            PointStruct(
                id=_chunk_id_to_int(chunk.chunk_id),
                vector=vector,
                payload={
                    "chunk_id": chunk.chunk_id,
                    "doc_id": chunk.doc_id,
                    "source_file": chunk.source_file,
                    "page_label": chunk.page_label,
                    "text": chunk.text,
                    **chunk.metadata,
                },
            )
        )

    await client.upsert(
        collection_name=settings.qdrant_collection,
        points=points,
        wait=True,
    )
    logger.info("Upserted %d vectors into Qdrant.", len(points))


async def similarity_search(
    query_vector: list[float],
    top_k: int = settings.top_k,
    score_threshold: float | None = None,
) -> list[dict[str, Any]]:
    client = get_client()
    results = await client.search(
        collection_name=settings.qdrant_collection,
        query_vector=query_vector,
        limit=top_k,
        score_threshold=settings.similarity_threshold if score_threshold is None else score_threshold,
        with_payload=True,
    )
    return [
        {**hit.payload, "score": round(hit.score, 4)}
        for hit in results
        if hit.payload
    ]


async def collection_count() -> int:
    client = get_client()
    try:
        info = await client.get_collection(settings.qdrant_collection)
        return info.points_count or 0
    except Exception:
        return 0


def _chunk_id_to_int(chunk_id: str) -> int:
    """Convert hex MD5 to positive int for Qdrant point ID."""
    return int(chunk_id[:16], 16)
