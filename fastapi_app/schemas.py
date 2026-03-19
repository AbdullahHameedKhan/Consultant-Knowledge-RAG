"""Pydantic schemas — single source of truth for API contracts."""
from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000, description="Natural language question")
    top_k: int = Field(default=4, ge=1, le=10, description="Number of context chunks to retrieve")


class SourceContextSchema(BaseModel):
    source_file: str
    page_label: str
    relevance_score: float
    excerpt: str = Field(..., description="Relevant text snippet (first 300 chars)")


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceContextSchema]
    model_used: str
    chunks_retrieved: int


class IngestRequest(BaseModel):
    force_reload: bool = Field(default=False, description="Re-embed all docs even if hash unchanged")


class IngestResponse(BaseModel):
    status: str
    files_processed: int
    chunks_added: int
    total_vectors: int


class KnowledgeBaseStatus(BaseModel):
    total_vectors: int
    document_dir: str
    embed_model: str
    llm_model: str
    collection_name: str


class FeedbackRequest(BaseModel):
    question: str
    answer: str
    rating: int = Field(..., ge=1, le=2, description="1 = thumbs down, 2 = thumbs up")
    comment: str | None = None


class FeedbackResponse(BaseModel):
    status: str
    message: str


class HealthResponse(BaseModel):
    status: str
    ollama_reachable: bool
    qdrant_ready: bool
