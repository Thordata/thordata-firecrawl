# Self-Hosting Guide

This guide explains how to self-host Thordata Firecrawl API server.

## Prerequisites

- Python 3.10+ or Docker
- Thordata API key (get from [Thordata Dashboard](https://dashboard.thordata.com))
- (Optional) OpenAI-compatible API key for `agent` functionality

## Quick Start with Docker

1. Clone the repository:
```bash
git clone https://github.com/Thordata/thordata-firecrawl.git
cd thordata-firecrawl
```

2. Create `.env` file:
```bash
cp .env.example .env
# Edit .env and add your THORDATA_API_KEY
```

3. Start the server:
```bash
docker-compose up -d
```

The API will be available at `http://localhost:3002`

## Local Development Setup

1. Install dependencies:
```bash
pip install -e ".[all]"
```

2. Set environment variables:
```bash
export THORDATA_API_KEY=your-api-key
export OPENAI_API_KEY=your-openai-key  # Optional, for agent functionality
```

3. Run the server:
```bash
python run_server.py
# Or use uvicorn directly:
uvicorn thordata_firecrawl.api:app --host 0.0.0.0 --port 3002
```

## "I opened /docs but don't know what to do" (Beginner Guide)

Open:

- `http://127.0.0.1:3002/` (home page)
- `http://127.0.0.1:3002/playground` (the easiest way to try endpoints)
- `http://127.0.0.1:3002/docs` (Swagger UI)

### Recommended: use `/playground`

1. Paste your token into the **Authorization** box.
   - If you have `THORDATA_SCRAPER_TOKEN`, use it (Universal API requires scraper_token for clean markdown/html/screenshots).
2. Click **Fill example** then **Send**.
3. Read the JSON response on the right.

### Using Swagger UI (`/docs`)

1. Click the green **Authorize** button (top-right).
2. Paste `Bearer <YOUR_TOKEN>` and click **Authorize**.
3. Expand an endpoint (e.g. `POST /v1/scrape`) → **Try it out** → fill JSON body → **Execute**.

## API Endpoints

Once running, the API provides:

- `GET /health` - Health check
- `POST /v1/scrape` - Scrape a single URL
- `POST /v1/crawl` - Submit an async crawl job (returns job id)
- `GET /v1/crawl/{id}` - Poll crawl job status/results
- `POST /v1/map` - Discover URLs on a website
- `POST /v1/search` - Search the web
- `POST /v1/agent` - Extract structured data using LLM

Interactive API documentation is available at `/docs` (Swagger UI) and `/redoc` (ReDoc).

## Configuration

Key environment variables:

- `THORDATA_API_KEY` (required) - Your Thordata API key
- `THORDATA_BASE_URL` (optional) - Custom Thordata API base URL
- `OPENAI_API_KEY` (optional) - For agent functionality
- `OPENAI_API_BASE` (optional) - LLM API base URL
- `OPENAI_MODEL` (optional) - LLM model name
- `PORT` (optional) - Server port (default: 3002)
- `HOST` (optional) - Server host (default: 0.0.0.0)

## Production Deployment

For production, consider:

1. **Reverse Proxy**: Use Nginx or Caddy in front of the API
2. **Process Manager**: Use systemd, supervisor, or PM2
3. **Monitoring**: Add health checks and logging
4. **Rate Limiting**: Implement rate limiting at the reverse proxy level
5. **SSL/TLS**: Use Let's Encrypt for HTTPS

Example systemd service (`/etc/systemd/system/thordata-firecrawl.service`):

```ini
[Unit]
Description=Thordata Firecrawl API
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/thordata-firecrawl
Environment="THORDATA_API_KEY=your-key"
ExecStart=/usr/bin/python3 -m uvicorn thordata_firecrawl.api:app --host 0.0.0.0 --port 3002
Restart=always

[Install]
WantedBy=multi-user.target
```

## Troubleshooting

### Port already in use
Change the port:
```bash
PORT=3003 python run_server.py
```

### API key not working
Verify your API key is correct and has sufficient credits.

### LLM not working
Ensure `OPENAI_API_KEY` is set and the API is accessible from your server.
