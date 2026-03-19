# Changelog

All notable changes to **Consultant Knowledge RAG** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] — 2026-03-19

### 🚀 Release Highlights

**First production-ready release of Consultant Knowledge RAG.** Complete system for enterprise-grade retrieval-augmented generation over confidential documents, running entirely on-premises with zero API costs.

### ✨ Features

#### Core RAG Pipeline
- ✅ **Document Ingestion** — Parse PDF, DOCX, TXT files with smart chunking (768 tokens, 128 overlap)
- ✅ **Vector Embeddings** — nomic-embed-text (768-dim) via local Ollama
- ✅ **Semantic Search** — Qdrant vector database with similarity thresholding (0.35)
- ✅ **Answer Generation** — Qwen 2.5 (3B) with temperature control (0.1) for deterministic answers
- ✅ **Source Citations** — Every answer includes relevance scores and document metadata

#### API & Web Interface
- ✅ **FastAPI Backend** — Async, streaming responses, multi-tenant ready
- ✅ **NDJSON Streaming** — Real-time answer generation (token-at-a-time)
- ✅ **Web UI** — Vanilla HTML/JS, no framework bloat, responsive design
- ✅ **Swagger/OpenAPI** — Auto-generated API docs at `/docs`

#### Intelligence Features
- ✅ **Query Routing** — Classify queries as generic (no KB) vs. factual (KB search)
- ✅ **Feedback Loop** — User ratings (👍/👎) logged to feedback_log.jsonl
- ✅ **Health Monitoring** — /health endpoint tracks Ollama + Qdrant status
- ✅ **Configuration Management** — All tunables via .env (pydantic-settings)

#### Multi-Tenancy (Framework)
- ✅ **Tenant Isolation Architecture** — Separate Qdrant collections per tenant
- ✅ **API Key Auth** — Bearer token validation in middleware
- ✅ **Rate Limiting** — Per-tenant query limits (configurable)
- ⚠️ **Implementation Ready** — Auth middleware stubbed; see SECURITY.md for setup

#### Responsible AI
- ✅ **Hallucination Prevention** — Temperature 0.1, output capping (600 tokens)
- ✅ **Prompt Guardrails** — Explicit grounding rules, no meta-commentary
- ✅ **PII-Aware Retrieval** — Similarity thresholding + optional PII filtering
- ✅ **Auditability** — All queries logged; feedback data for RAGAS evaluation
- ✅ **Cost Transparency** — $0 API costs, local models, detailed cost analysis

#### Security & Compliance
- ✅ **On-Premises by Default** — No external API calls, data stays local
- ✅ **Secrets Management** — .env-based config, .gitignore protection
- ✅ **Encryption Foundation** — Ready for at-rest + in-transit encryption
- ✅ **Audit Trail** — Query/feedback logging, consent to SIEM integration
- ✅ **GDPR-Ready** — No personal data processing unless explicitly stored in docs
- ✅ **Data Residency** — Flexible: on-prem, AWS, Azure, GCP (your infrastructure)

### 📦 Dependencies (Pinned)

**Core:**
- FastAPI 0.115.5
- Uvicorn 0.32.1
- Python 3.11+

**RAG Engine:**
- Ollama 0.3.3 (local LLM serving)
- Qdrant-client 1.12.1 (vector database)
- LangChain-text-splitters 0.3.2 (document chunking)

**Document Processing:**
- pdfplumber 0.11.4 (PDF extraction)
- python-docx 1.1.2 (Word document parsing)

**Configuration & Utilities:**
- Pydantic 2.10.3 (data validation)
- Pydantic-settings 2.7.0 (config management)
- python-dotenv 1.0.1 (.env parsing)
- requests 2.32.3 (HTTP client)

**See requirements.txt for full list.**

### 📋 Documentation

- ✅ **README.md** — Problem statement, quick-start, value story
- ✅ **ARCHITECTURE.md** — Detailed system design, data flows, multi-tenancy
- ✅ **SECURITY.md** — Secrets management, auth, PII, compliance
- ✅ **RAI.md** — Responsible AI practices, cost analysis, evals
- ✅ **CHANGELOG.md** — This file
- ✅ **API Docs** — Auto-generated Swagger UI

### 🧪 Testing

- ✅ **Health Check Tests** — Verify Ollama + Qdrant connectivity
- ✅ **Ingestion Tests** — Document parsing and vector storage
- ✅ **Query Pipeline Tests** — End-to-end query + streaming
- ✅ **Smoke Tests** — Fast validation of core functionality
- ⚠️ **RAGAS Evaluation** — Stubbed; ready for user feedback data

### 🐳 Deployment

- ✅ **Docker** — Multi-stage Dockerfile for production
- ✅ **Docker Compose** — Local dev environment setup
- ✅ **Environment Flexibility** — Works on-prem, AWS, Azure, GCP
- ⚠️ **Kubernetes** — YAML templates available; not in core release

### 🔧 Configuration Tuning

All major settings configurable via .env:

