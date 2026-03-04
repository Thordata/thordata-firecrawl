## Thordata Crawl (thordata-firecrawl)

**Thordata Crawl – Turn any website into AI‑ready data with a single API.**

Thordata Crawl is a Firecrawl‑like Web Data API service built on top of Thordata’s AI‑native web data infrastructure. It turns websites into structured, AI‑ready data (Markdown / JSON / HTML / screenshots) for LLMs, RAG systems, and agents.

---

## ✨ Features

- **LLM‑ready output**: Directly returns Markdown, structured JSON, raw HTML, and screenshot URLs to minimize post‑processing.
- **Simple unified API**: A single client/service covers `scrape`, `crawl`, `map`, `search`, and `agent`-style operations.
- **Firecrawl‑inspired interface**: Request and response shapes are designed to be as close as reasonably possible to `firecrawl/firecrawl` for easy migration.
- **Powered by Thordata**: Leverages Thordata’s Web Scraper, Scraping Browser, SERP API, and proxy network for higher reliability and success rates.
- **Self‑hostable**: Can be deployed locally or in your own environment via Docker / docker‑compose.
- **AI & Agent ecosystem**: Designed to work smoothly with `thordata-mcp-server`, `thordata-rag-pipeline`, LangChain tools, and more.

---

## 📦 Repository Structure

- `README.md`: Project overview and usage documentation
- `SELF_HOST.md`: Self-hosting guide with Docker and production deployment instructions
- `docker-compose.yml`: One-command Docker deployment
- `Dockerfile`: Docker image for HTTP API service
- `run_server.py`: Simple script to run the API server locally
- `test_api.py`: Quick test script to verify API functionality
- `.env.example`: Environment variable template
- `src/thordata_firecrawl/`: Core Python package
  - `__init__.py`: Package exports
  - `client.py`: High-level Python client (`ThordataCrawl`)
  - `api.py`: FastAPI HTTP server with REST endpoints
  - `cli.py`: Command-line interface
  - `_crawler.py`: Internal crawler utilities (BFS, link discovery)
  - `_llm.py`: LLM integration for agent functionality
- `examples/`: Usage examples
  - `basic_crawl.py`: Basic crawl examples
  - `search_and_agent.py`: Search and agent examples
  - `agent_with_llm.py`: LLM-powered structured extraction examples

---

## 🚀 Quickstart

> The code is under active development. The examples below describe the target DX; details may change as the implementation evolves.

### Python client example

Install (planned):

```bash
pip install thordata-firecrawl
```

Basic `scrape` example:

```python
from thordata_firecrawl import ThordataCrawl

client = ThordataCrawl(api_key="td-YOUR_API_KEY")

doc = client.scrape(
    url="https://www.thordata.com",
    formats=["markdown"]
)

print(doc.markdown)
```

Site‑level `crawl` example (planned):

```python
job = client.crawl(
    url="https://doc.thordata.com",
    limit=100,
    formats=["markdown"]
)

for page in job["data"]:
    print(page["metadata"]["sourceUrl"], page["markdown"][:200])
```

### HTTP API examples

Start the server:
```bash
# Using Docker
docker-compose up -d

# Or locally
pip install -e ".[server]"
python run_server.py
```

Scrape a single page:

```bash
# Scrape a single page
curl -X POST "http://localhost:3002/v1/scrape" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.thordata.com",
    "formats": ["markdown", "html", "screenshot"]
  }'

# Crawl a website (async job)
curl -X POST "http://localhost:3002/v1/crawl" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://doc.thordata.com",
    "limit": 10,
    "maxDepth": 2,
    "scrapeOptions": {
      "formats": ["markdown"]
    }
  }'

# Poll crawl job status/results
# (Replace JOB_ID with the id returned by POST /v1/crawl)
curl -X GET "http://localhost:3002/v1/crawl/JOB_ID" \
  -H "Authorization: Bearer YOUR_API_KEY"

# Map (discover links)
curl -X POST "http://localhost:3002/v1/map" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "search": "pricing"
  }'

# Search the web
curl -X POST "http://localhost:3002/v1/search" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "best web scraping tools 2026",
    "limit": 10
  }'

# Agent (structured extraction)
curl -X POST "http://localhost:3002/v1/agent" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Extract company founders information",
    "urls": ["https://example.com/about"],
    "schema": {
      "type": "object",
      "properties": {
        "founders": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "name": {"type": "string"},
              "role": {"type": "string"}
            }
          }
        }
      }
    }
  }'
```

Interactive API documentation is available at `http://localhost:3002/docs` (Swagger UI) and `http://localhost:3002/redoc` (ReDoc).

### CLI examples

