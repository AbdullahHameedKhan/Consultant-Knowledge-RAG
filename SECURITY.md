# Security Policy

## Overview

**Consultant Knowledge RAG** is designed for enterprise deployment with strict attention to:
- **Data Residency:** All data stays on-premises or in your controlled cloud infrastructure
- **No External APIs:** Zero external API calls (no OpenAI, no Azure, no cloud vendor lock-in)
- **Confidentiality:** Confidential documents never leave your infrastructure
- **Auditability:** All queries and feedback logged for compliance audits
- **Multi-Tenancy:** Tenant isolation prevents cross-organizational data leakage

---

## 1. Secrets Management

### Critical Secrets

| Secret | Purpose | Default | Storage |
|--------|---------|---------|---------|
| `OLLAMA_API_KEY` | Auth for remote Ollama | Empty (local) | `.env` (DO NOT commit) |
| `EMBED_API_KEY` | Auth for remote embeddings | Empty (local) | `.env` (DO NOT commit) |
| `API_TENANT_KEYS` | Tenant→Key mapping | `{}` | `secrets.json` (encrypted) |
| `JWT_SECRET` | (Future) JWT signing key | N/A | Vault/Secrets Manager |

### Secrets Handling Best Practices

#### ✅ DO:
```bash
# Generate a strong API key for each tenant
python -c "import secrets; print(secrets.token_urlsafe(32))"
# Output: AbC_dEf-GhIjKlMnOpQrStUvWxYz1234567890

# Store in .env (local dev) or Secrets Manager (production)
export API_KEY_ACME_CORP="AbC_dEf-GhIjKlMnOpQrStUvWxYz1234567890"

# Use environment variable
TENANT_API_KEY = os.getenv("API_KEY_ACME_CORP")

# Rotate keys quarterly
# For each key rotation:
# 1. Generate new key
# 2. Add to Secrets Manager with "new" label
# 3. Update clients to new key (with 30-day grace period)
# 4. Revoke old key
```

#### ❌ DON'T:
```bash
# DON'T hardcode keys in code
API_KEY = "AbC_dEf-GhIjKlMnOpQrStUvWxYz1234567890"

# DON'T commit .env to git
git add .env  # ❌ WRONG

# DON'T log secrets
logger.info(f"Using API key: {api_key}")  # ❌ WRONG

# DON'T reuse keys across tenants
api_key_for_all = "shared-secret"  # ❌ WRONG
```

### Environment Variables (.env)

**Development (.env):**
```bash
# Copy from .env.example and fill in
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_API_KEY=
MODEL_NAME=qwen2.5:3b

# These can be empty for local development
EMBED_API_KEY=
```

**Production (.env or Secrets Manager):**
```bash
# Use AWS Secrets Manager, HashiCorp Vault, or Azure Key Vault
OLLAMA_BASE_URL=https://ollama.acme-corp.com  # Remote Ollama
OLLAMA_API_KEY=${VAULT_OLLAMA_KEY}            # From vault
EMBED_API_KEY=${VAULT_EMBED_KEY}              # From vault

# Tenant API keys (example)
API_KEY_ACME_CORP=${VAULT_ACME_KEY}
API_KEY_TECHCORP=${VAULT_TECHCORP_KEY}
```

### Git Security

```bash
# Ensure .env is ignored
cat .gitignore
# Output should include:
.env
.env.local
secrets.json
qdrant_storage/
feedback_log.jsonl

# Check for accidentally committed secrets
git log -p -- .env | head  # Should be empty

# Scan codebase for hardcoded secrets
pip install detect-secrets
detect-secrets scan --baseline .secrets.baseline
```

---

## 2. Authentication & Authorization

### Multi-Tenant API Key Strategy

#### Architecture

```
Request Header: Authorization: Bearer {tenant_api_key}
                              │
                              ↓
                      [Middleware Layer]
                      1. Extract bearer token
                      2. Look up in Secrets Store
                      3. Map token → tenant_id
                      4. Validate tenant_id
                      5. Add to request context
                              │
                              ↓
                      [Route Handler]
                      Uses tenant_id to:
                      - Select Qdrant collection
                      - Filter documents
                      - Enforce rate limits
```

#### Implementation Example

