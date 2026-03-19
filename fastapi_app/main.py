"""FastAPI application — entry point and route definitions."""
import logging
import os
import shutil
import aiofiles
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from fastapi_app.schemas import (
    FeedbackRequest, FeedbackResponse,
    IngestRequest, IngestResponse,
    KnowledgeBaseStatus, QueryRequest,
    HealthResponse,
)
from fastapi_app.services import (
    check_health, get_kb_status, ingest_documents,
    log_feedback, query_knowledge_base_stream,
)
from rag_engine.vector_store import ensure_collection

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — initialising Qdrant collection...")
    await ensure_collection()
    yield
    logger.info("Shutdown complete.")


app = FastAPI(
    title="Consultant Knowledge RAG API",
    description="Retrieval-Augmented Generation over internal consulting reports.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("fastapi_app/static", exist_ok=True)
app.mount("/static", StaticFiles(directory="fastapi_app/static"), name="static")

@app.get("/", include_in_schema=False)
async def serve_spa():
    return FileResponse("fastapi_app/static/index.html")


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check() -> HealthResponse:
    return await check_health()


@app.post("/upload", tags=["Knowledge Base"])
async def upload_and_ingest(files: list[UploadFile] = File(...)):
    from rag_engine.config import settings
    doc_dir = Path(settings.document_dir)
    doc_dir.mkdir(parents=True, exist_ok=True)
    
    saved = []
    for f in files:
        file_path = doc_dir / f.filename
        async with aiofiles.open(file_path, "wb") as buf:
            while chunk := await f.read(1024 * 1024):
                await buf.write(chunk)
        saved.append(f.filename)
        
    try:
        res = await ingest_documents(force_reload=False)
        return {"status": "ok", "message": f"Uploaded {len(saved)} files", "ingest": res.model_dump()}
    except Exception as exc:
        logger.exception("Upload ingest failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/ingest", response_model=IngestResponse, tags=["Knowledge Base"])
async def ingest(req: IngestRequest) -> IngestResponse:
    try:
        return await ingest_documents(force_reload=req.force_reload)
    except Exception as exc:
        logger.exception("Ingestion failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/status", response_model=KnowledgeBaseStatus, tags=["Knowledge Base"])
async def kb_status() -> KnowledgeBaseStatus:
    return await get_kb_status()


@app.post("/query/stream", tags=["Query"])
async def query_stream(req: QueryRequest):
    if not req.question.strip():
        raise HTTPException(status_code=422, detail="Question cannot be empty.")
    try:
        return StreamingResponse(query_knowledge_base_stream(req), media_type="application/x-ndjson")
    except Exception as exc:
        logger.exception("Streaming query failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/feedback", response_model=FeedbackResponse, tags=["Feedback"])
async def feedback(req: FeedbackRequest) -> FeedbackResponse:
    return await log_feedback(req)