```bash
# Scrape a single page
thordata-firecrawl scrape https://www.thordata.com \
  --format markdown --format html --format screenshot \
  --out thordata.md

# Crawl a website (discovers and scrapes multiple pages)
thordata-firecrawl crawl https://doc.thordata.com \
  --limit 50 \
  --max-depth 3 \
  --include-subdomains \
  --concurrency 5 \
  --format markdown \
  --out ./data/crawl-result.json

# Map (discover links without full content)
thordata-firecrawl map https://example.com \
  --search "pricing" \
  --include-subdomains \
  --out links.json

# Search the web
thordata-firecrawl search "best web scraping tools 2026" \
  --limit 10 \
  --engine google \
  --country us \
  --out search-results.json

# Agent (structured extraction - MVP)
thordata-firecrawl agent "Extract company founders" \
  --url https://example.com/about \
  --schema schema.json \
  --out extracted-data.json
```

---

## 🧩 API Design (Firecrawl‑inspired)

> This section documents the target API surface. A canonical spec will be added later in `openapi.yaml`.

### `/v1/scrape` – Single‑page scrape

- **Purpose**: Scrape a single URL and return content in requested formats.
- **Example request body**:

```json
{
  "url": "https://example.com",
  "formats": ["markdown", "html", "screenshot"],
  "scrapeOptions": {
    "waitFor": "selector-or-time",
    "timeout": 30000,
    "javascript": true
  },
  "metadata": {
    "includeHeaders": false
  }
}
```

- **Example response body**:

```json
{
  "success": true,
  "data": {
    "markdown": "...",
    "html": "...",
    "screenshot": "https://cdn.thordata.com/.../shot.png",
    "metadata": {
      "title": "...",
      "sourceUrl": "https://example.com"
    }
  }
}
```

### `/v1/crawl` – Site crawl

- **Purpose**: Discover and scrape multiple pages starting from a seed URL using BFS traversal.
- **Features**:
  - Automatic link discovery from HTML content
  - Domain/subdomain filtering
  - Depth and limit controls
  - Concurrent requests for better performance
- **Example request body**:

```json
{
  "url": "https://docs.example.com",
  "limit": 100,
  "scrapeOptions": {
    "formats": ["markdown"]
  },
  "includeSubdomains": false,
  "maxDepth": 3
}
```

- **Example response (job submission)**:

```json
{
  "success": true,
  "id": "job-123",
  "url": "https://api.thordata.com/crawl/v1/crawl/job-123"
}
```

- **Example response (poll job status)**:

```json
{
  "status": "completed",
  "total": 50,
  "completed": 50,
  "creditsUsed": 50,
  "data": [
    {
      "markdown": "# Page Title\\n\\nContent...",
      "metadata": {
        "title": "Page Title",
        "sourceUrl": "https://..."
      }
    }
  ]
}
```

### `/v1/map` – URL topology / link map

- **Purpose**: Discover URLs within a site without fetching full page content.
- **Features**:
  - Extracts all links from the seed page HTML
  - Filters by domain/subdomain
  - Optional keyword-based filtering/ranking
- **Example request body**:

```json
{
  "url": "https://example.com",
  "search": "pricing"
}
```

- **Example response body**:

```json
{
  "success": true,
  "links": [
    {
      "url": "https://example.com",
      "title": "Example",
      "description": "..."
    },
    {
      "url": "https://example.com/pricing",
      "title": "Pricing",
      "description": "..."
    }
  ]
}
```

### `/v1/search` – Web search

- **Purpose**: Firecrawl‑style `search` interface backed by Thordata SERP API.
- **Example request body**:

```json
{
  "query": "best web scraping tools 2026",
  "limit": 10
}
```

- **Example response body**:

```json
{
  "success": true,
  "data": {
    "web": [
      {
        "title": "...",
        "url": "...",
        "snippet": "..."
      }
    ]
  }
}
```

### `/v1/agent` – Structured extraction (advanced)

- **Purpose**: Use LLM + JSON schema to extract structured data from web content.
- **Features**:
  - Scrapes provided URLs (or searches if no URLs given)
  - Uses OpenAI-compatible LLM APIs for extraction
  - Supports JSON schema validation
  - Works with OpenAI, SiliconFlow, DeepSeek, and other compatible providers
- **Example request body**:

```json
{
  "urls": ["https://example.com/about"],
  "prompt": "Extract company founders information",
  "schema": {
    "type": "object",
    "properties": {
      "founders": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "name": { "type": "string" },
            "role": { "type": "string" }
          }
        }
      }
    }
  },
  "model": "spark-1-mini"
}
```

- **Example response body**:

```json
{
  "success": true,
  "data": {
    "founders": [
      {
        "name": "Alice",
        "role": "CEO"
      }
    ]
  },
  "sources": ["https://example.com/about"]
}
```

---

## 🏗 Architecture (Planned)

High‑level architecture:

- **Entry points**
  - HTTP API
  - Python SDK
  - CLI tool
- **Middle layer**
  - Job management / queue (for async crawl)
  - URL discovery / deduplication / rate limiting
  - Content cleaning (HTML → Markdown / JSON)
  - Structured extraction module (Agent / RAG)
- **Underlying Thordata infrastructure**
  - Proxy Network
  - Web Scraper API
  - Scraping Browser
  - SERP API
  - RAG Pipeline

This repository does **not** contain proxy network or anti‑bot core logic. It only calls official Thordata APIs/SDKs, allowing this project to use a permissive open‑source license (MIT, planned) without exposing commercial internals.

