# Architecture Document

## System Overview

**Consultant Knowledge RAG** is a **retrieval-augmented generation (RAG) system** designed for enterprises to query confidential documents using natural language. The system operates entirely on-premises, with no cloud APIs required.

### Core Design Principles

1. **Transparency** — Every answer includes source citations and relevance scores
2. **Determinism** — Low temperature (0.1) ensures consistent answers across identical queries
3. **Cost-awareness** — Local models eliminate per-query API costs
4. **Auditability** — All queries and feedback logged for compliance/evals
5. **Multi-tenancy** — Isolated knowledge bases per organizational unit

---

## System Architecture

### Layered Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                         Presentation Layer                         │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │  Browser UI (HTML/JS/Vanilla)                              │ │
│  │  • Document upload & ingestion controls                    │ │
│  │  • Query interface with streaming responses                │ │
│  │  • Source context visualization                            │ │
│  │  • Feedback collection (👍/👎)                             │ │
│  └──────────────────────────────────────────────────────────────┘ │
└────────────────────┬─────────────────────────────────────────────┘
                     │ HTTP/WebSocket
┌────────────────────↓─────────────────────────────────────────────┐
│                       API Layer (FastAPI)                         │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │  Routes:                                                    │ │
│  │  • POST /ingest          → Trigger document ingestion      │ │
│  │  • POST /query/stream    → Query with streaming response   │ │
│  │  • POST /feedback        → Log response feedback           │ │
│  │  • GET /health           → System diagnostics              │ │
│  │  • GET /status           → Knowledge base metadata         │ │
│  │                                                              │ │
│  │  Middleware:                                                │ │
│  │  • CORS (allow all for development)                        │ │
│  │  • Request logging                                          │ │
│  │  • Error handling                                           │ │
│  └──────────────────────────────────────────────────────────────┘ │
└────────────────┬─────────────────────────────────┬────────────────┘
                 │                                 │
        ┌────────↓────────┐             ┌──────────↓──────────┐
        │ Services Layer  │             │ Config Layer        │
        ├─ Orchestration  │             ├─ pydantic-settings  │
        ├─ Error handling │             ├─ .env parsing       │
        └─────────┬───────┘             └─────────────────────┘
                  │
        ┌─────────↓───────────────────────────────┐
        │      Business Logic (RAG Engine)        │
        │  ┌──────────────────────────────────┐   │
        │  │  1. Data Loader                  │   │
        │  │     • PDF parsing (pdfplumber)   │   │
        │  │     • DOCX parsing (python-docx) │   │
        │  │     • Text chunking              │   │
        │  │     • Hash caching (no re-embed) │   │
        │  └──────────────────────────────────┘   │
        │  ┌──────────────────────────────────┐   │
        │  │  2. Vector Store (Qdrant)        │   │
        │  │     • Upsert chunks → vectors    │   │
        │  │     • Search by similarity       │   │
        │  │     • Multi-collection support   │   │
        │  └──────────────────────────────────┘   │
        │  ┌──────────────────────────────────┐   │
        │  │  3. Retriever                    │   │
        │  │     • Embedding (nomic-embed)    │   │
        │  │     • Similarity search          │   │
        │  │     • Score thresholding (0.35)  │   │
        │  └──────────────────────────────────┘   │
        │  ┌──────────────────────────────────┐   │
        │  │  4. Generator (LLM Orchestration)│   │
        │  │     • Prompt templating          │   │
        │  │     • Stream handling            │   │
        │  │     • Output validation          │   │
        │  └──────────────────────────────────┘   │
        │  ┌──────────────────────────────────┐   │
        │  │  5. Router (Query Classification)│   │
        │  │     • Generic (hello/how are you)│   │
        │  │     • Factual (KB lookup needed) │   │
        │  └──────────────────────────────────┘   │
        └──────────────┬──────────────────────────┘
                       │
        ┌──────────────↓──────────────────────────┐
        │        External Services Layer          │
        │  ┌──────────────────────────────────┐   │
        │  │  Ollama (Local LLM Server)       │   │
        │  │  • Model: qwen2.5:3b (3.8B)      │   │
        │  │  • Embed: nomic-embed-text       │   │
        │  │  • Latency: 2-3s per query       │   │
        │  │  • Hosted: localhost:11434       │   │
        │  └──────────────────────────────────┘   │
        │  ┌──────────────────────────────────┐   │
        │  │  Qdrant (Vector Database)        │   │
        │  │  • Embedding dim: 768            │   │
        │  │  • Collections: multi-tenant     │   │
        │  │  • Hosted: localhost:6333        │   │
        │  │  • Storage: ./qdrant_storage/    │   │
        │  └──────────────────────────────────┘   │
        │  ┌──────────────────────────────────┐   │
        │  │  File System                     │   │
        │  │  • ./internal_reports/           │   │
        │  │  • ./feedback_log.jsonl          │   │
        │  └──────────────────────────────────┘   │
        └─────────────────────────────────────────┘