```python
# fastapi_app/middleware.py

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

# In-memory tenant store (would be in Vault/Secrets Manager in production)
TENANT_API_KEYS = {
    "acme-corp-key-1234567890": {"tenant_id": "acme", "org": "ACME Corp"},
    "techcorp-key-0987654321": {"tenant_id": "techcorp", "org": "TechCorp Inc"},
}

async def tenant_middleware(request: Request, call_next):
    """Validate API key and inject tenant_id into request."""
    
    # Skip auth for health check
    if request.url.path == "/health":
        return await call_next(request)
    
    # Extract Authorization header
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    
    api_key = auth_header[7:]  # Remove "Bearer " prefix
    
    # Validate API key
    if api_key not in TENANT_API_KEYS:
        logger.warning(f"Invalid API key attempt: {api_key[:10]}...")
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    tenant_info = TENANT_API_KEYS[api_key]
    
    # Inject tenant_id into request state
    request.state.tenant_id = tenant_info["tenant_id"]
    request.state.tenant_org = tenant_info["org"]
    
    return await call_next(request)

# Usage in routes
@app.post("/query/stream")
async def query_stream(req: QueryRequest, request: Request):
    tenant_id = request.state.tenant_id
    
    # Retrieve only from tenant's collection
    sources = await retrieve(
        req.question, 
        collection=f"consultant_kb_{tenant_id}"
    )
    ...
```

#### Production Setup (AWS Secrets Manager)

```python
# fastapi_app/auth.py

import boto3
import json
from functools import lru_cache

secrets_client = boto3.client("secretsmanager", region_name="us-east-1")

@lru_cache(maxsize=100)
def get_tenant_api_keys():
    """Load tenant API keys from AWS Secrets Manager."""
    try:
        response = secrets_client.get_secret_value(SecretId="prod/tenant-api-keys")
        return json.loads(response["SecretString"])
    except Exception as e:
        logger.error(f"Failed to load tenant keys: {e}")
        raise

# Called at app startup
@app.on_event("startup")
async def load_secrets():
    global TENANT_API_KEYS
    TENANT_API_KEYS = get_tenant_api_keys()
    logger.info(f"Loaded {len(TENANT_API_KEYS)} tenant API keys")
```

### Rate Limiting (Cost Control)

```python
# fastapi_app/rate_limit.py

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/query/stream")
@limiter.limit("100/hour")  # 100 queries per hour per tenant
async def query_stream(req: QueryRequest, request: Request):
    tenant_id = request.state.tenant_id
    
    # Additionally, enforce per-tenant limits
    daily_limit = 10000  # Queries per day per tenant
    today_usage = get_tenant_usage(tenant_id, date.today())
    
    if today_usage >= daily_limit:
        raise HTTPException(
            status_code=429,
            detail=f"Daily query limit exceeded ({daily_limit}). Reset tomorrow."
        )
    
    # Process query
    ...
```

---

## 3. Data Residency & Compliance

### On-Premises Deployment

**Default Setup (Development/Testing):**
```
┌──────────────────────────────┐
│  Your Laptop / Local VM      │
├──────────────────────────────┤
│  FastAPI + Ollama + Qdrant   │
│  ./internal_reports/         │
│  ./qdrant_storage/           │
└──────────────────────────────┘
✅ All data stays local
✅ No cloud dependencies
✅ Full control
```

**On-Premises Production (Your Data Center):**
```
┌─────────────────────────────────────────┐
│  Your Corporate Data Center              │
├─────────────────────────────────────────┤
│  ┌─────────────────────────────────┐    │
│  │  FastAPI Replicas (3x)          │    │
│  │  Load Balancer (nginx)          │    │
│  └─────────────────────────────────┘    │
│  ┌─────────────────────────────────┐    │
│  │  Ollama Service                 │    │
│  │  (Could be shared or dedicated) │    │
│  └─────────────────────────────────┘    │
│  ┌─────────────────────────────────┐    │
│  │  Qdrant Cluster (3-node HA)     │    │
│  └─────────────────────────────────┘    │
│  ┌─────────────────────────────────┐    │
│  │  Network Storage (NFS/SAN)      │    │
│  │  • internal_reports/            │    │
│  │  • qdrant_storage/              │    │
│  │  • feedback_log.jsonl           │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
✅ All data in your facility
✅ Encrypted at rest & in transit
✅ Audit logs (syslog → SIEM)
```

