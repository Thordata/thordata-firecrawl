from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional

from thordata.client import ThordataClient

from ._crawler import crawl_bfs, discover_links

try:
    from ._llm import extract_structured_data
except ImportError:
    # LLM support is optional
    extract_structured_data = None


class ThordataCrawl:
    """
    High-level client for Thordata Crawl.

    This is a thin wrapper around the official Thordata Python SDK that
    exposes Firecrawl-like methods: scrape, crawl, map, search, agent.
    """

    def __init__(self, api_key: str, base_url: Optional[str] = None, **kwargs: Any) -> None:
        """
        Initialize the Thordata Crawl client.

        :param api_key: Thordata API key.
        :param base_url: Optional base URL for Thordata API.
        :param kwargs: Extra arguments forwarded to the underlying SDK client.
        """
        # The Thordata SDK uses `scraper_token` as the main credential for scraping APIs.
        # `base_url` can be wired through using the *_base_url parameters if needed.
        self._client = ThordataClient(
            scraper_token=api_key,
            universalapi_base_url=base_url,
            **kwargs,
        )

    def scrape(self, url: str, formats: Optional[List[str]] = None, **options: Any) -> Dict[str, Any]:
        """
        Scrape a single URL and return AI-ready content.

        This minimal implementation supports:
        - markdown: via universal_scrape_markdown
        - html: via universal_scrape(output_format=\"html\")
        - screenshot: via universal_scrape with PNG output, returned as a data URL
        """
        formats = formats or ["markdown"]
        result: Dict[str, Any] = {"success": True, "data": {}, "url": url}

        # Options mapping (Firecrawl-ish -> Thordata SDK)
        js_render = bool(options.get("javascript", True))
        wait = options.get("wait") or options.get("waitFor")
        wait_for = options.get("wait_for") or options.get("waitForSelector") or options.get("waitFor")
        country = options.get("country")
        block_resources = options.get("block_resources") or options.get("blockResources")
        clean_content = options.get("clean_content") or options.get("cleanContent")
        follow_redirect = options.get("follow_redirect") or options.get("followRedirect")
        max_chars = options.get("max_chars") or options.get("maxChars") or 20000

        if "markdown" in formats:
            # Prefer SDK's universal_scrape_markdown (fast path), but fall back to
            # HTML -> Markdown conversion if the SDK environment is missing optional deps.
            try:
                markdown = self._client.universal_scrape_markdown(
                    url=url,
                    js_render=js_render,
                    wait=wait,
                    wait_for=wait_for,
                    country=country,
                    block_resources=block_resources,
                    max_chars=int(max_chars) if max_chars else 20000,
                )
                result["data"]["markdown"] = markdown
            except Exception as e:
                # Fallback: fetch HTML and convert locally via html2text.
                try:
                    import html2text

                    html = self._client.universal_scrape(
                        url=url,
                        js_render=js_render,
                        output_format="html",
                        wait=wait,
                        wait_for=wait_for,
                        country=country,
                        block_resources=block_resources,
                        clean_content=clean_content,
                        follow_redirect=follow_redirect,
                    )
                    html_str = html if isinstance(html, str) else str(html)
                    h = html2text.HTML2Text()
                    h.ignore_links = False
                    h.ignore_images = True
                    result["data"]["markdown"] = h.handle(html_str)
                    result["data"]["markdown_fallback_reason"] = str(e)
                except Exception:
                    # Last resort: still return a structured response.
                    result["data"]["markdown"] = ""
                    result["data"]["markdown_error"] = str(e)

        need_html = "html" in formats
        need_screenshot = "screenshot" in formats

        if need_html or need_screenshot:
            html_value: Optional[str] = None
            png_bytes: Optional[bytes] = None

            if need_html and need_screenshot:
                # Request both HTML and PNG in a single Universal Scrape call.
                combo = self._client.universal_scrape(
                    url=url,
                    js_render=js_render,
                    output_format=["html", "png"],
                    wait=wait,
                    wait_for=wait_for,
                    country=country,
                    block_resources=block_resources,
                    clean_content=clean_content,
                    follow_redirect=follow_redirect,
                )
                if isinstance(combo, dict):
                    html_value = combo.get("html") if isinstance(combo.get("html"), str) else None
                    png_raw = combo.get("png")
                    if isinstance(png_raw, (bytes, bytearray)):
                        png_bytes = bytes(png_raw)
            elif need_html:
                html = self._client.universal_scrape(
                    url=url,
                    js_render=js_render,
                    output_format="html",
                    wait=wait,
                    wait_for=wait_for,
                    country=country,
                    block_resources=block_resources,
                    clean_content=clean_content,
                    follow_redirect=follow_redirect,
                )
                html_value = html if isinstance(html, str) else str(html)
            else:  # need_screenshot only
                png_raw = self._client.universal_scrape(
                    url=url,
                    js_render=js_render,
                    output_format="png",
                    wait=wait,
                    wait_for=wait_for,
                    country=country,
                    block_resources=block_resources,
                    clean_content=clean_content,
                    follow_redirect=follow_redirect,
                )
                if isinstance(png_raw, (bytes, bytearray)):
                    png_bytes = bytes(png_raw)

            if html_value is not None:
                result["data"]["html"] = html_value

            if png_bytes is not None:
                # Return screenshot as a data URL for now; in future we may provide CDN URLs.
                b64 = base64.b64encode(png_bytes).decode("ascii")
                result["data"]["screenshot"] = f"data:image/png;base64,{b64}"

        unsupported = [f for f in formats if f not in {"markdown", "html", "screenshot"}]
        if unsupported:
            result["data"]["unsupported_formats"] = unsupported

        return result

    def crawl(self, url: str, limit: int = 100, **options: Any) -> Dict[str, Any]:
        """
        Crawl a website starting from the given URL.

        This implementation uses BFS to discover and scrape multiple pages:
        - Extracts links from HTML content
        - Respects domain/subdomain filtering
        - Supports depth and limit controls
        - Uses concurrent requests for better performance

        :param url: Seed URL.
        :param limit: Maximum number of pages to crawl.
        :param options: Extra crawl options:
            - formats: List of output formats (default: ["markdown"])
            - maxDepth: Maximum crawl depth (None = unlimited)
            - includeSubdomains: Whether to include subdomains (default: False)
            - concurrency: Number of concurrent requests (default: 5)
            - Other options are passed to scrape() for each page
        """
        formats = options.pop("formats", ["markdown"])
        max_depth = options.pop("maxDepth", options.pop("max_depth", None))
        include_subdomains = options.pop("includeSubdomains", options.pop("include_subdomains", False))
        concurrency = options.pop("concurrency", 5)

        # Ensure we fetch HTML for link discovery
        if "html" not in formats:
            formats = list(formats) + ["html"]

        return crawl_bfs(
            scrape_func=self.scrape,
            seed_url=url,
            limit=limit,
            max_depth=max_depth,
            include_subdomains=include_subdomains,
            formats=formats,
            concurrency=concurrency,
            **options,
        )

    def map(self, url: str, search: Optional[str] = None, **options: Any) -> Dict[str, Any]:
        """
        Discover URLs on a website without fetching full content.

        This implementation:
        - Fetches the seed page HTML
        - Extracts all links from the page
        - Filters by domain/subdomain
        - Optionally filters/ranks by search keyword

        :param url: Seed URL to start discovery from.
        :param search: Optional keyword to filter/rank links (not yet fully implemented).
        :param options: Extra options:
            - includeSubdomains: Whether to include subdomains (default: False)
            - Other options are passed to scrape() for fetching the seed page
        """
        include_subdomains = options.pop("includeSubdomains", options.pop("include_subdomains", False))

        # Fetch the seed page HTML
        page_result = self.scrape(url=url, formats=["html"], **options)
        if not page_result.get("success"):
            return {"success": False, "links": [], "error": "Failed to fetch seed page"}

        html_content = page_result.get("data", {}).get("html", "")
        if not html_content:
            return {"success": True, "links": []}

        # Discover links
        links = discover_links(
            html_content=html_content,
            base_url=url,
            seed_url=url,
            include_subdomains=include_subdomains,
        )

        # Simple keyword filtering if search is provided
        if search:
            search_lower = search.lower()
            links = [
                link
                for link in links
                if search_lower in link["url"].lower()
                or (link.get("title") and search_lower in link["title"].lower())
            ]

        return {"success": True, "links": links}

    def search(self, query: str, limit: int = 10, **options: Any) -> Dict[str, Any]:
        """
        Search the web via Thordata SERP API.

        Returns results in Firecrawl-compatible format.

        :param query: Search query string.
        :param limit: Maximum number of results (default: 10).
        :param options: Extra SERP options:
            - engine: Search engine (default: "google")
            - country: Country code (e.g., "us", "uk")
            - language: Language code (e.g., "en", "zh")
            - Other options are passed to Thordata SERP API
        """
        # Extract common options
        engine = options.pop("engine", "google")
        country = options.pop("country", None)
        language = options.pop("language", None)

        # Call SERP API
        serp_result = self._client.serp_search(
            query=query,
            num=limit,
            engine=engine,
            country=country,
            language=language,
            **options,
        )

        # Transform to Firecrawl-like format
        web_results = []
        if isinstance(serp_result, dict):
            # SERP API typically returns results in various keys depending on engine
            # Common keys: "organic_results", "results", "items", etc.
            organic = (
                serp_result.get("organic")
                or serp_result.get("organic_results")
                or serp_result.get("results")
                or serp_result.get("items", [])
            )
            for item in organic[:limit]:
                if isinstance(item, dict):
                    web_results.append(
                        {
                            "title": item.get("title", ""),
                            "url": item.get("link") or item.get("url", ""),
                            "snippet": item.get("snippet") or item.get("description", ""),
                        }
                    )

        return {"success": True, "data": {"web": web_results}}

    def agent(self, prompt: str, urls: Optional[List[str]] = None, **options: Any) -> Dict[str, Any]:
        """
        Run an agent task with optional context from given URLs.

        This method scrapes the provided URLs (or searches if no URLs given),
        then uses LLM to extract structured data based on the prompt and optional schema.

        :param prompt: Task description or extraction prompt.
        :param urls: Optional list of URLs to scrape for context.
        :param options: Extra options:
            - schema: Optional JSON schema for structured output
            - model: LLM model identifier (default: auto-detected from env)
            - Other options are passed to scrape() when fetching URLs
        :return: Firecrawl-like agent result with extracted data and sources.
        """
        schema = options.pop("schema", None)
        model = options.pop("model", None)

        # Step 1: Gather context from URLs or search
        sources: List[str] = []
        context_parts: List[str] = []

        if urls:
            # Scrape provided URLs
            formats = options.pop("formats", ["markdown"])
            for url in urls:
                try:
                    page_result = self.scrape(url=url, formats=formats, **options)
                    if page_result.get("success"):
                        sources.append(url)
                        markdown = page_result.get("data", {}).get("markdown", "")
                        if markdown:
                            context_parts.append(f"## Content from {url}\n\n{markdown}")
                except Exception:
                    # Skip failed URLs but continue
                    continue
        else:
            # If no URLs provided, use search to find relevant pages
            # Search for the prompt and scrape top results
            try:
                search_results = self.search(query=prompt, limit=3)
                if search_results.get("success"):
                    web_results = search_results.get("data", {}).get("web", [])
                    formats = options.pop("formats", ["markdown"])
                    for result in web_results[:3]:  # Top 3 results
                        url = result.get("url", "")
                        if url:
                            try:
                                page_result = self.scrape(url=url, formats=formats, **options)
                                if page_result.get("success"):
                                    sources.append(url)
                                    markdown = page_result.get("data", {}).get("markdown", "")
                                    if markdown:
                                        context_parts.append(f"## Content from {url}\n\n{markdown}")
                            except Exception:
                                continue
            except Exception:
                pass

        if not context_parts:
            return {
                "success": False,
                "data": {},
                "sources": [],
                "error": "No content could be retrieved from the provided URLs or search.",
            }

        # Step 2: Extract structured data using LLM
        context = "\n\n".join(context_parts)

        if extract_structured_data is None:
            return {
                "success": False,
                "data": {},
                "sources": sources,
                "error": "LLM support not available. Install openai package: pip install openai",
            }

        try:
            extracted_data = extract_structured_data(
                prompt=prompt,
                context=context,
                schema=schema,
                model=model,
            )
        except ValueError as e:
            return {
                "success": False,
                "data": {},
                "sources": sources,
                "error": str(e),
            }

        return {
            "success": True,
            "data": extracted_data,
            "sources": sources,
        }

