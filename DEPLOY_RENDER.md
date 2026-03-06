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
3. Select your GitHub repo.
4. Render will detect `render.yaml` and create a Web Service:
   - Build: `pip install -U pip && pip install ".[server]"`
   - Start: `uvicorn thordata_firecrawl.api:app --host 0.0.0.0 --port $PORT`
5. Set environment variables:
   - **Required (recommended)**:
     - `THORDATA_API_KEY` (or use a scraper token)
   - **Recommended**:
     - `CORS_ALLOW_ORIGINS`: comma-separated origins for your frontend(s), e.g.
       - `https://thordata.github.io`
       - `https://thordata.github.io,https://your-domain.com`
   - Optional tuning (already defaulted in `render.yaml`): rate limits, response size, logging.
6. Deploy. When finished, you’ll get an HTTPS URL like:
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

- Set **API URL** to your Render URL (HTTPS).
- Paste your token into **API Key**.
- Click **Load Example** → **Send Request**.

## Notes / Limitations (Free tier)

- The service may sleep when idle; first request can be slow (cold start).
- For heavier workloads, upgrade plan or move to a paid tier.