```

---

## Data Flow Diagrams

### 1. Document Ingestion Pipeline

```
User Upload (UI)
    │
    ↓
POST /upload [file1.pdf, file2.docx]
    │
    ├─→ Save to ./internal_reports/
    │
    ↓
POST /ingest
    │
    ├─→ data_loader.load_documents()
    │   ├─ Hash each file (skip if unchanged)
    │   ├─ Parse PDF → text chunks
    │   ├─ Parse DOCX → text chunks
    │   ├─ Split chunks (768 tokens, 128 overlap)
    │   └─ Return: [Chunk, Chunk, ...]
    │
    ├─→ retriever.embed_chunks()
    │   ├─ Call Ollama nomic-embed-text
    │   └─ Return: [[0.1, -0.2, ...], ...]  (768-dim vectors)
    │
    ├─→ vector_store.upsert()
    │   ├─ Call Qdrant API
    │   ├─ Store: {id, vector, metadata: {source, page}}
    │   └─ Build indexes
    │
    ↓
IngestResponse
{
  "status": "ok",
  "files_processed": 5,
  "chunks_added": 245,
  "total_vectors": 1024
}
```

### 2. Query Pipeline (Streaming)

```
User Input: "What is our digital transformation approach?"
    │
    ↓
POST /query/stream {question, top_k: 4}
    │
    ├─→ Query Router (_classify_query)
    │   ├─ Send to LLM: "Is this GENERIC or FACTUAL?"
    │   ├─ LLM response: "FACTUAL"
    │   └─ Route to: retriever + generator
    │
    ├─→ Retriever.search()
    │   ├─ Embed query: [0.15, -0.1, ...]  (768-dim)
    │   ├─ Qdrant: Find nearest 4 vectors
    │   └─ Filter by similarity_threshold (≥0.35)
    │   └─ Return: [SourceContext, SourceContext, ...]
    │
    ├─→ Generator.stream_answer()
    │   ├─ Build prompt:
    │   │  SYSTEM: "You are a consultant..."
    │   │  USER: "[1] Source: file1.pdf | pg 5 | score 0.89
    │   │         [2] Source: file2.pdf | pg 12 | score 0.76
    │   │         Question: What is our digital transformation..."
    │   │
    │   ├─ Call Ollama qwen2.5:3b (streaming mode)
    │   ├─ Options: temp=0.1, num_predict=600
    │   │
    │   └─ Stream chunks to client:
    │      "Our digital transformation"
    │      " approach focuses on"
    │      " three key pillars:"
    │      ...
    │
    ├─→ Emit metadata
    │   {
    │     "type": "meta",
    │     "sources": [...],
    │     "model_used": "qwen2.5:3b",
    │     "chunks_retrieved": 4
    │   }
    │
    ↓
