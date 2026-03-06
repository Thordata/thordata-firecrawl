# Deploy to Render (Free PaaS)

This guide deploys the **Thordata Firecrawl API** to Render using the included `render.yaml`.

## Why Render?

- Free tier available (good for demos and GitHub Pages playground).
- Automatic HTTPS.
- Simple GitHub-based deploys.

## Prerequisites

- A GitHub repo containing this project.
- A Render account.
- A Thordata API key / scraper token (recommended).

## One-click deploy (Blueprint)

1. Push this repo to GitHub (make sure `render.yaml` is in the repo root).
2. In Render dashboard, choose **New** → **Blueprint**.
3. Select your GitHub repo (`Thordata/thordata-firecrawl`).
4. **Blueprint Name** (optional): You can name it `thordata-firecrawl` or leave it as default.
5. Render will detect `render.yaml` and create a Web Service:
   - Build: `pip install -U pip && pip install ".[server]"`
   - Start: `uvicorn thordata_firecrawl.api:app --host 0.0.0.0 --port $PORT`
6. Set environment variables:
   - **Required**:
     - `THORDATA_API_KEY` = `你的 Thordata API Key 或 Scraper Token`
   - **Recommended** (for GitHub Pages):
     - `CORS_ALLOW_ORIGINS` = `https://thordata.github.io`
     - **Note**: CORS origin is protocol + domain (no path). Even though your site is at `https://thordata.github.io/thordata-firecrawl-site/`, use `https://thordata.github.io` (without the path).
     - For multiple origins, use comma-separated: `https://thordata.github.io,https://your-domain.com`
   - **Optional** (already defaulted in `render.yaml`): rate limits, response size, logging.
7. Click **Create Blueprint** or **Apply** to start deployment.
8. Wait for deployment to complete (3-5 minutes). You'll get an HTTPS URL like:
   - `https://<your-service>.onrender.com`

## Verify

Open in browser:

- `GET /health` should return `{"status":"ok"}`
- `GET /docs` should show Swagger UI

Example:

```bash
curl -sS https://<your-service>.onrender.com/health
```

## Connect GitHub Pages Playground

Open the website:

- `https://thordata.github.io/thordata-firecrawl-site/`

In Playground:

- Set **API URL** to your Render URL (HTTPS), e.g. `https://thordata-firecrawl-api.onrender.com`
- Paste your token into **API Key**.
- Click **Load Example** → **Send Request**.

### CORS Configuration Explained

**Important**: CORS (Cross-Origin Resource Sharing) checks the **origin** (protocol + domain + port), not the full URL path.

- ✅ **Correct**: `CORS_ALLOW_ORIGINS=https://thordata.github.io`
  - This allows requests from `https://thordata.github.io/thordata-firecrawl-site/` and any other path under `thordata.github.io`
- ❌ **Wrong**: `CORS_ALLOW_ORIGINS=https://thordata.github.io/thordata-firecrawl-site/`
  - This won't work because CORS doesn't check paths

**Why**: When your browser makes a request from `https://thordata.github.io/thordata-firecrawl-site/` to `https://your-api.onrender.com`, the browser sends `Origin: https://thordata.github.io` (without the path). The API server checks if this origin is allowed.

## Notes / Limitations (Free tier)

- The service may sleep when idle; first request can be slow (cold start).
- For heavier workloads, upgrade plan or move to a paid tier.

