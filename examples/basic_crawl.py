"""
Basic crawl example using Thordata Firecrawl.

This example demonstrates how to crawl a website and extract AI-ready content
from multiple pages.
"""

import os
from thordata_firecrawl import ThordataCrawl

# Initialize client
api_key = os.getenv("THORDATA_API_KEY", "your-api-key-here")
client = ThordataCrawl(api_key=api_key)

# Example 1: Simple crawl with default settings
print("Example 1: Basic crawl (limit=5)")
result = client.crawl(
    url="https://example.com",
    limit=5,
    formats=["markdown"],
)

print(f"Status: {result['status']}")
print(f"Total pages: {result['total']}")
print(f"Completed: {result['completed']}")
for i, page in enumerate(result["data"][:2], 1):  # Show first 2 pages
    print(f"\nPage {i}:")
    print(f"  URL: {page['metadata']['sourceUrl']}")
    print(f"  Title: {page['metadata'].get('title', 'N/A')}")
    print(f"  Markdown preview: {page['markdown'][:100]}..." if page.get('markdown') else "  No markdown")

# Example 2: Crawl with depth control and subdomain inclusion
print("\n\nExample 2: Crawl with max depth and subdomains")
result = client.crawl(
    url="https://example.com",
    limit=10,
    maxDepth=2,  # Only crawl 2 levels deep
    includeSubdomains=True,
    formats=["markdown", "html"],
    concurrency=3,  # Use 3 concurrent requests
)

print(f"Status: {result['status']}")
print(f"Total pages: {result['total']}")

# Example 3: Map (discover links without full content)
print("\n\nExample 3: Map (link discovery)")
map_result = client.map(
    url="https://example.com",
    includeSubdomains=False,
)

print(f"Found {len(map_result['links'])} links:")
for link in map_result["links"][:5]:  # Show first 5 links
    print(f"  - {link['url']}")