Client receives streaming JSON (NDJSON)
```

### 3. Feedback Loop (Continuous Improvement)

```
User Rating (👍 or 👎)
    │
    ↓
POST /feedback
{
  "question": "What is our DX approach?",
  "answer": "Our digital transformation...",
  "rating": 1,  # 1=helpful, 0=not helpful
  "model_used": "qwen2.5:3b"
}
    │
    ├─→ Log to feedback_log.jsonl
    │   (Appended for historical analysis)
    │
    ↓
FeedbackResponse: {"status": "ok", "message": "Thank you!"}

# Later: Use feedback_log.jsonl for:
# - RAGAS evals (Retrieval Augmented Generation Assessment)
# - Model fine-tuning data
# - Quality metrics
```

---

## Multi-Tenancy Design

### Tenant Isolation Strategy

Each **tenant** (team, client, or organizational unit) gets:

1. **Separate Qdrant Collection**
   - Namespace: `consultant_kb_{tenant_id}`
   - Prevents cross-tenant data leakage
   - Independent indexing & search

2. **Separate API Key**
   - Required header: `Authorization: Bearer {tenant_api_key}`
   - Validated at FastAPI middleware
   - Rate limiting per API key

3. **Separate Document Store**
   - Path: `./internal_reports/{tenant_id}/`
   - Documents only ingested into tenant's collection
   - Clear audit trail

### Example: Multi-Tenant Query

```python
# Request
curl -X POST http://localhost:8000/query/stream \
  -H "Authorization: Bearer tenant-acme-corp-key" \
  -H "Content-Type: application/json" \
  -d '{"question": "ACME digital strategy?", "top_k": 4}'

# In services.py, middleware validates:
if not request.headers.get("Authorization"):
    raise HTTPException(status_code=401, detail="Missing API key")

tenant_id = validate_api_key(request.headers["Authorization"])

# Retriever searches only in tenant's collection:
# collection_name = f"consultant_kb_{tenant_id}"
sources = await retrieve(question, collection=collection_name)
```

### Authentication & Authorization

```
┌─────────────────────────────────────────┐
│  API Gateway / Middleware               │
├─────────────────────────────────────────┤
│  1. Check Authorization header          │
│  2. Validate API key signature          │
│  3. Map key → Tenant ID                 │
│  4. Add tenant_id to request context    │
│  5. Enforce collection isolation        │
└─────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────┐
│  Route Handler (now tenant-aware)       │
├─────────────────────────────────────────┤
│  POST /query/stream                     │
│    └─ retrieve(question,                │
│         collection=f"kb_{tenant_id}")   │
└─────────────────────────────────────────┘
```

---

## LLM Interaction Patterns

### Answer Generation (Temperature Control)

```python
# From generator.py
response = await client.chat(
    model=settings.model_name,  # qwen2.5:3b
    messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ],
    options={
        "temperature": 0.1,          # ← Deterministic (0.0=greedy, 0.5=balanced)
        "num_ctx": 2048,             # ← Context window
        "num_predict": 600,          # ← Max output tokens
    },
)
```

**Why 0.1?**
- **0.0** = Always pick the most likely token (too rigid)
- **0.1** = Small randomness for variety, but mostly deterministic
- **0.5** = Balanced (default for chatbots)
- **1.0+** = High creativity (not suitable for factual RAG)

### Query Routing (Generic vs. Factual)

```python
# From services.py
async def _classify_query(question: str) -> bool:
    """
    Returns True if query is GENERIC (no KB lookup needed)
    Returns False if query is FACTUAL (needs KB search)
    """
    prompt = (
        "Classify: GENERIC or FACTUAL?\n"
        "GENERIC: hello, who are you, what can you do?\n"
        "FACTUAL: questions needing document facts.\n"
        f"Input: {question}"
    )
    
    resp = await client.chat(
        model=settings.model_name,
        messages=[...],
        options={"temperature": 0.0, "num_predict": 5},  # Classification only
    )
    
    # Route decision:
    # GENERIC → stream_answer(question, sources=[])  (no KB context)
    # FACTUAL → retrieve(question) → stream_answer(question, sources=[...])