```env
# Ollama
OLLAMA_BASE_URL=http://localhost:11434
MODEL_NAME=qwen2.5:3b
EMBED_MODEL=nomic-embed-text

# Qdrant
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=consultant_kb

# Retrieval
TOP_K=4                        # Chunks to retrieve
SIMILARITY_THRESHOLD=0.35      # Min relevance score
CHUNK_SIZE=768
CHUNK_OVERLAP=128

# Cost Control
GENERATION_TOP_K=4             # Sources to use
MAX_OUTPUT_TOKENS=600          # Answer length limit
LLM_NUM_CTX=2048               # Context window

# API
API_HOST=127.0.0.1
API_PORT=8000
```

### 🐛 Known Limitations

1. **Streaming Edge Case** — If Ollama doesn't support streaming for a model, falls back to pseudo-streaming (chunked output)
2. **Memory Usage** — Qwen 2.5 (3B) requires ~3-4GB VRAM (Ollama-optimized)
3. **Latency** — ~2-3s per query (acceptable for consultant use; not real-time chat)
4. **Multi-Tenancy** — Auth middleware stubbed; deployment guide in SECURITY.md
5. **Model Switching** — To use different models, update MODEL_NAME in .env (no code changes needed)

### 🔮 Roadmap

#### v1.1 (Next Sprint)
- [ ] Multi-tenant implementation (API key validation)
- [ ] Advanced filtering (by document type, date range)
- [ ] Reranking stage (cross-encoder for relevance)
- [ ] Confidence scoring (tell users when uncertain)

#### v1.2 (Mid-term)
- [ ] Fine-tuned router (domain-specific query classification)
- [ ] Active learning (query user for ground truth)
- [ ] Fine-tuned embedding model (on your documents)
- [ ] Streaming ingestion (real-time document updates)

#### v2.0 (Long-term)
- [ ] Hybrid retrieval (BM25 + semantic search)
- [ ] Graph RAG (knowledge graph extraction + reasoning)
- [ ] Multi-hop QA (chain multiple documents)
- [ ] Slack/Teams integration

### 🙏 Acknowledgments

**Open-Source Projects:**
- Ollama — Making local LLMs accessible
- Qdrant — Reliable vector database
- FastAPI — Modern async web framework
- Qwen Team — State-of-art 3B model
- nomic — Excellent embedding model

### 🤝 Contributing

This is a solo PoC built for a master's semester project. Feedback welcome via GitHub issues or direct outreach.

### 📄 License

All code: MIT License  
Dependencies: See requirements.txt (Apache 2.0, MIT, BSD compatible)

---

## [0.9.0-alpha] — 2026-03-10

### 🧪 Alpha Release

Initial internal testing version. Core RAG pipeline working, multi-tenancy scaffolding in place.

### ✨ Early Features
- RAG pipeline (Ollama + Qdrant)
- FastAPI backend
- Basic web UI
- Feedback logging

### ⚠️ Known Issues
- Streaming may fail on some models (fallback implemented)
- Auth middleware not yet enforced
- No Docker setup
- Limited documentation

---

## Version Tags

### Tagging Scheme

We use semantic versioning: `MAJOR.MINOR.PATCH`

```
v1.0.0 = major release, production-ready
v1.1.0 = minor feature addition
v1.0.1 = bug fix
```

### Git Tags

```bash
# View all releases
git tag -l

# View a specific release
git show v1.0.0

# Create a tag (maintainer only)
git tag -a v1.0.0 -m "Production release"
git push origin v1.0.0
```

---

## Upgrade Guide

### From 0.9.0 to 1.0.0

**No breaking changes.** Existing deployments can upgrade by:

1. Pulling latest code
2. Installing updated dependencies: `pip install -r requirements.txt`
3. Running migrations (none required for 1.0)
4. Restarting services

```bash
# Backup your data
cp -r qdrant_storage/ qdrant_storage.backup
cp feedback_log.jsonl feedback_log.jsonl.backup

# Upgrade code
git pull origin main

# Reinstall dependencies
pip install -r requirements.txt --upgrade

# Restart
docker-compose restart
```

---

## Security Updates

### Reporting Security Issues

**Do not open a public issue.** Email: security@your-domain.local

**Include:**
- Description of vulnerability
- Affected version(s)
- Steps to reproduce
- Potential impact

---

## Deprecations

**None in v1.0.0.**

Future deprecations will be announced 2 releases in advance.

---

## Migration Notes

### Model Switching (v1.1+)

To use a different LLM:

```bash
# 1. Pull the model
ollama pull llama2:7b

# 2. Update .env
MODEL_NAME=llama2:7b

# 3. Restart
docker-compose restart

# No code changes needed!
```

---

## Release Schedule

| Version | Release Date | Status | Support Until |
|---------|--------------|--------|---------------|
| v0.9-alpha | 2026-03-10 | Deprecated | (EOL) |
| **v1.0.0** | **2026-03-19** | **Current** | 2026-09-19 (6 months) |
| v1.1 | Q2 2026 (planned) | — | — |
| v2.0 | Q4 2026 (planned) | — | — |

---

## Questions?

- **Technical:** See README.md, ARCHITECTURE.md
- **Security:** See SECURITY.md
- **Responsible AI:** See RAI.md
- **Bugs/Features:** Open a GitHub issue

---

**Happy querying! 🚀**
