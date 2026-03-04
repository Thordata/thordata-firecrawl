"""
Internal crawler utilities for link discovery and multi-page crawling.

This module provides low-level helpers for extracting links from HTML,
normalizing URLs, and managing crawl queues.
"""

from __future__ import annotations

import html.parser
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse, urlunparse


class LinkExtractor(html.parser.HTMLParser):
    """Extract all <a href> links from HTML content."""

    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.links: List[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if tag == "a":
            for attr, value in attrs:
                if attr == "href" and value:
                    # Resolve relative URLs
                    absolute = urljoin(self.base_url, value)
                    self.links.append(absolute)

    def extract_links(self, html_content: str) -> List[str]:
        """Parse HTML and return list of absolute URLs."""
        self.links = []
        try:
            self.feed(html_content)
        except Exception:
            # Ignore parsing errors, return what we found so far
            pass
        return self.links


def normalize_url(url: str) -> str:
    """
    Normalize a URL for deduplication.

    - Remove fragment (#anchor)
    - Remove trailing slash (optional, but helps with dedup)
    - Convert to lowercase for scheme/host
    """
    parsed = urlparse(url)
    # Remove fragment
    normalized = urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/") or "/",
            parsed.params,
            parsed.query,
            "",  # Remove fragment
        )
    )
    return normalized


def is_same_domain(url1: str, url2: str, include_subdomains: bool = False) -> bool:
    """Check if two URLs belong to the same domain."""
    host1 = urlparse(url1).netloc.lower()
    host2 = urlparse(url2).netloc.lower()

    if host1 == host2:
        return True

    if include_subdomains:
        # Extract base domain (e.g., "example.com" from "www.example.com")
        parts1 = host1.split(".")
        parts2 = host2.split(".")
        if len(parts1) >= 2 and len(parts2) >= 2:
            base1 = ".".join(parts1[-2:])
            base2 = ".".join(parts2[-2:])
            return base1 == base2

    return False


def extract_title_from_html(html_content: str) -> Optional[str]:
    """Extract <title> tag content from HTML."""
    parser = html.parser.HTMLParser()

    class TitleExtractor(html.parser.HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.title: Optional[str] = None
            self.in_title = False

        def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
            if tag == "title":
                self.in_title = True

        def handle_endtag(self, tag: str) -> None:
            if tag == "title":
                self.in_title = False

        def handle_data(self, data: str) -> None:
            if self.in_title:
                self.title = (self.title or "") + data

    extractor = TitleExtractor()
    try:
        extractor.feed(html_content)
        return extractor.title.strip() if extractor.title else None
    except Exception:
        return None


def discover_links(
    html_content: str,
    base_url: str,
    seed_url: str,
    include_subdomains: bool = False,
    max_depth: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Discover and filter links from HTML content.

    Returns a list of link dicts with url, title, description fields.
    """
    extractor = LinkExtractor(base_url)
    raw_links = extractor.extract_links(html_content)

    # Normalize and deduplicate
    seen: Set[str] = set()
    links: List[Dict[str, Any]] = []

    for link in raw_links:
        normalized = normalize_url(link)
        if normalized in seen:
            continue

        # Filter by domain
        if not is_same_domain(link, seed_url, include_subdomains=include_subdomains):
            continue

        # Basic validation: must be http/https
        parsed = urlparse(link)
        if parsed.scheme not in ("http", "https"):
            continue

        seen.add(normalized)
        links.append(
            {
                "url": link,
                "title": None,  # Could extract from <a> tag text in future
                "description": None,
            }
        )

    return links


def crawl_bfs(
    scrape_func,
    seed_url: str,
    limit: int = 100,
    max_depth: Optional[int] = None,
    include_subdomains: bool = False,
    formats: Optional[List[str]] = None,
    concurrency: int = 5,
    **scrape_options: Any,
) -> Dict[str, Any]:
    """
    BFS-based crawler that discovers and scrapes multiple pages.

    :param scrape_func: Function to call for each URL: scrape_func(url, formats, **options) -> dict
    :param seed_url: Starting URL
    :param limit: Maximum number of pages to crawl
    :param max_depth: Maximum crawl depth (None = unlimited)
    :param include_subdomains: Whether to include subdomains
    :param formats: Output formats for scraping
    :param concurrency: Number of concurrent requests
    :param scrape_options: Extra options passed to scrape_func
    :return: Firecrawl-like crawl result dict
    """
    formats = formats or ["markdown"]
    visited: Set[str] = set()
    queue: deque[Tuple[str, int]] = deque([(seed_url, 0)])  # (url, depth)
    results: List[Dict[str, Any]] = []
    failed_count = 0

    while queue and len(results) < limit:
        # Collect a batch of URLs to process
        batch: List[Tuple[str, int]] = []
        while queue and len(batch) < concurrency and len(results) + len(batch) < limit:
            url, depth = queue.popleft()
            normalized = normalize_url(url)
            if normalized in visited:
                continue
            if max_depth is not None and depth > max_depth:
                continue
            visited.add(normalized)
            batch.append((url, depth))

        if not batch:
            break

        # Scrape batch concurrently
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {
                executor.submit(scrape_func, url=url, formats=formats, **scrape_options): (url, depth)
                for url, depth in batch
            }

            for future in as_completed(futures):
                url, depth = futures[future]
                try:
                    page_result = future.result()
                    if not page_result.get("success"):
                        failed_count += 1
                        continue

                    # Extract HTML for link discovery
                    html_content = page_result.get("data", {}).get("html", "")
                    if html_content and depth < (max_depth or float("inf")):
                        # Discover new links
                        new_links = discover_links(
                            html_content=html_content,
                            base_url=url,
                            seed_url=seed_url,
                            include_subdomains=include_subdomains,
                            max_depth=max_depth,
                        )

                        # Add to queue
                        for link_info in new_links:
                            link_url = link_info["url"]
                            link_normalized = normalize_url(link_url)
                            if link_normalized not in visited:
                                queue.append((link_url, depth + 1))

                    # Build result entry
                    title = None
                    if html_content:
                        title = extract_title_from_html(html_content)

                    results.append(
                        {
                            "markdown": page_result.get("data", {}).get("markdown"),
                            "html": page_result.get("data", {}).get("html"),
                            "screenshot": page_result.get("data", {}).get("screenshot"),
                            "metadata": {
                                "sourceUrl": url,
                                "title": title,
                            },
                        }
                    )

                except Exception:
                    failed_count += 1
                    continue

    return {
        "status": "completed" if len(results) >= limit or not queue else "partial",
        "total": len(results),
        "completed": len(results),
        "failed": failed_count,
        "data": results,
    }