### Cloud Deployment (Hybrid)

**Option A: Your Cloud Account (AWS/GCP/Azure)**

```
Your AWS Account
├─ VPC (private network)
├─ EC2 instances (FastAPI)
├─ RDS or EBS (storage)
├─ Secrets Manager (API keys)
└─ CloudWatch (logs)

✅ Data stays in YOUR account
✅ You manage encryption keys
✅ HIPAA/SOC2 compliance possible
```

**Option B: Mixed (Not Recommended)**

```
Avoid:
• Ollama in cloud, Qdrant on-prem (latency issues)
• Documents in cloud, Qdrant on-prem (data residency issues)

Instead:
• Keep all components in same region/facility
```

### Compliance Certifications

| Standard | Compliance Status | Notes |
|----------|------------------|-------|
| **GDPR** | ✅ Ready | No external APIs, data stays in-region |
| **HIPAA** | ✅ Ready | On-premises + encryption + audit logs |
| **SOC 2** | ⚠️ Partial | Requires: encryption, audit logs, access controls |
| **ISO 27001** | ⚠️ Partial | Requires: formal InfoSec program |
| **FedRAMP** | ❌ Not applicable | For cloud providers only |

---

## 4. Personally Identifiable Information (PII) Handling

### PII Detection & Prevention

#### What is Considered PII?

```
✅ Safe to include in documents:
- Company names (ACME Corp, TechCorp)
- Project codenames (Project Alpha, Initiative X)
- Generic business metrics (25% revenue growth)
- Methodology names (our 5-step framework)

❌ DO NOT include in documents:
- Employee names (John Smith, Jane Doe)
- Email addresses (john@acme.com)
- Phone numbers (555-1234)
- Social Security numbers (123-45-6789)
- Credit card numbers
- Customer personal data (without consent)
```

#### Handling PII in Documents

**Option 1: Redact Before Upload**

```bash
# Use a redaction tool or script
python scripts/redact_pii.py ./internal_reports/

# Input:
# "John Smith from TechCorp contacted us for the DX initiative..."

# Output:
# "[PERSON] from TechCorp contacted us for the DX initiative..."
```

**Option 2: PII Filter in Retrieval**

```python
# rag_engine/retriever.py

import re

PII_PATTERNS = {
    "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    "phone": r"\d{3}[-.]?\d{3}[-.]?\d{4}",
    "ssn": r"\d{3}-\d{2}-\d{4}",
}

def has_pii(text: str) -> bool:
    """Check if text contains PII patterns."""
    for pattern in PII_PATTERNS.values():
        if re.search(pattern, text):
            return True
    return False

async def retrieve(question: str, top_k: int = 4):
    # Retrieve candidates
    candidates = await vector_store.search(question, top_k * 2)
    
    # Filter out any results containing PII
    safe_results = [
        c for c in candidates 
        if not has_pii(c.text)
    ]
    
    # Return top-k safe results
    return safe_results[:top_k]
```

#### Document Scanning

```bash
# Pre-ingest scan for PII
pip install presidio-analyzer

python -c "
from presidio_analyzer import AnalyzerEngine

analyzer = AnalyzerEngine()

with open('document.txt') as f:
    text = f.read()
    results = analyzer.analyze(text=text, language='en')
    
    for entity in results:
        print(f'Found {entity.entity_type} at {entity.start}-{entity.end}')
        print(f'  Risk: {entity.score:.2%}')
"
```

---

## 5. Data Encryption

### Encryption at Rest

```
┌──────────────────────────────────────────────┐
│  Qdrant Storage (./qdrant_storage/)          │
├──────────────────────────────────────────────┤
│  ✅ Enable Qdrant encryption (built-in)      │
│     See: https://qdrant.tech/docs/concepts   │
└──────────────────────────────────────────────┘

┌──────────────────────────────────────────────┐
│  Confidential Documents                      │
├──────────────────────────────────────────────┤
│  ✅ Use encrypted volume                     │
│     Linux: LUKS                              │
│     AWS: EBS encryption                      │
│     Azure: Disk encryption                   │
└──────────────────────────────────────────────┘

┌──────────────────────────────────────────────┐
│  Feedback Log (feedback_log.jsonl)           │
├──────────────────────────────────────────────┤
│  ✅ Encrypt in transit & at rest             │
│  ✅ Restrict file permissions (600)          │
│  ✅ Rotate files regularly                   │
└──────────────────────────────────────────────┘
```

