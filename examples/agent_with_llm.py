"""
Agent example with LLM integration for structured extraction.

This example demonstrates how to use the agent functionality to extract
structured data from web pages using LLM.
"""

import json
import os
from thordata_firecrawl import ThordataCrawl

# Load environment variables (you can use .env file)
# Make sure OPENAI_API_KEY is set for LLM functionality
api_key = os.getenv("THORDATA_API_KEY", "your-thordata-api-key-here")

client = ThordataCrawl(api_key=api_key)

# Example 1: Extract structured data from a single URL
print("Example 1: Extract company information")
result = client.agent(
    prompt="Extract key information about the company including name, description, and founding year",
    urls=["https://example.com"],
    schema={
        "type": "object",
        "properties": {
            "company_name": {"type": "string"},
            "description": {"type": "string"},
            "founded": {"type": "string"},
            "headquarters": {"type": "string"},
        },
        "required": ["company_name"],
    },
)

if result["success"]:
    print(f"Extracted data: {json.dumps(result['data'], indent=2, ensure_ascii=False)}")
    print(f"\nSources used: {result['sources']}")
else:
    print(f"Error: {result.get('error', 'Unknown error')}")

# Example 2: Extract founders information
print("\n\nExample 2: Extract founders information")
result = client.agent(
    prompt="Extract information about company founders including their names and roles",
    urls=["https://example.com/about"],
    schema={
        "type": "object",
        "properties": {
            "founders": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "role": {"type": "string"},
                        "bio": {"type": "string"},
                    },
                    "required": ["name"],
                },
            },
        },
    },
)

if result["success"]:
    print(f"Founders: {json.dumps(result['data'], indent=2, ensure_ascii=False)}")
else:
    print(f"Error: {result.get('error', 'Unknown error')}")

# Example 3: Search and extract (no URLs provided)
print("\n\nExample 3: Search and extract")
result = client.agent(
    prompt="Find and extract information about the latest AI models released in 2026",
    urls=None,  # Will search for the prompt
    schema={
        "type": "object",
        "properties": {
            "models": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "company": {"type": "string"},
                        "release_date": {"type": "string"},
                    },
                },
            },
        },
    },
)

if result["success"]:
    print(f"Models found: {json.dumps(result['data'], indent=2, ensure_ascii=False)}")
    print(f"\nSources: {result['sources']}")
else:
    print(f"Error: {result.get('error', 'Unknown error')}")
