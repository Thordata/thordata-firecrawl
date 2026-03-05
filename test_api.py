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

def test_openapi_contains_new_endpoints():
    """Sanity check OpenAPI contains newer endpoints."""
    from fastapi.testclient import TestClient

    client = TestClient(app)
    spec = client.get("/openapi.json").json()
    paths = spec.get("paths", {})
    assert "/v1/batch-scrape" in paths
    assert "/v1/search-and-scrape" in paths
    print("[OK] OpenAPI contains new endpoints")

def test_openapi_agent_request_includes_scrapeoptions_and_formats():
    """Ensure /v1/agent request includes new convenience fields."""
    from fastapi.testclient import TestClient

    client = TestClient(app)
    spec = client.get("/openapi.json").json()
    agent_schema_ref = spec["paths"]["/v1/agent"]["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    # Resolve #/components/schemas/AgentRequest
    name = agent_schema_ref.split("/")[-1]
    agent_schema = spec["components"]["schemas"][name]
    props = agent_schema.get("properties", {})
    assert "scrapeOptions" in props
    assert "formats" in props
    assert "searchLimit" in props
    print("[OK] OpenAPI agent request includes scrapeOptions/formats/searchLimit")


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



def test_crawl_url_filtering_rules():
    """Test include/exclude filtering in BFS crawler (no network)."""
    from thordata_firecrawl._crawler import crawl_bfs

    pages = {
        "https://example.com/": '<html><body>'
        '<a href="/docs/intro">intro</a>'
        '<a href="/docs/hidden">hidden</a>'
        '<a href="/blog/post1">post1</a>'
        '</body></html>',
        "https://example.com/docs/intro": '<html><body><a href="/docs/hidden">h</a></body></html>',
        "https://example.com/blog/post1": '<html><body>blog</body></html>',
        "https://example.com/docs/hidden": '<html><body>secret</body></html>',
    }

    def fake_scrape(url: str, formats, **opts):
        html = pages.get(url, '')
        return {
            "success": True,
            "data": {
                "html": html,
                "markdown": "md",
                "screenshot": None,
            },
        }

    r = crawl_bfs(
        scrape_func=fake_scrape,
        seed_url="https://example.com/",
        limit=10,
        max_depth=2,
        include_subdomains=False,
        formats=["html", "markdown"],
        concurrency=1,
        include_paths=["/docs/*"],
        exclude_paths=["*/hidden"],
    )

    urls = sorted([x.get("metadata", {}).get("sourceUrl") for x in r.get("data", [])])
    assert "https://example.com/" in urls
    assert "https://example.com/docs/intro" in urls
    assert "https://example.com/docs/hidden" not in urls
    assert "https://example.com/blog/post1" not in urls
    print("[OK] Crawl include/exclude filtering works")


def test_openapi_crawl_request_includes_webhook_and_filters():
    """Ensure /v1/crawl request exposes webhook + include/exclude patterns."""
    from fastapi.testclient import TestClient

    client = TestClient(app)
    spec = client.get("/openapi.json").json()
    crawl_schema_ref = spec["paths"]["/v1/crawl"]["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    name = crawl_schema_ref.split("/")[-1]
    crawl_schema = spec["components"]["schemas"][name]
    props = crawl_schema.get("properties", {})
    assert "includePaths" in props
    assert "excludePaths" in props
    assert "webhook" in props
    print("[OK] OpenAPI crawl request includes webhook/includePaths/excludePaths")


def test_webhook_config_accepts_new_fields():
    """Test that webhook config accepts timeout, maxRetries, includeData."""
    from fastapi.testclient import TestClient
    from thordata_firecrawl import api as api_module

    async def _fake_run(job_id: str, api_key: str) -> None:
        async with api_module._CRAWL_JOBS_LOCK:
            job = api_module._CRAWL_JOBS.get(job_id)
            if job is None:
                return
            job.status = "completed"
            job.total = 1
            job.completed = 1
            job.data = [{"test": "data"}]

    api_module._run_crawl_job = _fake_run  # type: ignore[attr-defined]

    client = TestClient(app)

    # Submit job with full webhook config
    resp = client.post(
        "/v1/crawl",
        headers={"Authorization": "Bearer test-key"},
        json={
            "url": "https://example.com",
            "limit": 1,
            "webhook": {
                "url": "https://example.com/webhook",
                "headers": {"Authorization": "Bearer token"},
                "secret": "test-secret",
                "timeout": 15,
                "maxRetries": 5,
                "includeData": False
            }
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["success"] is True
    print("[OK] Webhook config accepts timeout/maxRetries/includeData")


def test_crawl_idempotency():
    """Test that clientJobId provides idempotency for crawl jobs."""
    from fastapi.testclient import TestClient
    from thordata_firecrawl import api as api_module

    async def _fake_run(job_id: str, api_key: str) -> None:
        async with api_module._CRAWL_JOBS_LOCK:
            job = api_module._CRAWL_JOBS.get(job_id)
            if job is None:
                return
            job.status = "completed"
            job.total = 1
            job.completed = 1
            job.data = [{"test": "data"}]

    api_module._run_crawl_job = _fake_run  # type: ignore[attr-defined]

    client = TestClient(app)
    client_job_id = "test-unique-id-123"

    # First submission
    resp1 = client.post(
        "/v1/crawl",
        headers={"Authorization": "Bearer test-key"},
        params={"clientJobId": client_job_id},
        json={"url": "https://example.com", "limit": 1},
    )
    assert resp1.status_code == 200
    job_id_1 = resp1.json()["id"]

    # Second submission with same clientJobId should return same job_id
    resp2 = client.post(
        "/v1/crawl",
        headers={"Authorization": "Bearer test-key"},
        params={"clientJobId": client_job_id},
        json={"url": "https://example.com", "limit": 1},
    )
    assert resp2.status_code == 200
    job_id_2 = resp2.json()["id"]
    assert job_id_1 == job_id_2, "Idempotency should return same job_id"
    print("[OK] Crawl idempotency works with clientJobId")
if __name__ == "__main__":
    print("Testing Thordata Firecrawl API...")
    try:
        test_health()
        test_docs()
        test_openapi_contains_new_endpoints()
        test_openapi_agent_request_includes_scrapeoptions_and_formats()
        test_openapi_crawl_request_includes_webhook_and_filters()
        test_webhook_config_accepts_new_fields()
        test_crawl_idempotency()
        test_crawl_url_filtering_rules()
        test_crawl_async_job_flow()
        test_crawl_pagination_and_cancel()
        print("\n[OK] All tests passed! API server is ready.")
    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        sys.exit(1)