### Encryption in Transit

```bash
# ✅ Enable HTTPS when deployed publicly
# (Use self-signed cert for internal only)

# Generate self-signed cert
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365

# Run with HTTPS
uvicorn fastapi_app.main:app --ssl-keyfile=key.pem --ssl-certfile=cert.pem

# Or use nginx as reverse proxy
# (Recommended for production)
```

---

## 6. Access Control

### File Permissions

```bash
# Configuration files
chmod 600 .env                      # Owner read-write only
chmod 600 secrets.json              # Owner read-write only

# Directories
chmod 755 fastapi_app/              # Readable by all, writable by owner
chmod 700 qdrant_storage/           # Owner only (contains encrypted data)
chmod 700 internal_reports/         # Owner only (contains sensitive docs)

# Audit log
chmod 600 feedback_log.jsonl        # Owner read-write only
```

### Firewall Rules (Kubernetes/VM)

```bash
# If deploying in cloud VPC:

# Allow (internal only)
Port 8000   (FastAPI)      FROM: 10.0.0.0/8      (internal only)
Port 11434  (Ollama)       FROM: 127.0.0.1       (localhost only)
Port 6333   (Qdrant)       FROM: 127.0.0.1       (localhost only)

# Block (all external)
Port 443    (HTTPS)        FROM: 0.0.0.0/0       ❌ Expose only via load balancer
Port 22     (SSH)          FROM: 0.0.0.0/0       ❌ Use bastion host
```

---

## 7. Audit Logging

### Query Audit Trail

```python
# fastapi_app/services.py

import logging
import json
from datetime import datetime

audit_logger = logging.getLogger("audit")

async def query_knowledge_base_stream(req: QueryRequest, request: Request):
    tenant_id = request.state.tenant_id
    
    # Log query start
    audit_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "event": "query_start",
        "tenant_id": tenant_id,
        "question_hash": hashlib.sha256(req.question.encode()).hexdigest(),
        "top_k": req.top_k,
    }
    audit_logger.info(json.dumps(audit_entry))
    
    try:
        # Process query
        async for chunk in query_knowledge_base_stream(req):
            yield chunk
        
        # Log query success
        audit_logger.info(json.dumps({
            "timestamp": datetime.utcnow().isoformat(),
            "event": "query_success",
            "tenant_id": tenant_id,
        }))
    
    except Exception as e:
        # Log query failure
        audit_logger.error(json.dumps({
            "timestamp": datetime.utcnow().isoformat(),
            "event": "query_failure",
            "tenant_id": tenant_id,
            "error": str(e),
        }))
```

### Feedback Audit Trail

```python
async def log_feedback(req: FeedbackRequest, request: Request):
    tenant_id = request.state.tenant_id
    
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "tenant_id": tenant_id,
        "question_hash": hashlib.sha256(req.question.encode()).hexdigest(),
        "rating": req.rating,  # 0 = unhelpful, 1 = helpful
        "model_used": req.model_used,
    }
    
    # Write to JSONL (append-only)
    log_path = Path("feedback_log.jsonl")
    with log_path.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    
    logger.info(f"Feedback logged (tenant={tenant_id}, rating={entry['rating']})")
```

### Sending Logs to SIEM

```python
# fastapi_app/logging_config.py

import logging
import logging.handlers

# Send audit logs to syslog (ingested by SIEM)
syslog_handler = logging.handlers.SysLogHandler(
    address=('siem.acme-corp.com', 514),
    facility=logging.handlers.SysLogHandler.LOG_LOCAL0
)
audit_logger.addHandler(syslog_handler)
```

---

## 8. Deployment Security Checklist

### Before Production

- [ ] **Secrets**
  - [ ] All API keys in Secrets Manager (not .env)
  - [ ] .env not committed to git
  - [ ] .gitignore includes secrets files
  - [ ] Credentials rotated quarterly

- [ ] **Authentication**
  - [ ] API key validation enabled
  - [ ] Rate limiting enforced (per tenant)
  - [ ] JWT or OAuth2 considered (for future)

