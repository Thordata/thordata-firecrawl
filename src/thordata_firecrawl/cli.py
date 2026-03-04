from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import click

from .client import ThordataCrawl

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency at runtime
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv()


def _write_output(output: str, out: Optional[Path]) -> None:
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(output, encoding="utf-8")
    else:
        click.echo(output)


@click.group(invoke_without_command=True)
@click.option(
    "--api-key",
    envvar=["THORDATA_API_KEY", "THORDATA_SCRAPER_TOKEN"],
    help="Thordata API key. Supports THORDATA_API_KEY or THORDATA_SCRAPER_TOKEN.",
)
@click.option(
    "--base-url",
    envvar="THORDATA_BASE_URL",
    default=None,
    help="Optional Thordata API base URL.",
)
@click.pass_context
def main(ctx: click.Context, api_key: str, base_url: Optional[str]) -> None:
    """
    Thordata Firecrawl CLI – high-level web data toolkit built on Thordata.
    """
    # Do not validate credentials here so `--help` works for all subcommands.
    # Each command will validate credentials when executed.
    ctx.obj = {"api_key": api_key, "base_url": base_url}


def _require_client(ctx: click.Context) -> ThordataCrawl:
    obj = ctx.obj or {}
    api_key = obj.get("api_key") if isinstance(obj, dict) else None
    base_url = obj.get("base_url") if isinstance(obj, dict) else None
    if not api_key:
        raise click.UsageError(
            "API key is required. Set --api-key or THORDATA_API_KEY / THORDATA_SCRAPER_TOKEN."
        )
    return ThordataCrawl(api_key=api_key, base_url=base_url)


@main.command()
@click.argument("url")
@click.option(
    "--format",
    "formats",
    multiple=True,
    default=["markdown"],
    help="Output format(s), e.g. markdown, html, screenshot.",
)
@click.option(
    "--out",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Optional output file path. If omitted, print to stdout.",
)
@click.pass_context
def scrape(ctx: click.Context, url: str, formats: tuple[str, ...], out: Optional[Path]) -> None:
    """
    Scrape a single URL and output AI-ready content.
    """
    client = _require_client(ctx)
    result = client.scrape(url=url, formats=list(formats))
    # Serialize result as JSON; future versions may offer format-specific output helpers.
    _write_output(json.dumps(result, ensure_ascii=False, indent=2), out)


@main.command(name="batch-scrape")
@click.argument("url", nargs=-1)
@click.option(
    "--format",
    "formats",
    multiple=True,
    default=["markdown"],
    help="Output format(s), e.g. markdown, html, screenshot.",
)
@click.option(
    "--out",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Optional output file path. If omitted, print to stdout.",
)
@click.pass_context
def batch_scrape(
    ctx: click.Context,
    url: tuple[str, ...],
    formats: tuple[str, ...],
    out: Optional[Path],
) -> None:
    """
    Scrape multiple URLs in one command (batch scrape).

    Example:
      thordata-firecrawl batch-scrape https://a.com https://b.com --format markdown
    """
    if not url:
        raise click.UsageError("At least one URL is required.")
    client = _require_client(ctx)
    result = client.batch_scrape(urls=list(url), formats=list(formats))
    _write_output(json.dumps(result, ensure_ascii=False, indent=2), out)

@main.command()
@click.argument("url")
@click.option("--limit", type=int, default=100, help="Maximum number of pages to crawl.")
@click.option(
    "--max-depth",
    type=int,
    default=None,
    help="Maximum crawl depth (None = unlimited).",
)
@click.option(
    "--include-subdomains",
    is_flag=True,
    default=False,
    help="Include subdomains when crawling.",
)
@click.option(
    "--concurrency",
    type=int,
    default=5,
    help="Number of concurrent requests (default: 5).",
)
@click.option(
    "--format",
    "formats",
    multiple=True,
    default=["markdown"],
    help="Output format(s) for each page, e.g. markdown, html, screenshot.",
)
@click.option(
    "--out",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Optional output file path. If omitted, print to stdout.",
)
@click.pass_context
def crawl(
    ctx: click.Context,
    url: str,
    limit: int,
    max_depth: Optional[int],
    include_subdomains: bool,
    concurrency: int,
    formats: tuple[str, ...],
    out: Optional[Path],
) -> None:
    """
    Crawl a website starting from the given URL.

    Discovers links from HTML and crawls multiple pages using BFS.
    """
    client = _require_client(ctx)
    result = client.crawl(
        url=url,
        limit=limit,
        maxDepth=max_depth,
        includeSubdomains=include_subdomains,
        concurrency=concurrency,
        formats=list(formats),
    )
    _write_output(json.dumps(result, ensure_ascii=False, indent=2), out)


