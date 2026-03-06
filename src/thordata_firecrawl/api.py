"""
FastAPI HTTP server for Thordata Firecrawl.

Provides REST API endpoints compatible with Firecrawl API structure.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
import json
import hashlib
import hmac
import urllib.request
import urllib.error
import logging
import re
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from urllib.parse import urlparse

from fastapi import BackgroundTasks, FastAPI, HTTPException, Header, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator

from .client import ThordataCrawl

# Configure structured logging
_log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("thordata_firecrawl")

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency at runtime
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv()


# Validation helpers
def validate_url(url: str) -> str:
    """Validate URL format."""
    if not url or not isinstance(url, str):
        raise ValueError("URL is required and must be a string")
    
    # Basic URL format check
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid URL format: {url}")
    
    # Only allow http/https
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"URL scheme must be http or https, got: {parsed.scheme}")
    
    return url


def validate_urls(urls: List[str]) -> List[str]:
    """Validate a list of URLs."""
    if not urls:
        raise ValueError("At least one URL is required")
    
    if len(urls) > 100:  # Reasonable limit for batch operations
        raise ValueError(f"Too many URLs (max 100), got {len(urls)}")
    
    validated = []
    for url in urls:
        validated.append(validate_url(url))
    
    return validated


# Request/Response Models
class ScrapeRequest(BaseModel):
    url: str
    formats: List[str] = Field(default=["markdown"], description="Output formats")
    scrapeOptions: Optional[Dict[str, Any]] = Field(default=None, alias="scrapeOptions")
    metadata: Optional[Dict[str, Any]] = None
    
    @validator("url")
    def validate_url_field(cls, v):
        return validate_url(v)
    
    @validator("formats")
    def validate_formats(cls, v):
        if not v:
            raise ValueError("At least one format is required")
        allowed = {"markdown", "html", "screenshot", "json"}
        invalid = set(v) - allowed
        if invalid:
            raise ValueError(f"Invalid formats: {invalid}. Allowed: {allowed}")
        return v


class ScrapeResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class BatchScrapeRequest(BaseModel):
    urls: List[str]
    formats: List[str] = Field(default=["markdown"], description="Output formats")
    scrapeOptions: Optional[Dict[str, Any]] = Field(default=None, alias="scrapeOptions")
    metadata: Optional[Dict[str, Any]] = None
    
    @validator("urls")
    def validate_urls_field(cls, v):
        return validate_urls(v)
    
    @validator("formats")
    def validate_formats(cls, v):
        if not v:
            raise ValueError("At least one format is required")
        allowed = {"markdown", "html", "screenshot", "json"}
        invalid = set(v) - allowed
        if invalid:
            raise ValueError(f"Invalid formats: {invalid}. Allowed: {allowed}")
        return v


class BatchScrapeResponse(BaseModel):
    success: bool
    results: List[Dict[str, Any]]
    error: Optional[str] = None


class WebhookConfig(BaseModel):
    url: str = Field(description="Webhook URL to POST crawl job events to")
    headers: Optional[Dict[str, str]] = Field(default=None, description="Optional extra headers for webhook request")
    secret: Optional[str] = Field(default=None, description="Optional secret for HMAC-SHA256 signature")
    timeout: Optional[int] = Field(default=10, ge=1, le=60, description="Request timeout in seconds (default: 10)")
    maxRetries: Optional[int] = Field(default=3, ge=0, le=10, alias="maxRetries", description="Maximum retry attempts (default: 3)")
    includeData: Optional[bool] = Field(default=True, alias="includeData", description="Include full data array in payload (default: true). Set to false for large crawls to reduce webhook payload size.")


class CrawlRequest(BaseModel):
    url: str
    limit: int = Field(default=100, ge=1, le=1000)
    scrapeOptions: Optional[Dict[str, Any]] = Field(default=None, alias="scrapeOptions")
    includeSubdomains: bool = Field(default=False, alias="includeSubdomains")
    maxDepth: Optional[int] = Field(default=None, alias="maxDepth", ge=1, le=10)
    includePaths: Optional[List[str]] = Field(default=None, alias="includePaths", description="Only crawl URLs whose path matches any of these wildcard patterns (fnmatch)")
    excludePaths: Optional[List[str]] = Field(default=None, alias="excludePaths", description="Do not crawl URLs whose path matches any of these wildcard patterns (fnmatch)")
    webhook: Optional[WebhookConfig] = Field(default=None, description="Optional webhook to receive crawl job completion/failure events")
    
    @validator("url")
    def validate_url_field(cls, v):
        return validate_url(v)


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
        self.client_job_id: Optional[str] = None  # For idempotency

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
    
    @validator("url")
    def validate_url_field(cls, v):
        return validate_url(v)


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


class SearchAndScrapeRequest(BaseModel):
    query: str
    searchLimit: int = Field(default=5, ge=1, le=20, alias="searchLimit")
    formats: List[str] = Field(default=["markdown"], description="Output formats for scraping")
    scrapeOptions: Optional[Dict[str, Any]] = Field(default=None, alias="scrapeOptions")


class SearchAndScrapeResponse(BaseModel):
    success: bool
    query: str
    results: List[Dict[str, Any]]
    error: Optional[str] = None


class AgentRequest(BaseModel):
    prompt: str
    urls: Optional[List[str]] = None
    schema_: Optional[Dict[str, Any]] = Field(default=None, alias="schema")
    model: Optional[str] = None
    searchLimit: int = Field(default=3, ge=1, le=10, alias="searchLimit")
    formats: List[str] = Field(default=["markdown"], description="Formats to scrape for context")
    scrapeOptions: Optional[Dict[str, Any]] = Field(default=None, alias="scrapeOptions")
    
    @validator("prompt")
    def validate_prompt(cls, v):
        if not v or not isinstance(v, str) or len(v.strip()) == 0:
            raise ValueError("Prompt is required and cannot be empty")
        if len(v) > 10000:  # Reasonable limit
            raise ValueError(f"Prompt too long (max 10000 characters), got {len(v)}")
        return v.strip()
    
    @validator("urls")
    def validate_urls_field(cls, v):
        if v is None:
            return v
        return validate_urls(v)
    
    @validator("formats")
    def validate_formats(cls, v):
        if not v:
            raise ValueError("At least one format is required")
        allowed = {"markdown", "html", "screenshot", "json"}
        invalid = set(v) - allowed
        if invalid:
            raise ValueError(f"Invalid formats: {invalid}. Allowed: {allowed}")
        return v


class AgentResponse(BaseModel):
    success: bool
    data: Dict[str, Any]
    sources: List[str]
    error: Optional[str] = None


# Rate Limiting
class RateLimiter:
    """Simple in-memory rate limiter using sliding window algorithm."""
    
    def __init__(self):
        # Store request timestamps per key (token or IP)
        self._requests: Dict[str, deque] = defaultdict(lambda: deque())
        self._lock = asyncio.Lock()
    
    async def check_rate_limit(
        self, 
        key: str, 
        max_requests: int, 
        window_seconds: int
    ) -> tuple[bool, Optional[int]]:
        """
        Check if request is allowed.
        
        Returns:
            (allowed, retry_after_seconds)
        """
        async with self._lock:
            now = time.time()
            window_start = now - window_seconds
            
            # Clean old requests outside the window
            requests = self._requests[key]
            while requests and requests[0] < window_start:
                requests.popleft()
            
            # Check if limit exceeded
            if len(requests) >= max_requests:
                # Calculate retry after (time until oldest request expires)
                if requests:
                    retry_after = int(requests[0] + window_seconds - now) + 1
                    return False, max(1, retry_after)
                return False, window_seconds
            
            # Add current request
            requests.append(now)
            return True, None
    
    async def reset(self, key: str) -> None:
        """Reset rate limit for a key (for testing/admin purposes)."""
        async with self._lock:
            self._requests.pop(key, None)


# Global rate limiter instance
_rate_limiter = RateLimiter()


def _get_rate_limit_config() -> Dict[str, int]:
    """Get rate limit configuration from environment variables."""
    # Per-token limits (requests per minute)
    token_rpm = int(os.getenv("RATE_LIMIT_TOKEN_RPM", "60"))
    # Per-IP limits (requests per minute)
    ip_rpm = int(os.getenv("RATE_LIMIT_IP_RPM", "120"))
    # Window size in seconds (default: 60 seconds = 1 minute)
    window_seconds = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
    
    return {
        "token_rpm": token_rpm,
        "ip_rpm": ip_rpm,
        "window_seconds": window_seconds,
    }


def _get_max_response_size() -> int:
    """Get maximum response size in bytes from environment variable."""
    # Default: 10MB (10 * 1024 * 1024)
    default_size = 10 * 1024 * 1024
    try:
        return int(os.getenv("MAX_RESPONSE_SIZE", str(default_size)))
    except Exception:
        return default_size


def _check_response_size(response_data: Any, max_size: int) -> tuple[bool, Optional[str]]:
    """
    Check if response data exceeds size limit.
    
    Returns:
        (within_limit, error_message)
    """
    try:
        # Serialize to JSON to estimate size
        json_str = json.dumps(response_data, ensure_ascii=False)
        size_bytes = len(json_str.encode("utf-8"))
        
        if size_bytes > max_size:
            size_mb = size_bytes / (1024 * 1024)
            max_mb = max_size / (1024 * 1024)
            return False, f"Response size ({size_mb:.2f}MB) exceeds limit ({max_mb:.2f}MB). Consider using pagination or reducing data."
        return True, None
    except Exception as e:
        # If serialization fails, log but don't block
        logger.warning(f"Failed to check response size: {str(e)}")
        return True, None


async def check_rate_limit(request: Request, api_key: Optional[str] = None) -> None:
    """Dependency to check rate limits (per-token and per-IP)."""
    config = _get_rate_limit_config()
    
    # Get client IP
    client_ip = request.client.host if request.client else "unknown"
    
    # Check per-IP limit
    allowed, retry_after = await _rate_limiter.check_rate_limit(
        key=f"ip:{client_ip}",
        max_requests=config["ip_rpm"],
        window_seconds=config["window_seconds"],
    )
    if not allowed:
        logger.warning(f"Rate limit exceeded: IP={client_ip}, retry_after={retry_after}s")
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Please retry after {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )
    
    # Check per-token limit (if API key provided)
    if api_key:
        # Use hash of API key for privacy
        token_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]
        allowed, retry_after = await _rate_limiter.check_rate_limit(
            key=f"token:{token_hash}",
            max_requests=config["token_rpm"],
            window_seconds=config["window_seconds"],
        )
        if not allowed:
            logger.warning(f"Rate limit exceeded: token_hash={token_hash}, retry_after={retry_after}s")
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Please retry after {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )


# FastAPI app
app = FastAPI(
    title="Thordata Firecrawl API",
    description="Turn any website into AI-ready data with a single API",
    version="0.1.0",
)


# CORS configuration so that GitHub Pages playground and local/static sites can call the API.
# - If CORS_ALLOW_ORIGINS is set, we honor that (comma-separated list) and allow credentials.
# - Otherwise, we allow all origins without credentials (API key is sent in header, not cookies).
_cors_origins_env = os.getenv("CORS_ALLOW_ORIGINS")
if _cors_origins_env:
    _allowed_origins = [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
    _allow_credentials = True
else:
    _allowed_origins = ["*"]
    _allow_credentials = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Dependency: Get API key from header
def get_api_key(authorization: Optional[str] = Header(None)) -> str:
    """Extract API key from Authorization header."""
    if not authorization:
        # Fallback to environment variables (both naming conventions supported)
        api_key = os.getenv("THORDATA_API_KEY") or os.getenv("THORDATA_SCRAPER_TOKEN")
        if not api_key:
            raise HTTPException(
                status_code=401,
                detail="API key required (THORDATA_API_KEY or THORDATA_SCRAPER_TOKEN)",
            )
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


@app.get("/", response_class=HTMLResponse)
async def root() -> str:
    return """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>Thordata Firecrawl API</title>
    <style>
      body { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial; margin: 24px; color: #111827; }
      code { background: #f3f4f6; padding: 2px 6px; border-radius: 6px; }
      a { color: #2563eb; text-decoration: none; }
      a:hover { text-decoration: underline; }
      .card { border: 1px solid #e5e7eb; border-radius: 12px; padding: 16px; max-width: 920px; }
      .muted { color: #6b7280; }
      ul { line-height: 1.7; }
    </style>
  </head>
  <body>
    <div class="card">
      <h2 style="margin: 0 0 8px 0;">🔥 Thordata Firecrawl API</h2>
      <div class="muted">Local helper page for quick testing (no domain / no fancy website required).</div>
      <ul>
        <li><a href="/docs">Swagger UI</a> (interactive API docs)</li>
        <li><a href="/redoc">ReDoc</a></li>
        <li><a href="/playground">Playground</a> (copy/paste friendly)</li>
        <li><a href="/openapi.json">OpenAPI JSON</a></li>
        <li><code>GET /health</code> → {"status":"ok"}</li>
      </ul>
    </div>
  </body>
</html>
""".strip()


@app.get("/playground", response_class=HTMLResponse)
async def playground() -> str:
    # Minimal local playground so new users can "just use it" without learning Swagger first.
    return """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>Thordata Firecrawl Playground</title>
    <style>
      body { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial; margin: 24px; color: #111827; }
      input, textarea, select, button { font: inherit; }
      .row { display: flex; gap: 12px; flex-wrap: wrap; }
      .col { flex: 1; min-width: 320px; }
      .card { border: 1px solid #e5e7eb; border-radius: 12px; padding: 16px; }
      label { display:block; font-weight: 600; margin: 8px 0 6px; }
      input[type=text], textarea, select { width: 100%; padding: 10px 12px; border-radius: 10px; border: 1px solid #d1d5db; }
      textarea { min-height: 160px; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; }
      button { padding: 10px 14px; border-radius: 10px; border: 1px solid #111827; background: #111827; color: white; cursor: pointer; }
      button.secondary { background: white; color: #111827; border-color: #d1d5db; }
      .muted { color: #6b7280; font-size: 13px; line-height: 1.4; }
      pre { background: #0b1020; color: #e5e7eb; padding: 12px; border-radius: 12px; overflow: auto; }
      code { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; }
      .ok { color: #16a34a; }
      .bad { color: #dc2626; }
      a { color: #2563eb; text-decoration: none; }
      a:hover { text-decoration: underline; }
    </style>
  </head>
  <body>
    <div class="card" style="margin-bottom: 12px;">
      <div style="display:flex; justify-content:space-between; align-items:center; gap: 12px; flex-wrap: wrap;">
        <div>
          <h2 style="margin:0;">🧪 Thordata Firecrawl Playground</h2>
          <div class="muted">Tip: If you have <code>THORDATA_SCRAPER_TOKEN</code>, use it (Universal API requires scraper_token for clean markdown/html).</div>
        </div>
        <div class="muted">
          <a href="/docs">Swagger UI</a> · <a href="/">Home</a>
        </div>
      </div>
    </div>

    <div class="row">
      <div class="col">
        <div class="card">
          <label>Authorization (Bearer token)</label>
          <input id="token" type="text" placeholder="paste token here (stored in your browser localStorage)" />
          <div class="muted">This page runs locally. The token is only stored in your browser's localStorage.</div>

          <label style="margin-top: 14px;">Endpoint</label>
          <select id="endpoint">
            <option value="/v1/scrape">POST /v1/scrape</option>
            <option value="/v1/batch-scrape">POST /v1/batch-scrape</option>
            <option value="/v1/map">POST /v1/map</option>
            <option value="/v1/search">POST /v1/search</option>
            <option value="/v1/search-and-scrape">POST /v1/search-and-scrape</option>
            <option value="/v1/crawl">POST /v1/crawl (async job)</option>
            <option value="/v1/agent">POST /v1/agent</option>
          </select>

          <label style="margin-top: 14px;">JSON Body</label>
          <textarea id="body"></textarea>

          <div style="margin-top: 12px; display:flex; gap: 10px; flex-wrap: wrap;">
            <button id="send">Send</button>
            <button id="fill" class="secondary">Fill example</button>
            <button id="clear" class="secondary">Clear</button>
          </div>

          <div class="muted" style="margin-top: 12px;">
            For crawl jobs, copy the returned <code>id</code> and call <code>GET /v1/crawl/{id}</code> in Swagger UI or curl.
          </div>
        </div>
      </div>

      <div class="col">
        <div class="card">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <div style="font-weight:600;">Response</div>
            <div id="status" class="muted"></div>
          </div>
          <pre id="out"><code>// click "Fill example" then "Send"</code></pre>
        </div>
      </div>
    </div>

    <script>
      const tokenEl = document.getElementById("token");
      const endpointEl = document.getElementById("endpoint");
      const bodyEl = document.getElementById("body");
      const outEl = document.getElementById("out");
      const statusEl = document.getElementById("status");

      const LS_KEY = "thordata_firecrawl_token";
      tokenEl.value = localStorage.getItem(LS_KEY) || "";
      tokenEl.addEventListener("input", () => localStorage.setItem(LS_KEY, tokenEl.value || ""));

      function setExample() {
        const ep = endpointEl.value;
        let example = {};
        if (ep === "/v1/scrape") {
          example = { url: "https://www.thordata.com", formats: ["markdown"], scrapeOptions: { javascript: true } };
        } else if (ep === "/v1/batch-scrape") {
          example = { urls: ["https://www.thordata.com", "https://www.thordata.com/about"], formats: ["markdown"], scrapeOptions: { javascript: true } };
        } else if (ep === "/v1/map") {
          example = { url: "https://www.thordata.com" };
        } else if (ep === "/v1/search") {
          example = { query: "Thordata web data API", limit: 5, engine: "google" };
        } else if (ep === "/v1/search-and-scrape") {
          example = { query: "Thordata web data API", searchLimit: 3, formats: ["markdown"], scrapeOptions: { javascript: true } };
        } else if (ep === "/v1/crawl") {
          example = {
            url: "https://www.thordata.com",
            limit: 20,
            maxDepth: 2,
            includeSubdomains: false,
            includePaths: ["/*"],
            excludePaths: ["/privacy*", "/terms*"],
            webhook: {
              url: "https://example.com/webhook",
              headers: { "Authorization": "Bearer YOUR_WEBHOOK_TOKEN" },
              secret: "YOUR_WEBHOOK_SECRET",
              timeout: 10,
              maxRetries: 3,
              includeData: true
            },
            scrapeOptions: { javascript: true, formats: ["markdown"] }
          };
        } else if (ep === "/v1/agent") {
          example = {
            urls: ["https://www.thordata.com"],
            prompt: "Extract basic company information (name, tagline).",
            schema: {
              type: "object",
              properties: {
                name: { type: "string" },
                tagline: { type: "string" }
              }
            }
          };
        }
        bodyEl.value = JSON.stringify(example, null, 2);
      }

      async function send() {
        const ep = endpointEl.value;
        let payload;
        try {
          payload = JSON.parse(bodyEl.value || "{}");
        } catch (e) {
          outEl.textContent = "Invalid JSON body: " + e;
          return;
        }

        statusEl.textContent = "Sending...";
        const headers = { "Content-Type": "application/json" };
        const t = (tokenEl.value || "").trim();
        if (t) headers["Authorization"] = t.startsWith("Bearer ") ? t : ("Bearer " + t);

        try {
          const resp = await fetch(ep, { method: "POST", headers, body: JSON.stringify(payload) });
          const text = await resp.text();
          statusEl.innerHTML = resp.ok
            ? ('<span class="ok">' + resp.status + ' ' + resp.statusText + '</span>')
            : ('<span class="bad">' + resp.status + ' ' + resp.statusText + '</span>');
          try {
            outEl.textContent = JSON.stringify(JSON.parse(text), null, 2);
          } catch {
            outEl.textContent = text;
          }
        } catch (e) {
          statusEl.innerHTML = '<span class="bad">Request failed</span>';
          outEl.textContent = String(e);
        }
      }

      document.getElementById("fill").addEventListener("click", setExample);
      document.getElementById("send").addEventListener("click", send);
      document.getElementById("clear").addEventListener("click", () => { bodyEl.value = ""; outEl.textContent = ""; statusEl.textContent = ""; });

      // Fill initial example
      setExample();
    </script>
  </body>
</html>
""".strip()


# API Endpoints
@app.post("/v1/scrape", response_model=ScrapeResponse)
async def scrape_endpoint(
    request: ScrapeRequest, 
    http_request: Request,
    client: ThordataCrawl = Depends(get_client),
    api_key: str = Depends(get_api_key),
):
    """Scrape a single URL."""
    await check_rate_limit(http_request, api_key)
    logger.info(f"Scrape request: url={request.url}, formats={request.formats}")
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
        response = ScrapeResponse(
            success=bool(result.get("success")),
            data=result.get("data"),
            error=result.get("error"),
        )
        
        # Check response size limit
        if response.success and response.data:
            max_size = _get_max_response_size()
            within_limit, size_error = _check_response_size(response.dict(), max_size)
            if not within_limit:
                logger.warning(f"Response size limit exceeded: url={request.url}, error={size_error}")
                return ScrapeResponse(
                    success=False,
                    error=size_error or "Response size exceeds limit",
                )
        
        if response.success:
            logger.info(f"Scrape success: url={request.url}")
        else:
            logger.warning(f"Scrape failed: url={request.url}, error={response.error}")
        return response
    except ValueError as e:
        # Validation errors
        logger.warning(f"Scrape validation error: url={request.url}, error={str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Scrape exception: url={request.url}, error={str(e)}", exc_info=True)
        return ScrapeResponse(success=False, error=str(e))


@app.post("/v1/batch-scrape", response_model=BatchScrapeResponse)
async def batch_scrape_endpoint(
    request: BatchScrapeRequest,
    http_request: Request,
    client: ThordataCrawl = Depends(get_client),
    api_key: str = Depends(get_api_key),
):
    """
    Batch scrape multiple URLs (Firecrawl-style batch endpoint).
    """
    await check_rate_limit(http_request, api_key)
    try:
        options: Dict[str, Any] = {}
        if request.scrapeOptions:
            options.update(request.scrapeOptions)
            # Firecrawl-ish to our Python client options
            if "waitFor" in options and "wait" not in options:
                options["wait"] = options.pop("waitFor")
            if "wait_for" in options and "waitForSelector" not in options:
                options["waitForSelector"] = options.get("wait_for")
            if "javascript" in options:
                options["javascript"] = bool(options.get("javascript"))

        result = client.batch_scrape(
            urls=request.urls,
            formats=request.formats,
            **options,
        )
        response = BatchScrapeResponse(
            success=bool(result.get("success")),
            results=result.get("results", []),
            error=result.get("error"),
        )
        
        # Check response size limit
        if response.success:
            max_size = _get_max_response_size()
            within_limit, size_error = _check_response_size(response.dict(), max_size)
            if not within_limit:
                logger.warning(f"Response size limit exceeded: batch-scrape, error={size_error}")
                return BatchScrapeResponse(
                    success=False,
                    results=[],
                    error=size_error or "Response size exceeds limit",
                )
        
        return response
    except ValueError as e:
        # Validation errors
        logger.warning(f"Batch scrape validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Batch scrape exception: {str(e)}", exc_info=True)
        return BatchScrapeResponse(success=False, results=[], error=str(e))


def _webhook_signature(secret: str, body: bytes) -> str:
    sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


def _post_webhook(url: str, body: bytes, headers: Dict[str, str], timeout: int = 10) -> None:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        resp.read()


async def _deliver_webhook(webhook: WebhookConfig, payload: Dict[str, Any], event: str, job_id: str) -> None:
    # Best-effort delivery with exponential backoff retries. Never raise to job runner.
    logger.debug(f"Delivering webhook: job_id={job_id}, event={event}, url={webhook.url}")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    headers: Dict[str, str] = {}
    if webhook.headers:
        headers.update({str(k): str(v) for k, v in webhook.headers.items()})

    headers["Content-Type"] = "application/json"
    headers["User-Agent"] = "thordata-firecrawl-webhook/0.1"
    headers["X-Thordata-Event"] = event
    headers["X-Thordata-Job-Id"] = job_id
    if webhook.secret:
        headers["X-Thordata-Signature"] = _webhook_signature(webhook.secret, body)

    timeout = webhook.timeout or 10
    max_retries = webhook.maxRetries or 3
    
    last_err: Optional[str] = None
    # Exponential backoff: 0s, 1s, 2s, 4s, ...
    for attempt in range(max_retries + 1):
        if attempt > 0:
            delay = min(2 ** (attempt - 1), 30)  # Cap at 30 seconds
            await asyncio.sleep(delay)
        try:
            await asyncio.to_thread(_post_webhook, webhook.url, body, headers, timeout)
            logger.info(f"Webhook delivered: job_id={job_id}, event={event}, url={webhook.url}, attempt={attempt+1}")
            return
        except Exception as e:
            last_err = str(e)
            logger.warning(f"Webhook delivery failed: job_id={job_id}, event={event}, attempt={attempt+1}, error={str(e)}")
            continue

    # Swallow errors (best-effort). Log final failure.
    logger.error(f"Webhook delivery exhausted retries: job_id={job_id}, event={event}, url={webhook.url}, error={last_err}")


async def _run_crawl_job(job_id: str, api_key: str) -> None:
    # Build a client inside the background task to avoid relying on request-scoped dependencies.
    base_url = os.getenv("THORDATA_BASE_URL")
    client = ThordataCrawl(api_key=api_key, base_url=base_url)

    async with _CRAWL_JOBS_LOCK:
        job = _CRAWL_JOBS.get(job_id)
        if job is None:
            logger.warning(f"Crawl job not found: job_id={job_id}")
            return
        job.status = "running"
        job.updated_at = time.time()
    logger.info(f"Crawl job started: job_id={job_id}, url={job.request.url}")

    try:
        options: Dict[str, Any] = {}
        if job.request.scrapeOptions:
            options.update(job.request.scrapeOptions)
        if job.request.includePaths:
            options["includePaths"] = job.request.includePaths
        if job.request.excludePaths:
            options["excludePaths"] = job.request.excludePaths
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
        logger.info(f"Crawl job completed: job_id={job_id}, total={job.total}, completed={job.completed}, failed={job.failed}")

        # Webhook (best-effort)
        if job.request.webhook:
            payload: Dict[str, Any] = {
                "event": "crawl.completed",
                "id": job_id,
                "status": job.status,
                "total": job.total,
                "completed": job.completed,
                "failed": job.failed,
                "error": None,
            }
            # Include data only if explicitly requested (avoid huge payloads for large crawls)
            if job.request.webhook.includeData is not False:
                payload["data"] = job.data
            else:
                payload["dataCount"] = len(job.data)
            await _deliver_webhook(job.request.webhook, payload, "crawl.completed", job_id)

    except Exception as e:
        logger.error(f"Crawl job failed: job_id={job_id}, error={str(e)}", exc_info=True)
        async with _CRAWL_JOBS_LOCK:
            job = _CRAWL_JOBS.get(job_id)
            if job is None:
                return
            job.status = "failed"
            job.error = str(e)
            job.updated_at = time.time()

        # Webhook (best-effort)
        if job.request.webhook:
            payload: Dict[str, Any] = {
                "event": "crawl.failed",
                "id": job_id,
                "status": job.status,
                "total": job.total,
                "completed": job.completed,
                "failed": job.failed,
                "error": job.error,
            }
            # Include data only if explicitly requested (avoid huge payloads for large crawls)
            if job.request.webhook.includeData is not False:
                payload["data"] = job.data
            else:
                payload["dataCount"] = len(job.data)
            await _deliver_webhook(job.request.webhook, payload, "crawl.failed", job_id)


@app.post("/v1/crawl", response_model=CrawlJobResponse)
async def crawl_submit(
    request: CrawlRequest,
    http_request: Request,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(get_api_key),
    clientJobId: Optional[str] = Query(None, alias="clientJobId", description="Optional client-provided job ID for idempotency"),
):
    """Submit an async crawl job. Use GET /v1/crawl/{id} to poll status/results."""
    await check_rate_limit(http_request, api_key)
    await _cleanup_expired_jobs()

    running = await _running_jobs_count()
    if running >= _max_concurrent_crawls():
        logger.warning(f"Crawl job rejected: too many concurrent jobs (max={_max_concurrent_crawls()})")
        raise HTTPException(status_code=429, detail="Too many concurrent crawl jobs")

    # Idempotency: if clientJobId provided, check for existing job
    if clientJobId:
        async with _CRAWL_JOBS_LOCK:
            for existing_id, existing_job in _CRAWL_JOBS.items():
                if hasattr(existing_job, "client_job_id") and existing_job.client_job_id == clientJobId:
                    logger.info(f"Crawl job idempotency: clientJobId={clientJobId} -> existing job_id={existing_id}")
                    return CrawlJobResponse(success=True, id=existing_id, url=f"/v1/crawl/{existing_id}")

    job_id = uuid.uuid4().hex
    job = _CrawlJob(job_id, request)
    if clientJobId:
        job.client_job_id = clientJobId

    async with _CRAWL_JOBS_LOCK:
        _CRAWL_JOBS[job_id] = job

    logger.info(f"Crawl job submitted: job_id={job_id}, url={request.url}, limit={request.limit}, clientJobId={clientJobId}")
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
async def map_endpoint(
    request: MapRequest, 
    http_request: Request,
    client: ThordataCrawl = Depends(get_client),
    api_key: str = Depends(get_api_key),
):
    """Discover URLs on a website."""
    await check_rate_limit(http_request, api_key)
    try:
        result = client.map(url=request.url, search=request.search)
        return MapResponse(success=True, links=result.get("links", []))
    except ValueError as e:
        # Validation errors
        logger.warning(f"Map validation error: url={request.url}, error={str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Map exception: url={request.url}, error={str(e)}", exc_info=True)
        # Keep response shape stable; surface error in a minimal way via empty links.
        return MapResponse(success=False, links=[])


@app.post("/v1/search", response_model=SearchResponse)
async def search_endpoint(
    request: SearchRequest, 
    http_request: Request,
    client: ThordataCrawl = Depends(get_client),
    api_key: str = Depends(get_api_key),
):
    """Search the web."""
    await check_rate_limit(http_request, api_key)
    try:
        result = client.search(
            query=request.query,
            limit=request.limit,
            engine=request.engine,
            country=request.country,
            language=request.language,
        )
        return SearchResponse(success=True, data=result.get("data", {}))
    except ValueError as e:
        # Validation errors
        logger.warning(f"Search validation error: query={request.query}, error={str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Search exception: query={request.query}, error={str(e)}", exc_info=True)
        return SearchResponse(success=False, data={"error": str(e)})


@app.post("/v1/search-and-scrape", response_model=SearchAndScrapeResponse)
async def search_and_scrape_endpoint(
    request: SearchAndScrapeRequest,
    http_request: Request,
    client: ThordataCrawl = Depends(get_client),
    api_key: str = Depends(get_api_key),
):
    """
    Combined search + scrape helper: search the web, then scrape the top results.
    """
    await check_rate_limit(http_request, api_key)
    try:
        options: Dict[str, Any] = {}
        if request.scrapeOptions:
            options.update(request.scrapeOptions)
            if "waitFor" in options and "wait" not in options:
                options["wait"] = options.pop("waitFor")
            if "wait_for" in options and "waitForSelector" not in options:
                options["waitForSelector"] = options.get("wait_for")
            if "javascript" in options:
                options["javascript"] = bool(options.get("javascript"))

        result = client.search_and_scrape(
            query=request.query,
            search_limit=request.searchLimit,
            scrape_formats=request.formats,
            **options,
        )
        response = SearchAndScrapeResponse(
            success=bool(result.get("success")),
            query=str(result.get("query") or request.query),
            results=result.get("results", []),
            error=result.get("error"),
        )
        
        # Check response size limit
        if response.success:
            max_size = _get_max_response_size()
            within_limit, size_error = _check_response_size(response.dict(), max_size)
            if not within_limit:
                logger.warning(f"Response size limit exceeded: search-and-scrape, error={size_error}")
                return SearchAndScrapeResponse(
                    success=False,
                    query=request.query,
                    results=[],
                    error=size_error or "Response size exceeds limit",
                )
        
        return response
    except ValueError as e:
        # Validation errors
        logger.warning(f"Search-and-scrape validation error: query={request.query}, error={str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Search-and-scrape exception: query={request.query}, error={str(e)}", exc_info=True)
        return SearchAndScrapeResponse(
            success=False,
            query=request.query,
            results=[],
            error=str(e),
        )

@app.post("/v1/agent", response_model=AgentResponse)
async def agent_endpoint(
    request: AgentRequest, 
    http_request: Request,
    client: ThordataCrawl = Depends(get_client),
    api_key: str = Depends(get_api_key),
):
    """Run an agent task for structured extraction."""
    await check_rate_limit(http_request, api_key)
    try:
        options: Dict[str, Any] = {}
        if request.scrapeOptions:
            options.update(request.scrapeOptions)
            if "waitFor" in options and "wait" not in options:
                options["wait"] = options.pop("waitFor")
            if "wait_for" in options and "waitForSelector" not in options:
                options["waitForSelector"] = options.get("wait_for")
            if "javascript" in options:
                options["javascript"] = bool(options.get("javascript"))

        # Pass scrape formats for context gathering
        options["formats"] = request.formats
        options.setdefault("limit", int(request.searchLimit))

        result = client.agent(prompt=request.prompt, urls=request.urls, schema=request.schema_, model=request.model, **options)
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
    except ValueError as e:
        # Validation errors
        logger.warning(f"Agent validation error: prompt={request.prompt[:50]}..., error={str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Agent exception: prompt={request.prompt[:50]}..., error={str(e)}", exc_info=True)
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