---

## ⚙️ Installation & Deployment (Planned)

### Local development

Planned local workflow:

- Requires Python 3.10+.
- After cloning the repo, install in editable mode:

```bash
pip install -e .
```


- Install optional LLM dependencies (for `agent` functionality):
```bash
pip install -e ".[llm]"
```

- Configure environment variables (or `.env` file):
  - `THORDATA_API_KEY`: Thordata API key for scraping (required)
  - `THORDATA_BASE_URL`: Optional Thordata API base URL
  - `OPENAI_API_KEY`: OpenAI-compatible API key (required for `agent` functionality)
  - `OPENAI_API_BASE`: API base URL (default: `https://api.openai.com/v1`)
  - `OPENAI_MODEL`: Model name (default: `auto` - auto-detects based on API_BASE)

### Docker / docker-compose

Planned deployment:

- Build service image via `Dockerfile`.
- Start via `docker-compose.yaml`:

```bash
docker-compose up --build
```

The service is expected to listen on `http://localhost:3002` by default (exact port TBD).

### Production deployment (planned)

- Can be deployed to K8s / ECS / VMs.
- Recommended to front the service with an API Gateway for auth, rate limiting, and auditing.
- Task metadata and results can be stored in Redis / a database for better resilience and observability.

---

## 🔧 Configuration & Environment Variables (Planned)

Planned core configuration:

- **Core**
  - `THORDATA_API_KEY`: Required Thordata API key for scraping.
  - `THORDATA_BASE_URL`: Optional base URL, defaults to official endpoint if omitted.
  - `CRAWL_MAX_CONCURRENCY`: Maximum concurrent scrape operations.
  - `CRAWL_DEFAULT_LIMIT`: Default maximum number of pages per crawl.
- **Optional**
  - `REDIS_URL` / `DATABASE_URL`: Storage for tasks and results.
  - `LOG_LEVEL`: Logging level, e.g. `INFO` / `DEBUG`.
  - `MAX_RESPONSE_SIZE`: Max response size in bytes to prevent OOM.

---

## 🛡 Resilience & Performance (Planned)

To ensure real‑world stability, the project will gradually introduce:

- **Retry strategies**: Exponential backoff for 5xx / network errors / timeouts.
- **Rate limiting & quotas**: Per‑token / per‑IP concurrency and QPS controls.
- **Idempotency**: Optional `clientJobId` for crawl jobs to avoid duplicates.
- **Observability**: Structured logging around key operations for debugging and monitoring.

---

## 🔍 Comparison with Firecrawl

**Interface & DX**

- Aligns with Firecrawl’s `/scrape` / `/crawl` / `/map` / `/search` / `/agent` style APIs to lower migration cost.
- Provides Python client and CLI with examples that feel familiar to Firecrawl users.

**Infrastructure differences**

- Firecrawl’s internal infra is not fully public.
- Thordata Crawl is explicitly powered by Thordata’s Proxy Network, Web Scraper, Scraping Browser, SERP API, and RAG Pipeline.

**Licensing model**

- Firecrawl’s main repo is licensed under AGPL‑3.0.
- Thordata Crawl is planned to use MIT (see `LICENSE` once added), making it easy to integrate into commercial projects.

---

## 🌐 Relationship to Thordata Ecosystem

- **thordata-python-sdk (`thordata-sdk`)**
  - This project is a higher‑level wrapper on top of the official Python SDK; all HTTP calls to Thordata go through it.
- **thordata-rag-pipeline**
  - Provides a full RAG pipeline from web content to retrieval. Crawl/agent outputs from this project can flow directly into it.
- **thordata-mcp-server**
  - MCP bridge for clients like Claude / Cursor / OpenAI.
  - Future versions of this project may expose MCP tools so agents can call `/scrape` / `/crawl` directly.

---

## 🗺 Roadmap

- **v0.1 (MVP)**
  - Implement Python client based on `thordata-sdk` with `scrape` (single‑page) and basic `crawl`/`map` stubs.
  - Provide a CLI with `scrape` / `crawl` subcommands.
  - Document configuration and local usage.
- **v0.2**
  - Implement HTTP service (FastAPI or similar) exposing `/v1/scrape` / `/v1/crawl` / `/v1/map`.
  - Add Docker / docker‑compose support.
  - Introduce simple job queue and status polling endpoints.
- **v0.3**
  - Integrate Thordata SERP API to provide `/v1/search`.
  - Implement initial `/v1/agent` combining LLM with the RAG pipeline.
- **v0.4+**
  - MCP tools integration.
  - LangChain / LlamaIndex / OpenAI Tools integrations.
  - Performance tuning, multi‑tenant support, and smarter scheduling.

---

## 🤝 Contributing

Issues and Pull Requests are welcome.

Before submitting code, please:

- Run the existing tests (planned: `pytest`).
- Follow the basic code style (planned: `ruff` / `black` / `mypy`).

A full contributing guide will be added later in `CONTRIBUTING.md`.

---

## 📄 License

This project is licensed under the MIT License. See [LICENSE](LICENSE) file for details.