@main.command()
@click.argument("url")
@click.option(
    "--search",
    type=str,
    default=None,
    help="Optional keyword to filter/rank discovered links.",
)
@click.option(
    "--include-subdomains",
    is_flag=True,
    default=False,
    help="Include subdomains when discovering links.",
)
@click.option(
    "--out",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Optional output file path. If omitted, print to stdout.",
)
@click.pass_context
def map(
    ctx: click.Context,
    url: str,
    search: Optional[str],
    include_subdomains: bool,
    out: Optional[Path],
) -> None:
    """
    Discover URLs on a website without fetching full content.

    Fetches the seed page and extracts all links, optionally filtered by keyword.
    """
    client = _require_client(ctx)
    result = client.map(url=url, search=search, includeSubdomains=include_subdomains)
    _write_output(json.dumps(result, ensure_ascii=False, indent=2), out)


@main.command()
@click.argument("query")
@click.option("--limit", type=int, default=10, help="Maximum number of search results.")
@click.option("--engine", type=str, default="google", help="Search engine (google, bing, yandex).")
@click.option("--country", type=str, default=None, help="Country code (e.g., us, uk).")
@click.option("--language", type=str, default=None, help="Language code (e.g., en, zh).")
@click.option(
    "--out",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Optional output file path. If omitted, print to stdout.",
)
@click.pass_context
def search(
    ctx: click.Context,
    query: str,
    limit: int,
    engine: str,
    country: Optional[str],
    language: Optional[str],
    out: Optional[Path],
) -> None:
    """
    Search the web via Thordata SERP API.

    Returns search results in Firecrawl-compatible format.
    """
    client = _require_client(ctx)
    result = client.search(
        query=query,
        limit=limit,
        engine=engine,
        country=country,
        language=language,
    )
    _write_output(json.dumps(result, ensure_ascii=False, indent=2), out)


@main.command(name="search-and-scrape")
@click.argument("query")
@click.option(
    "--search-limit",
    type=int,
    default=5,
    help="Number of search results to scrape (default: 5).",
)
@click.option(
    "--format",
    "formats",
    multiple=True,
    default=["markdown"],
    help="Output format(s) when scraping, e.g. markdown, html, screenshot.",
)
@click.option(
    "--out",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Optional output file path. If omitted, print to stdout.",
)
@click.pass_context
def search_and_scrape(
    ctx: click.Context,
    query: str,
    search_limit: int,
    formats: tuple[str, ...],
    out: Optional[Path],
) -> None:
    """
    Search the web and scrape the top results in one command.

    This is a convenience wrapper around `search` + `scrape`.
    """
    client = _require_client(ctx)
    result = client.search_and_scrape(
      query=query,
      search_limit=search_limit,
      scrape_formats=list(formats),
    )
    _write_output(json.dumps(result, ensure_ascii=False, indent=2), out)

@main.command()
@click.argument("prompt")
@click.option(
    "--url",
    "urls",
    multiple=True,
    help="URL(s) to scrape for context. Can be specified multiple times.",
)
@click.option(
    "--schema",
    type=click.Path(exists=True, path_type=Path),
    help="Path to JSON schema file for structured output.",
)
@click.option("--model", type=str, default=None, help="LLM model identifier (optional). Overrides OPENAI_MODEL.")
@click.option(
    "--out",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Optional output file path. If omitted, print to stdout.",
)
@click.pass_context
def agent(
    ctx: click.Context,
    prompt: str,
    urls: tuple[str, ...],
    schema: Optional[Path],
    model: Optional[str],
    out: Optional[Path],
) -> None:
    """
    Run an agent task to extract structured data from web content.

    Scrapes the provided URLs and uses an OpenAI-compatible LLM to extract data based on the prompt (optional JSON schema).
    """
    schema_dict = None
    if schema:
        schema_dict = json.loads(schema.read_text(encoding="utf-8"))

    client = _require_client(ctx)
    result = client.agent(
        prompt=prompt,
        urls=list(urls) if urls else None,
        schema=schema_dict,
        model=model,
    )
    _write_output(json.dumps(result, ensure_ascii=False, indent=2), out)

