"""Central configuration — all tunables live here, never in logic files."""
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # Ollama
    ollama_base_url: str = Field(alias="OLLAMA_BASE_URL")
    ollama_api_key: str | None = Field(alias="OLLAMA_API_KEY")
    embed_base_url: str = Field(alias="EMBED_BASE_URL")
    embed_api_key: str | None = Field(alias="EMBED_API_KEY")
    model_name: str = Field(alias="MODEL_NAME")
    embed_model: str = Field(alias="EMBED_MODEL")

    # Paths
    document_dir: str = Field(alias="DOCUMENT_DIR")

    # Chunking
    chunk_size: int = Field(alias="CHUNK_SIZE")
    chunk_overlap: int = Field(alias="CHUNK_OVERLAP")

    # Retrieval
    top_k: int = Field(alias="TOP_K")
    similarity_threshold: float = Field(alias="SIMILARITY_THRESHOLD")
    generation_top_k: int = Field(alias="GENERATION_TOP_K")
    max_source_chars: int = Field(alias="MAX_SOURCE_CHARS")

    # Qdrant
    qdrant_collection: str = Field(alias="QDRANT_COLLECTION")
    vector_size: int = Field(alias="VECTOR_SIZE")
    qdrant_path: str | None = Field(alias="QDRANT_PATH")
    qdrant_url: str | None = Field(alias="QDRANT_URL")

    # FastAPI
    api_host: str = Field(alias="API_HOST")
    api_port: int = Field(alias="API_PORT")
    llm_num_ctx: int = Field(alias="LLM_NUM_CTX")
    max_output_tokens: int = Field(alias="MAX_OUTPUT_TOKENS")

    class Config:
        env_file = ".env"
        populate_by_name = True


settings = Settings()