```

**Examples:**

| Query | Classification | Action |
|-------|-----------------|--------|
| "Hello, how are you?" | GENERIC | Answer naturally, no KB |
| "What is digital transformation?" | FACTUAL | Retrieve from KB |
| "Who are you?" | GENERIC | Explain capabilities, no KB |
| "What was the TechCorp recommendation?" | FACTUAL | Search KB, cite sources |

---

## Performance & Scaling

### Latency Breakdown

```
Query: "What is our DX approach?"

Stage                               Duration      Notes
─────────────────────────────────────────────────────────────
1. Router classification            0.2–0.5s     Ollama qwen2.5:3b
2. Query embedding                  0.1–0.3s     nomic-embed-text
3. Qdrant search (top-4)             0.05–0.1s     Local vector search
4. LLM answer generation            2.0–3.0s     Streaming (token-at-a-time)
5. Network + UI rendering            0.2–0.5s     WebSocket overhead
─────────────────────────────────────────────────────────────
Total E2E Latency                    2.7–4.4s     Typical
```

### Memory Requirements

```
Component                           Memory (GB)    Notes
────────────────────────────────────────────────────────
Ollama (qwen2.5:3b loaded)           3–4           3B model in VRAM
Qdrant (10k vectors)                 0.5–1.0       768-dim embeddings
FastAPI application                  0.2–0.5       Async app
Python runtime                       0.3–0.5       Standard libraries
────────────────────────────────────────────────────────
Minimum Recommended                  4–6 GB        Single-server setup
```

### Scaling Options

| Scale Level | Setup | Cost/Year | Notes |
|------------|-------|-----------|-------|
| **Development** | Laptop | $0 | Single user, offline-capable |
| **Team PoC** | 1 VM (4 vCPU, 8GB RAM) | $500–1k | 10–50 concurrent users |
| **Pilot** | 2 VMs (distributed) | $1–2k | 50–200 users, HA |
| **Production** | Kubernetes cluster | $2–5k | 200+ users, auto-scaling |

### Vector DB Growth

```
Documents Ingested    Chunks (768-token)    Storage (Qdrant)    Search Latency
─────────────────────────────────────────────────────────────────────────────
10 PDFs               ~500 chunks           ~100 MB             < 50ms
100 PDFs              ~5k chunks            ~1 GB               < 100ms
1000 PDFs             ~50k chunks           ~10 GB              ~200ms
```

---

## Error Handling & Resilience

### Health Checks

```python
# GET /health
{
  "status": "ok",  # or "degraded"
  "ollama_reachable": true,
  "qdrant_ready": true,
}
```

**Degraded States:**
- Ollama down → Can't generate answers (but UI stays up)
- Qdrant down → Can't retrieve documents (health = degraded)
- Both services down → Return 503 Service Unavailable

### Graceful Degradation

```
Query arrives
  ├─ Is Ollama reachable?
  │  ├─ YES → Proceed normally
  │  └─ NO → Return "Service temporarily unavailable"
  │
  ├─ Is Qdrant reachable?
  │  ├─ YES → Proceed with retrieval
  │  └─ NO → Return "Knowledge base unavailable"
```

---

## Configuration Management

### Environment Variables (.env)

```bash
# Ollama (LLM server)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_API_KEY=                         # Optional: for remote Ollama
MODEL_NAME=qwen2.5:3b
EMBED_MODEL=nomic-embed-text

# Qdrant (vector store)
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=consultant_kb
VECTOR_SIZE=768

