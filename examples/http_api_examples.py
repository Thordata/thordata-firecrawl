"""
HTTP API usage examples for Thordata Firecrawl.

This example demonstrates how to use the HTTP API directly with curl and Python requests.
"""

import json
import os
import requests
from typing import Dict, Any

# Configuration
API_BASE_URL = os.getenv("THORDATA_FIRECRAWL_API_URL", "http://localhost:3002")
API_KEY = os.getenv("THORDATA_API_KEY", "your-api-key-here")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


def scrape_example() -> Dict[str, Any]:
    """Example: Scrape a single URL."""
    print("Example 1: Scrape a single URL")
    
    url = f"{API_BASE_URL}/v1/scrape"
    payload = {
        "url": "https://www.thordata.com",
        "formats": ["markdown", "html"],
        "scrapeOptions": {
            "javascript": True,
            "waitFor": 2000,  # Wait 2 seconds for JS to load
        },
    }
    
    response = requests.post(url, headers=HEADERS, json=payload)
    response.raise_for_status()
    return response.json()


def batch_scrape_example() -> Dict[str, Any]:
    """Example: Batch scrape multiple URLs."""
    print("\nExample 2: Batch scrape multiple URLs")
    
    url = f"{API_BASE_URL}/v1/batch-scrape"
    payload = {
        "urls": [
            "https://www.thordata.com",
            "https://www.thordata.com/about",
        ],
        "formats": ["markdown"],
        "scrapeOptions": {
            "javascript": True,
        },
    }
    
    response = requests.post(url, headers=HEADERS, json=payload)
    response.raise_for_status()
    return response.json()


def crawl_example() -> Dict[str, Any]:
    """Example: Start a crawl job."""
    print("\nExample 3: Start a crawl job")
    
    url = f"{API_BASE_URL}/v1/crawl"
    payload = {
        "url": "https://www.thordata.com",
        "limit": 10,
        "maxDepth": 2,
        "includePaths": ["/docs/*"],
        "excludePaths": ["/privacy*"],
        "scrapeOptions": {
            "formats": ["markdown"],
        },
    }
    
    # Optional: Add clientJobId for idempotency
    params = {"clientJobId": "my-unique-job-123"}
    
    response = requests.post(url, headers=HEADERS, json=payload, params=params)
    response.raise_for_status()
    result = response.json()
    
    job_id = result["id"]
    print(f"Job ID: {job_id}")
    print(f"Status URL: {result['url']}")
    
    return result


def crawl_status_example(job_id: str) -> Dict[str, Any]:
    """Example: Check crawl job status."""
    print(f"\nExample 4: Check crawl job status (job_id={job_id})")
    
    url = f"{API_BASE_URL}/v1/crawl/{job_id}"
    
    # Optional: Add pagination
    params = {"offset": 0, "limit": 5}
    
    response = requests.get(url, headers=HEADERS, params=params)
    response.raise_for_status()
    return response.json()


def search_example() -> Dict[str, Any]:
    """Example: Web search."""
    print("\nExample 5: Web search")
    
    url = f"{API_BASE_URL}/v1/search"
    payload = {
        "query": "Thordata web data API",
        "limit": 5,
        "engine": "google",
        "country": "us",
    }
    
    response = requests.post(url, headers=HEADERS, json=payload)
    response.raise_for_status()
    return response.json()


def search_and_scrape_example() -> Dict[str, Any]:
    """Example: Search and scrape top results."""
    print("\nExample 6: Search and scrape")
    
    url = f"{API_BASE_URL}/v1/search-and-scrape"
    payload = {
        "query": "Thordata web scraping",
        "searchLimit": 3,
        "formats": ["markdown"],
        "scrapeOptions": {
            "javascript": True,
        },
    }
    
    response = requests.post(url, headers=HEADERS, json=payload)
    response.raise_for_status()
    return response.json()


def agent_example() -> Dict[str, Any]:
    """Example: Agent-based structured extraction."""
    print("\nExample 7: Agent-based extraction")
    
    url = f"{API_BASE_URL}/v1/agent"
    payload = {
        "prompt": "Extract company information including name, description, and founding year",
        "urls": ["https://www.thordata.com"],
        "schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string"},
                "description": {"type": "string"},
                "founded": {"type": "string"},
            },
            "required": ["company_name"],
        },
        "formats": ["markdown"],
        "searchLimit": 3,
    }
    
    response = requests.post(url, headers=HEADERS, json=payload)
    response.raise_for_status()
    return response.json()


def map_example() -> Dict[str, Any]:
    """Example: Map (discover links)."""
    print("\nExample 8: Map (link discovery)")
    
    url = f"{API_BASE_URL}/v1/map"
    payload = {
        "url": "https://www.thordata.com",
        "search": "docs",  # Optional: filter links by search term
    }
    
    response = requests.post(url, headers=HEADERS, json=payload)
    response.raise_for_status()
    return response.json()


def main():
    """Run all examples."""
    print("=" * 60)
    print("Thordata Firecrawl HTTP API Examples")
    print("=" * 60)
    print(f"API Base URL: {API_BASE_URL}")
    print(f"API Key: {API_KEY[:10]}..." if len(API_KEY) > 10 else "API Key: Not set")
    print("=" * 60)
    
    try:
        # Example 1: Scrape
        result = scrape_example()
        print(f"Success: {result.get('success')}")
        if result.get("success"):
            print(f"Data keys: {list(result.get('data', {}).keys())}")
        
        # Example 2: Batch scrape
        result = batch_scrape_example()
        print(f"Success: {result.get('success')}")
        print(f"Results count: {len(result.get('results', []))}")
        
        # Example 3: Crawl (async job)
        crawl_result = crawl_example()
        job_id = crawl_result.get("id")
        
        # Example 4: Check crawl status
        if job_id:
            import time
            print("\nWaiting 2 seconds before checking status...")
            time.sleep(2)
            status = crawl_status_example(job_id)
            print(f"Status: {status.get('status')}")
            print(f"Total: {status.get('total')}")
            print(f"Completed: {status.get('completed')}")
        
        # Example 5: Search
        result = search_example()
        print(f"Success: {result.get('success')}")
        if result.get("success"):
            web_results = result.get("data", {}).get("web", [])
            print(f"Search results: {len(web_results)}")
        
        # Example 6: Search and scrape
        result = search_and_scrape_example()
        print(f"Success: {result.get('success')}")
        print(f"Results count: {len(result.get('results', []))}")
        
        # Example 7: Agent
        result = agent_example()
        print(f"Success: {result.get('success')}")
        if result.get("success"):
            print(f"Extracted data: {json.dumps(result.get('data', {}), indent=2)}")
            print(f"Sources: {result.get('sources', [])}")
        
        # Example 8: Map
        result = map_example()
        print(f"Success: {result.get('success')}")
        print(f"Links found: {len(result.get('links', []))}")
        
        print("\n" + "=" * 60)
        print("All examples completed successfully!")
        print("=" * 60)
        
    except requests.exceptions.HTTPError as e:
        print(f"\nHTTP Error: {e}")
        if e.response is not None:
            print(f"Status Code: {e.response.status_code}")
            print(f"Response: {e.response.text}")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
