"""
Smoke tests for Consultant Knowledge RAG.

Run with: pytest tests/ -v
Run with coverage: pytest tests/ --cov=fastapi_app --cov=rag_engine
"""

import pytest
import asyncio
import json
from httpx import AsyncClient
from pathlib import Path

# Fixtures and setup
@pytest.fixture
async def client():
    """Create test client."""
    from fastapi_app.main import app
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


class TestHealth:
    """Health check tests."""
    
    @pytest.mark.asyncio
    async def test_health_check(self, client):
        """Test GET /health endpoint."""
        response = await client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data
        assert data["status"] in ["ok", "degraded"]
        assert "ollama_reachable" in data
        assert "qdrant_ready" in data


class TestKnowledgeBase:
    """Knowledge base status tests."""
    
    @pytest.mark.asyncio
    async def test_kb_status(self, client):
        """Test GET /status endpoint."""
        response = await client.get("/status")
        assert response.status_code == 200
        
        data = response.json()
        assert "total_vectors" in data
        assert "embed_model" in data
        assert "llm_model" in data
        assert "collection_name" in data
        assert isinstance(data["total_vectors"], int)


class TestIngestion:
    """Document ingestion tests."""
    
    @pytest.mark.asyncio
    async def test_ingest_request(self, client):
        """Test POST /ingest endpoint."""
        payload = {"force_reload": False}
        response = await client.post("/ingest", json=payload)
        
        # Accept 200 (success) or 422 (no documents) as valid
        assert response.status_code in [200, 422]
        
        if response.status_code == 200:
            data = response.json()
            assert "status" in data
            assert "files_processed" in data or "chunks_added" in data


class TestQuery:
    """Query pipeline tests."""
    
    @pytest.mark.asyncio
    async def test_query_stream_endpoint_exists(self, client):
        """Test that /query/stream endpoint exists."""
        payload = {"question": "hello"}
        response = await client.post("/query/stream", json=payload)
        
        # Should return 200 or error if services not available
        # Just check endpoint exists and returns expected format
        assert response.status_code in [200, 500, 503]
    
    @pytest.mark.asyncio
    async def test_query_streaming_format(self, client):
        """Test that streaming response is NDJSON."""
        payload = {"question": "What is your purpose?"}
        response = await client.post("/query/stream", json=payload)
        
        if response.status_code == 200:
            # Response should be NDJSON (newline-delimited JSON)
            lines = response.text.strip().split("\n")
            for line in lines:
                if line:
                    data = json.loads(line)
                    assert "type" in data
                    assert data["type"] in ["chunk", "meta", "error"]
    
    @pytest.mark.asyncio
    async def test_query_validation(self, client):
        """Test query validation."""
        # Empty question should be rejected
        payload = {"question": ""}
        response = await client.post("/query/stream", json=payload)
        assert response.status_code == 422  # Unprocessable Entity


class TestFeedback:
    """Feedback logging tests."""
    
    @pytest.mark.asyncio
    async def test_feedback_submission(self, client):
        """Test POST /feedback endpoint."""
        payload = {
            "question": "Test question",
            "answer": "Test answer",
            "rating": 1,
            "model_used": "qwen2.5:3b"
        }
        response = await client.post("/feedback", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "ok"
    
    @pytest.mark.asyncio
    async def test_feedback_log_file(self, client):
        """Test that feedback is logged to file."""
        # Submit feedback
        payload = {
            "question": "Test",
            "answer": "Test answer",
            "rating": 1,
            "model_used": "qwen2.5:3b"
        }
        await client.post("/feedback", json=payload)
        
        # Check feedback_log.jsonl exists
        log_path = Path("feedback_log.jsonl")
        assert log_path.exists()
        
        # Verify last entry
        with open(log_path) as f:
            lines = f.readlines()
            if lines:
                last_entry = json.loads(lines[-1])
                assert last_entry["rating"] in [0, 1]


class TestErrorHandling:
    """Error handling tests."""
    
    @pytest.mark.asyncio
    async def test_invalid_json(self, client):
        """Test handling of invalid JSON."""
        response = await client.post(
            "/query/stream",
            content="invalid json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code in [400, 422]
    
    @pytest.mark.asyncio
    async def test_missing_required_field(self, client):
        """Test handling of missing required fields."""
        payload = {"top_k": 4}  # Missing 'question'
        response = await client.post("/query/stream", json=payload)
        assert response.status_code == 422


class TestIntegration:
    """Integration tests (end-to-end).
    
    Note: These require full stack (Ollama + Qdrant) running.
    Mark with @pytest.mark.integration to skip in CI if needed.
    """
    
    @pytest.mark.asyncio
    async def test_full_query_pipeline(self, client):
        """Test complete query pipeline (if services available)."""
        # Check health first
        health = await client.get("/health")
        if health.status_code != 200 or not health.json()["ollama_reachable"]:
            pytest.skip("Ollama service not available")
        
        # Submit a query
        payload = {"question": "Hello, how are you?"}
        response = await client.post("/query/stream", json=payload)
        
        assert response.status_code == 200
        # Should contain at least one JSON object
        lines = [l for l in response.text.strip().split("\n") if l]
        assert len(lines) > 0


# Configuration for pytest
def pytest_configure(config):
    """Configure pytest."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration (requires full stack)"
    )


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