# Tuning
CHUNK_SIZE=768                          # Tokens per chunk
CHUNK_OVERLAP=128                       # Overlap for context
TOP_K=4                                 # Chunks to retrieve
SIMILARITY_THRESHOLD=0.35               # Min relevance score
GENERATION_TOP_K=4                      # Sources to use
MAX_OUTPUT_TOKENS=600                   # Answer length limit
LLM_NUM_CTX=2048                        # Context window
```

### Loading Order

```python
# pydantic-settings automatically loads:
1. .env file (current directory)
2. Environment variables (system)
3. Field defaults in Settings class

# Example:
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        alias="OLLAMA_BASE_URL"
    )
    
    class Config:
        env_file = ".env"
        populate_by_name = True  # Allow direct field names too
```

---

## Deployment Architectures

### 1. Single Server (Development)

```
┌──────────────────────────────┐
│  Single VM / Laptop          │
├──────────────────────────────┤
│  FastAPI (port 8000)         │
│  Ollama (port 11434)         │
│  Qdrant (port 6333)          │
│  ./internal_reports/         │
│  ./qdrant_storage/           │
└──────────────────────────────┘
```

### 2. Distributed (Production)

```
┌─────────────────────────────────────────────────┐
│  Load Balancer / Reverse Proxy (nginx)          │
└──────────────┬──────────────────────────────────┘
               │
    ┌──────────┼──────────┐
    │          │          │
    ↓          ↓          ↓
┌────────┐ ┌────────┐ ┌────────┐
│FastAPI1│ │FastAPI2│ │FastAPI3│ (Replicas)
├────────┤ ├────────┤ ├────────┤
│(p 8000)│ │(p 8000)│ │(p 8000)│
└────────┘ └────────┘ └────────┘
    ↓          ↓          ↓
└──────────────┬──────────────────────────────────┘
               │
    ┌──────────┼──────────┐
    │          │          │
    ↓          ↓          ↓
┌─────────────────────────────────────────────────┐
│  Shared Ollama Service (p 11434)                │
│  (Could be local or remote)                     │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│  Shared Qdrant Cluster (p 6333)                 │
│  (High-availability setup)                      │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│  Shared Storage                                 │
│  • ./internal_reports/ (NFS/S3)                 │
│  • feedback_log.jsonl (centralized logging)     │
└─────────────────────────────────────────────────┘
```

---

## Security Architecture

### Data Flow (No External APIs)

```
Browser
  ↓ HTTPS (if deployed publicly)
FastAPI Server (local)
  ↓
Ollama (local)  ← Models never phone home
  ↓
Qdrant (local)  ← Vectors stay on-prem
  ↓
./internal_reports/  ← Confidential docs stay local
```

### API Authentication (Multi-Tenant)

```
curl -H "Authorization: Bearer tenant-acme-key" \
  http://localhost:8000/query/stream

# Middleware checks:
1. Is token present?
2. Is token valid (in secrets store)?
3. Map token → tenant_id
4. Enforce tenant_id in collection names
```

See **[SECURITY.md](./SECURITY.md)** for detailed auth, PII handling, and compliance.

---

## Future Enhancements

### Planned (v1.1)

- ✅ Multi-tenant isolation (separate API keys)
- ✅ Advanced filtering (by doc type, date range)
- ✅ Fine-tuned router (domain-specific classification)
- ✅ Reranking (cross-encoder for relevance)

### Exploration (v1.2+)

- Hybrid retrieval (BM25 + semantic search)
- Graph RAG (relationship extraction + reasoning)
- Streaming ingestion (real-time document updates)
- Active learning (identify low-confidence queries for human review)

---

## References

- **Ollama Docs:** https://ollama.ai
- **Qdrant Docs:** https://qdrant.tech
- **FastAPI:** https://fastapi.tiangolo.com
- **RAG Best Practices:** https://arxiv.org/abs/2312.10997 (LlamaIndex)

---

**Next Steps:**
1. Review **[SECURITY.md](./SECURITY.md)** for deployment checklist
2. Read **[RAI.md](./RAI.md)** for responsible AI guardrails
3. Check **[CHANGELOG.md](./CHANGELOG.md)** for version roadmap
