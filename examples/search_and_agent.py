"""
Search and Agent examples using Thordata Firecrawl.

This example demonstrates web search and agent-based structured extraction.
"""

import os
from thordata_firecrawl import ThordataCrawl

# Initialize client
api_key = os.getenv("THORDATA_API_KEY", "your-api-key-here")
client = ThordataCrawl(api_key=api_key)

# Example 1: Web search
print("Example 1: Web search")
search_result = client.search(
    query="best web scraping tools 2026",
    limit=5,
    engine="google",
    country="us",
)

print(f"Found {len(search_result['data']['web'])} results:")
for i, result in enumerate(search_result["data"]["web"], 1):
    print(f"\n{i}. {result['title']}")
    print(f"   URL: {result['url']}")
    print(f"   Snippet: {result['snippet'][:100]}...")

# Example 2: Agent with structured extraction (MVP)
print("\n\nExample 2: Agent-based extraction (MVP)")
# Note: Full LLM integration is planned for future versions
agent_result = client.agent(
    prompt="Extract key information about the company",
    urls=["https://example.com"],
    schema={
        "type": "object",
        "properties": {
            "company_name": {"type": "string"},
            "description": {"type": "string"},
            "founded": {"type": "string"},
        },
    },
)

print(f"Sources used: {agent_result['sources']}")
print(f"Extracted data: {agent_result['data']}")
if "note" in agent_result:
    print(f"Note: {agent_result['note']}")
