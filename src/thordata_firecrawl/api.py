"""
FastAPI HTTP server for Thordata Firecrawl.

Provides REST API endpoints compatible with Firecrawl API structure.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Header, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .client import ThordataCrawl


# Request/Response Models
class ScrapeRequest(BaseModel):
    url: str
    formats: List[str] = Field(default=["markdown"], description="Output formats")
    scrapeOptions: Optional[Dict[str, Any]] = Field(default=None, alias="scrapeOptions")
    metadata: Optional[Dict[str, Any]] = None


class ScrapeResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class CrawlRequest(BaseModel):
    url: str
    limit: int = Field(default=100, ge=1, le=1000)
    scrapeOptions: Optional[Dict[str, Any]] = Field(default=None, alias="scrapeOptions")
    includeSubdomains: bool = Field(default=False, alias="includeSubdomains")
    maxDepth: Optional[int] = Field(default=None, alias="maxDepth", ge=1, le=10)


class CrawlJobResponse(BaseModel):
    success: bool
    id: str
    url: str


class CrawlStatusResponse(BaseModel):
    status: str
    total: int
    completed: int
    failed: Optional[int] = 0
    data: List[Dict[str, Any]]


# ============================================================================
# In-memory crawl job store (MVP)
# NOTE: This is process-local and will be reset on restart. Replace with Redis/DB
# for production deployments.
# ============================================================================


class _CrawlJob:
    def __init__(self, job_id: str, request: CrawlRequest) -> None:
        self.id = job_id
        self.request = request
        self.created_at = time.time()
        self.updated_at = self.created_at
        self.status: str = "queued"
        self.total: int = 0
        self.completed: int = 0
        self.failed: int = 0
        self.data: List[Dict[str, Any]] = []
        self.error: Optional[str] = None

    def to_status(self) -> CrawlStatusResponse:
        return CrawlStatusResponse(
            status=self.status,
            total=self.total,
            completed=self.completed,
            failed=self.failed,
            data=self.data,
        )


_CRAWL_JOBS: Dict[str, _CrawlJob] = {}
_CRAWL_JOBS_LOCK = asyncio.Lock()


def _job_ttl_seconds() -> int:
    try:
        return int(os.getenv("JOB_TTL_SECONDS", "3600"))
    except Exception:
        return 3600


def _max_concurrent_crawls() -> int:
    try:
        return int(os.getenv("MAX_CONCURRENT_CRAWLS", "2"))
    except Exception:
        return 2


async def _cleanup_expired_jobs() -> None:
    ttl = _job_ttl_seconds()
    now = time.time()
    async with _CRAWL_JOBS_LOCK:
        expired = [jid for jid, job in _CRAWL_JOBS.items() if (now - job.updated_at) > ttl]
        for jid in expired:
            _CRAWL_JOBS.pop(jid, None)


async def _running_jobs_count() -> int:
    async with _CRAWL_JOBS_LOCK:
        return sum(1 for j in _CRAWL_JOBS.values() if j.status == "running")


class MapRequest(BaseModel):
    url: str
    search: Optional[str] = None


class MapResponse(BaseModel):
    success: bool
    links: List[Dict[str, Any]]


class SearchRequest(BaseModel):
    query: str
    limit: int = Field(default=10, ge=1, le=100)
    engine: Optional[str] = "google"
    country: Optional[str] = None
    language: Optional[str] = None


class SearchResponse(BaseModel):
    success: bool
    data: Dict[str, Any]


class AgentRequest(BaseModel):
    prompt: str
    urls: Optional[List[str]] = None
    schema_: Optional[Dict[str, Any]] = Field(default=None, alias="schema")
    model: Optional[str] = None


class AgentResponse(BaseModel):
    success: bool
    data: Dict[str, Any]
    sources: List[str]
    error: Optional[str] = None


# FastAPI app
app = FastAPI(
    title="Thordata Firecrawl API",
    description="Turn any website into AI-ready data with a single API",
    version="0.1.0",
)


# Dependency: Get API key from header
def get_api_key(authorization: Optional[str] = Header(None)) -> str:
    """Extract API key from Authorization header."""
    if not authorization:
        # Fallback to environment variable
        api_key = os.getenv("THORDATA_API_KEY")
        if not api_key:
            raise HTTPException(status_code=401, detail="API key required")
        return api_key

    # Support both "Bearer <key>" and direct key
    if authorization.startswith("Bearer "):
        return authorization[7:]
    return authorization


# Dependency: Get client instance
def get_client(api_key: str = Depends(get_api_key)) -> ThordataCrawl:
    """Create ThordataCrawl client instance."""
    base_url = os.getenv("THORDATA_BASE_URL")
    return ThordataCrawl(api_key=api_key, base_url=base_url)


# Health check
@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


# API Endpoints
@app.post("/v1/scrape", response_model=ScrapeResponse)
async def scrape_endpoint(request: ScrapeRequest, client: ThordataCrawl = Depends(get_client)):
    """Scrape a single URL."""
    try:
        options: Dict[str, Any] = {}
        if request.scrapeOptions:
            options.update(request.scrapeOptions)
            # Firecrawl-ish to our Python client options
            # - waitFor -> wait (ms)
            if "waitFor" in options and "wait" not in options:
                options["wait"] = options.pop("waitFor")
            # - wait_for (css selector)
            if "wait_for" in options and "waitForSelector" not in options:
                options["waitForSelector"] = options.get("wait_for")
            # - javascript is a boolean
            if "javascript" in options:
                options["javascript"] = bool(options.get("javascript"))

        result = client.scrape(url=request.url, formats=request.formats, **options)
        return ScrapeResponse(success=True, data=result.get("data"))
    except Exception as e:
        return ScrapeResponse(success=False, error=str(e))


async def _run_crawl_job(job_id: str, api_key: str) -> None:
    # Build a client inside the background task to avoid relying on request-scoped dependencies.
    base_url = os.getenv("THORDATA_BASE_URL")
    client = ThordataCrawl(api_key=api_key, base_url=base_url)

    async with _CRAWL_JOBS_LOCK:
        job = _CRAWL_JOBS.get(job_id)
        if job is None:
            return
        job.status = "running"
        job.updated_at = time.time()

    try:
        options: Dict[str, Any] = {}
        if job.request.scrapeOptions:
            options.update(job.request.scrapeOptions)
        if "formats" not in options:
            options["formats"] = ["markdown"]

        # If user cancelled before we start the expensive work, exit early.
        async with _CRAWL_JOBS_LOCK:
            job = _CRAWL_JOBS.get(job_id)
            if job is None or job.status == "cancelled":
                return

        result = client.crawl(
            url=job.request.url,
            limit=job.request.limit,
            maxDepth=job.request.maxDepth,
            includeSubdomains=job.request.includeSubdomains,
            **options,
        )

        async with _CRAWL_JOBS_LOCK:
            job = _CRAWL_JOBS.get(job_id)
            if job is None:
                return
            if job.status == "cancelled":
                # Do not overwrite cancelled state.
                job.updated_at = time.time()
                return
            job.status = "completed"
            job.total = int(result.get("total", 0) or 0)
            job.completed = int(result.get("completed", 0) or 0)
            job.failed = int(result.get("failed", 0) or 0)
            job.data = list(result.get("data", []) or [])
            job.updated_at = time.time()

    except Exception as e:
        async with _CRAWL_JOBS_LOCK:
            job = _CRAWL_JOBS.get(job_id)
            if job is None:
                return
            job.status = "failed"
            job.error = str(e)
            job.updated_at = time.time()


@app.post("/v1/crawl", response_model=CrawlJobResponse)
async def crawl_submit(
    request: CrawlRequest,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(get_api_key),
):
    """Submit an async crawl job. Use GET /v1/crawl/{id} to poll status/results."""
    await _cleanup_expired_jobs()

    running = await _running_jobs_count()
    if running >= _max_concurrent_crawls():
        raise HTTPException(status_code=429, detail="Too many concurrent crawl jobs")

    job_id = uuid.uuid4().hex
    job = _CrawlJob(job_id, request)

    async with _CRAWL_JOBS_LOCK:
        _CRAWL_JOBS[job_id] = job

    background_tasks.add_task(_run_crawl_job, job_id, api_key)

    return CrawlJobResponse(success=True, id=job_id, url=f"/v1/crawl/{job_id}")


@app.get("/v1/crawl/{job_id}", response_model=CrawlStatusResponse)
async def crawl_status(
    job_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    """Get crawl job status and results (supports pagination)."""
    await _cleanup_expired_jobs()

    async with _CRAWL_JOBS_LOCK:
        job = _CRAWL_JOBS.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Crawl job not found")
        if job.status == "failed" and job.error:
            raise HTTPException(status_code=500, detail=job.error)

        data_slice = job.data[offset : offset + limit]
        return CrawlStatusResponse(
            status=job.status,
            total=job.total,
            completed=job.completed,
            failed=job.failed,
            data=data_slice,
        )


@app.post("/v1/crawl/{job_id}/cancel")
async def crawl_cancel(job_id: str):
    """Cancel a crawl job (best-effort)."""
    await _cleanup_expired_jobs()
    async with _CRAWL_JOBS_LOCK:
        job = _CRAWL_JOBS.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Crawl job not found")
        if job.status in {"completed", "failed", "cancelled"}:
            return {"success": True, "status": job.status}
        job.status = "cancelled"
        job.updated_at = time.time()
        return {"success": True, "status": "cancelled"}


@app.post("/v1/map", response_model=MapResponse)
async def map_endpoint(request: MapRequest, client: ThordataCrawl = Depends(get_client)):
    """Discover URLs on a website."""
    try:
        result = client.map(url=request.url, search=request.search)
        return MapResponse(success=True, links=result.get("links", []))
    except Exception as e:
        return MapResponse(success=False, links=[])


@app.post("/v1/search", response_model=SearchResponse)
async def search_endpoint(request: SearchRequest, client: ThordataCrawl = Depends(get_client)):
    """Search the web."""
    try:
        result = client.search(
            query=request.query,
            limit=request.limit,
            engine=request.engine,
            country=request.country,
            language=request.language,
        )
        return SearchResponse(success=True, data=result.get("data", {}))
    except Exception as e:
        return SearchResponse(success=False, data={"error": str(e)})


@app.post("/v1/agent", response_model=AgentResponse)
async def agent_endpoint(request: AgentRequest, client: ThordataCrawl = Depends(get_client)):
    """Run an agent task for structured extraction."""
    try:
        result = client.agent(
            prompt=request.prompt,
            urls=request.urls,
            schema=request.schema_,
            model=request.model,
        )
        if result.get("success"):
            return AgentResponse(
                success=True,
                data=result.get("data", {}),
                sources=result.get("sources", []),
            )
        else:
            return AgentResponse(
                success=False,
                data={},
                sources=result.get("sources", []),
                error=result.get("error", "Unknown error"),
            )
    except Exception as e:
        return AgentResponse(
            success=False,
            data={},
            sources=[],
            error=str(e),
        )


# Run server
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "3002"))
    uvicorn.run(app, host="0.0.0.0", port=port)
