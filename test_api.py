#!/usr/bin/env python3
"""
Quick test script to verify the API server works.
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Set test API key if not set
if not os.getenv("THORDATA_API_KEY"):
    os.environ["THORDATA_API_KEY"] = "test-key"

from thordata_firecrawl.api import app

def test_health():
    """Test health endpoint."""
    from fastapi.testclient import TestClient
    
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    print("[OK] Health check passed")

def test_docs():
    """Test that docs are accessible."""
    from fastapi.testclient import TestClient

    client = TestClient(app)
    response = client.get("/docs")
    assert response.status_code == 200
    print("[OK] API docs accessible")


def test_crawl_async_job_flow():
    """Test async crawl job flow: submit -> poll."""
    from fastapi.testclient import TestClient
    from thordata_firecrawl import api as api_module

    # Monkeypatch the background crawl runner to avoid real network calls in unit tests.
    async def _fake_run(job_id: str, api_key: str) -> None:
        async with api_module._CRAWL_JOBS_LOCK:
            job = api_module._CRAWL_JOBS.get(job_id)
            if job is None:
                return
            job.status = "completed"
            job.total = 1
            job.completed = 1
            job.failed = 0
            job.data = [{"metadata": {"sourceUrl": job.request.url, "title": "Fake"}}]

    api_module._run_crawl_job = _fake_run  # type: ignore[attr-defined]

    client = TestClient(app)

    # Submit job
    resp = client.post(
        "/v1/crawl",
        headers={"Authorization": "Bearer test-key"},
        json={"url": "https://example.com", "limit": 1},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["success"] is True
    assert "id" in payload
    assert payload["url"].startswith("/v1/crawl/")

    job_id = payload["id"]

    # Poll job status
    status = client.get(f"/v1/crawl/{job_id}")
    assert status.status_code == 200
    body = status.json()
    assert body["status"] == "completed"
    assert body["completed"] == 1
    assert isinstance(body["data"], list)
    print("[OK] Async crawl job flow passed")


def test_crawl_pagination_and_cancel():
    """Test crawl status pagination and cancel endpoint."""
    from fastapi.testclient import TestClient
    from thordata_firecrawl import api as api_module

    async def _fake_run(job_id: str, api_key: str) -> None:
        async with api_module._CRAWL_JOBS_LOCK:
            job = api_module._CRAWL_JOBS.get(job_id)
            if job is None:
                return
            job.status = "completed"
            job.total = 200
            job.completed = 200
            job.data = [{"i": i} for i in range(200)]

    api_module._run_crawl_job = _fake_run  # type: ignore[attr-defined]

    client = TestClient(app)

    # Submit job
    resp = client.post(
        "/v1/crawl",
        headers={"Authorization": "Bearer test-key"},
        json={"url": "https://example.com", "limit": 200},
    )
    assert resp.status_code == 200
    job_id = resp.json()["id"]

    # Paginate
    page = client.get(f"/v1/crawl/{job_id}?offset=10&limit=5")
    assert page.status_code == 200
    body = page.json()
    assert len(body["data"]) == 5
    assert body["data"][0]["i"] == 10

    # Cancel already completed job should be idempotent
    cancel = client.post(f"/v1/crawl/{job_id}/cancel")
    assert cancel.status_code == 200
    assert cancel.json()["success"] is True
    print("[OK] Pagination and cancel passed")

if __name__ == "__main__":
    print("Testing Thordata Firecrawl API...")
    try:
        test_health()
        test_docs()
        test_crawl_async_job_flow()
        test_crawl_pagination_and_cancel()
        print("\n[OK] All tests passed! API server is ready.")
    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        sys.exit(1)
