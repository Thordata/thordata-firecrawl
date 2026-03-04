"""
FastAPI HTTP server for Thordata Firecrawl.

Provides REST API endpoints compatible with Firecrawl API structure.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Header, Depends
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
        options = {}
        if request.scrapeOptions:
            options.update(request.scrapeOptions)
            # Map Firecrawl options to Thordata options
            if "waitFor" in options:
                options["wait"] = options.pop("waitFor")
            # Our Python client expects `javascript` option (not `js_render`).
            # Keep the Firecrawl-style key name to avoid breaking scrape() behavior.
            if "javascript" in options:
                options["javascript"] = bool(options.get("javascript"))

        result = client.scrape(url=request.url, formats=request.formats, **options)
        return ScrapeResponse(success=True, data=result.get("data"))
    except Exception as e:
        return ScrapeResponse(success=False, error=str(e))


@app.post("/v1/crawl", response_model=CrawlStatusResponse)
async def crawl_submit(request: CrawlRequest, client: ThordataCrawl = Depends(get_client)):
    """Submit a crawl job (synchronous - returns results directly)."""
    try:
        options = {}
        if request.scrapeOptions:
            options.update(request.scrapeOptions)
        if "formats" not in options:
            options["formats"] = ["markdown"]

        result = client.crawl(
            url=request.url,
            limit=request.limit,
            maxDepth=request.maxDepth,
            includeSubdomains=request.includeSubdomains,
            **options,
        )

        # Return results directly (synchronous mode)
        # TODO: Implement async job queue for large crawls
        return CrawlStatusResponse(
            status=result.get("status", "completed"),
            total=result.get("total", 0),
            completed=result.get("completed", 0),
            failed=result.get("failed", 0),
            data=result.get("data", []),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/crawl/{job_id}", response_model=CrawlStatusResponse)
async def crawl_status(job_id: str, client: ThordataCrawl = Depends(get_client)):
    """Get crawl job status (placeholder - returns cached result for now)."""
    # TODO: Implement proper job queue and status tracking
    raise HTTPException(status_code=501, detail="Async crawl jobs not yet implemented. Use POST /v1/crawl for synchronous results.")


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
