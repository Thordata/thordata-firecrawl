## Crawl Job Store Design (In‑Memory → Optional Redis)

This document describes how crawl jobs are stored today, and how an optional
Redis‑backed job store can be introduced without breaking the current
in‑memory behavior.

---

## 1. Current Behavior (In‑Memory, Single Process)

Today, `/v1/crawl` uses a simple in‑memory store defined in `api.py`:

- `_CRAWL_JOBS: Dict[str, _CrawlJob]`
- `_CRAWL_JOBS_LOCK: asyncio.Lock`
- Background task `_run_crawl_job(job_id, api_key)` mutates `_Crawl_JOBS[job_id]`
- Helper functions:
  - `_cleanup_expired_jobs()` — TTL cleanup based on `JOB_TTL_SECONDS`
  - `_running_jobs_count()` — counts jobs with `status == "running"`

**Pros**

- Very simple, no external dependency.
- Good for local dev and single‑instance deployments.

**Limitations**

- Not shared across processes / containers (no horizontal scaling).
- Jobs are lost on process restart.
- No persistence or external observability.

This behavior must remain the **default** to keep self‑hosting friction low.

---

## 2. Design Goals for Redis Job Store

The optional Redis store should:

1. **Be opt‑in only**  
   - Enabled via configuration (e.g. `REDIS_URL`, `JOB_STORE_BACKEND=redis`).
   - If not configured, keep using the existing in‑memory store.

2. **Expose the same logical model**  
   - Job fields: `id`, `status`, `total`, `completed`, `failed`, `data`, `error`,
     `created_at`, `updated_at`, `request` (original `CrawlRequest` body).
   - HTTP API surface (`/v1/crawl`, `/v1/crawl/{id}`, `/v1/crawl/{id}/cancel`)
     must stay **backwards compatible**.

3. **Support horizontal scale‑out**

   - Multiple API instances can see the same job store.
   - TTL cleanup and running‑job counting work globally.

4. **Be simple to operate**

   - No complex schemas or migrations.
   - A single Redis instance or managed service is enough for most cases.

---

## 3. Redis Schema Proposal

Assuming `JOB_STORE_BACKEND=redis` and `REDIS_URL=redis://...`,
we use the following key structure:

- **Job metadata** (one hash per job)

  - Key: `crawl:job:{job_id}`
  - Type: `HASH`
  - Fields:
    - `id` — job id (string)
    - `status` — `"queued" | "running" | "completed" | "failed" | "cancelled"`
    - `total` — integer
    - `completed` — integer
    - `failed` — integer
    - `error` — string (optional)
    - `created_at` — UNIX timestamp (float or int)
    - `updated_at` — UNIX timestamp
    - `request` — JSON‑encoded original `CrawlRequest`

- **Job data pages** (list of results)

  - Key: `crawl:job:{job_id}:data`
  - Type: `LIST`
  - Items: JSON‑encoded page entries (same as in‑memory `job.data[i]`)
  - Pagination:
    - `LRANGE key offset (offset+limit-1)` corresponds to `offset` and `limit`
      in `GET /v1/crawl/{id}`.

- **Indexes**

  - Active jobs set:
    - Key: `crawl:jobs:active`
    - Type: `SET`
    - Members: `job_id` for jobs whose `status` is `"running"`
    - Used to implement `_running_jobs_count()`.

  - TTL:
    - Use native Redis expiration on `crawl:job:{job_id}` and `crawl:job:{job_id}:data`.
    - Expiration time: `JOB_TTL_SECONDS` (same as in‑memory cleanup).

---

## 4. Abstraction: JobStore Interface

To keep `api.py` clean, we can encapsulate job operations behind a small
interface, implemented twice:

```python
class CrawlJobStore(Protocol):
    async def create(self, job_id: str, request: CrawlRequest) -> None: ...
    async def mark_running(self, job_id: str) -> None: ...
    async def complete(self, job_id: str, result: Dict[str, Any]) -> None: ...
    async def fail(self, job_id: str, error: str) -> None: ...
    async def cancel(self, job_id: str) -> None: ...
    async def get(self, job_id: str) -> Optional[Dict[str, Any]]: ...
    async def get_page(self, job_id: str, offset: int, limit: int) -> Dict[str, Any]: ...
    async def running_count(self) -> int: ...
    async def cleanup_expired(self) -> None: ...
```

**Implementations**

- `InMemoryCrawlJobStore` — current logic using `_CRAWL_JOBS` + `_CRAWL_JOBS_LOCK`.
- `RedisCrawlJobStore` — backed by Redis using the schema above.

**Selection**

In `api.py` (or a new `_job_store.py`), choose implementation at startup:

```python
backend = os.getenv("JOB_STORE_BACKEND", "memory").lower()
if backend == "redis" and os.getenv("REDIS_URL"):
    store: CrawlJobStore = RedisCrawlJobStore(os.getenv("REDIS_URL"))
else:
    store = InMemoryCrawlJobStore()
```

All places that currently read/write `_CRAWL_JOBS` will be refactored to call
methods on `store` instead.

---

## 5. Concurrency & Limits

### Max Concurrent Jobs

The existing `_max_concurrent_crawls()` reads `MAX_CONCURRENT_CRAWLS` from env.

In Redis mode:

- `store.running_count()` will read `SCARD crawl:jobs:active`.
- When a job transitions to `"running"`, we `SADD crawl:jobs:active job_id`.
- When a job reaches `"completed"`, `"failed"`, or `"cancelled"`,
  we `SREM crawl:jobs:active job_id`.

This gives a **cluster‑wide** concurrency count compatible with the current
limit behavior.

### TTL Cleanup

In Redis mode we rely on native key expiration, so `_cleanup_expired_jobs()`
becomes a no‑op or a thin wrapper (e.g. removing orphan ids from
`crawl:jobs:active`).

---

## 6. Migration & Backwards Compatibility

**No automatic migration** between in‑memory and Redis is planned. Instead:

- In‑memory:
  - Ideal for local dev and simple single‑instance deployments.
  - Restart = in‑flight jobs lost (documented behavior).

- Redis:
  - Recommended for multi‑instance or long‑running crawls.
  - Administrators explicitly opt in by setting `JOB_STORE_BACKEND=redis`
    and `REDIS_URL=...`.

The HTTP API contract remains unchanged:

- `POST /v1/crawl` → `{ "success": true, "id": ..., "url": "/v1/crawl/{id}" }`
- `GET /v1/crawl/{id}` → job status + paginated `data`
- `POST /v1/crawl/{id}/cancel` → `{ "success": true, "status": ... }`

---

## 7. Deployment Notes

To enable Redis job store in production:

1. Provision Redis (managed service or self‑hosted).
2. Configure environment:

```bash
export JOB_STORE_BACKEND=redis
export REDIS_URL=redis://:password@hostname:6379/0
export MAX_CONCURRENT_CRAWLS=4
export JOB_TTL_SECONDS=3600
```

3. Deploy `thordata-firecrawl` as usual (Docker, systemd, etc.).

If Redis is unavailable or misconfigured, the server **should fail fast** at
startup instead of silently falling back to in‑memory, to avoid surprises in
production. For local development, leaving `JOB_STORE_BACKEND` unset will keep
current behavior.

---

## 8. Future Extensions

- Store minimal crawl metrics (per job stats, per token stats) for observability.
- Add an admin endpoint to list recent jobs (read‑only, optional).
- Optionally plug in other backends (Postgres, DynamoDB) behind the same
  `CrawlJobStore` interface if needed.