- [ ] **Data Residency**
  - [ ] All components in same region/facility
  - [ ] No external API calls
  - [ ] Data center compliance certified (SOC2, HIPAA if needed)

- [ ] **PII Handling**
  - [ ] Documents scanned for PII before upload
  - [ ] PII patterns filtered in retrieval
  - [ ] Audit trail includes PII-safe hashes

- [ ] **Encryption**
  - [ ] HTTPS enabled (TLS 1.2+)
  - [ ] At-rest encryption (encrypted volumes)
  - [ ] Qdrant encryption enabled
  - [ ] API keys encrypted in transit

- [ ] **Access Control**
  - [ ] File permissions (600 for secrets, 755 for code)
  - [ ] Firewall rules restrict access
  - [ ] Bastion host for SSH (no direct port 22)

- [ ] **Audit Logging**
  - [ ] All queries logged
  - [ ] All feedback logged
  - [ ] Logs sent to SIEM
  - [ ] Log retention policy (90–365 days)

- [ ] **Monitoring**
  - [ ] Health checks every 30s
  - [ ] Alerts on service degradation
  - [ ] Alerts on failed auth attempts
  - [ ] Dashboard for query metrics

---

## 9. Incident Response

### Security Incident Procedures

**If API key is compromised:**
```bash
# 1. Immediately revoke the key
TENANT_API_KEYS.delete("compromised-key-xxx")

# 2. Generate a new key for the tenant
new_key = secrets.token_urlsafe(32)

# 3. Notify the tenant (out-of-band)
# Email: "Your API key was rotated due to potential exposure. Use new key: ..."

# 4. Audit logs for suspicious activity
grep "compromised-key-xxx" audit.log | tail -20

# 5. Reset any rotated data if necessary
# (Qdrant data is safe; no external exposure possible)
```

**If a document is accidentally uploaded with PII:**
```bash
# 1. Identify the document
# ls -la internal_reports/

# 2. Remove it from Qdrant
# DELETE /qdrant/dashboard → select collection → delete by metadata

# 3. Remove the file
# rm internal_reports/sensitive_file.pdf

# 4. Force re-ingestion
# POST /ingest {"force_reload": true}

# 5. Audit log
# Check feedback_log.jsonl for any queries that may have retrieved PII
```

---

## 10. Compliance Artifacts

### Required for Audits

**Document Package:**
- [ ] Security Policy (this file)
- [ ] Data Processing Agreement (with Ollama/Qdrant)
- [ ] Incident Response Plan
- [ ] Audit logs (90–365 days)
- [ ] Access control matrix
- [ ] Network diagrams
- [ ] Encryption key management procedure

**Example DPA (Data Processing Agreement):**
```
Between: ACME Corp (Data Controller)
And: Ollama Community (Processor)

Scope:
- Ollama runs on ACME's infrastructure only
- No data shared with Ollama project maintainers
- ACME retains full control of data

This template can be adapted for compliance officers.
```

---

## 11. Security Best Practices Summary

| Practice | Status | Details |
|----------|--------|---------|
| **No External APIs** | ✅ | All processing local (on-prem or your cloud) |
| **API Key Auth** | ✅ | Per-tenant keys, rotated quarterly |
| **Rate Limiting** | ✅ | 100 queries/hour per tenant, configurable |
| **Encryption at Rest** | ✅ | Volumes encrypted, Qdrant encryption enabled |
| **Encryption in Transit** | ✅ | HTTPS/TLS 1.2+, self-signed for internal |
| **PII Detection** | ✅ | Regex + presidio, filtered from results |
| **Audit Logging** | ✅ | All queries logged, sent to SIEM |
| **Access Control** | ✅ | File permissions, firewall rules, secrets manager |
| **Incident Response** | ✅ | Documented procedures for key compromise, PII leakage |
| **Compliance** | ⚠️ | Ready for GDPR, HIPAA; requires SOC2/ISO27001 certification |

---

## Contact & Support

**Security Issue?**
- Do NOT open a public GitHub issue
- Email: security@acme-corp.local (replace with your domain)
- Include: description, reproduction steps, impact

**Compliance Questions?**
- Contact your Information Security team
- Refer to this document and ARCHITECTURE.md
- DPA template available upon request

---

**Next Step:** Read **[RAI.md](./RAI.md)** for responsible AI guardrails and cost controls.
