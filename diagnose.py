#!/usr/bin/env python3
"""
Quick diagnostic script for Thordata Firecrawl API.

This script helps diagnose common issues with the API deployment and functionality.

Usage:
    python diagnose.py [--api-key YOUR_KEY] [--url http://localhost:3002]
"""

import os
import sys
import time
from typing import Optional

try:
    import requests
except ImportError:
    print("❌ Missing dependency: requests")
    print("Install with: pip install requests")
    sys.exit(1)


def print_section(title: str):
    """Print section header."""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def check_health(base_url: str) -> bool:
    """Check API health status."""
    print_section("📊 Health Check")
    
    try:
        resp = requests.get(f"{base_url}/health", timeout=10)
        print(f"Status Code: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            print(f"✓ Status: {data.get('status', 'unknown')}")
            print(f"✓ Version: {data.get('version', 'unknown')}")
            
            config = data.get("configuration", {})
            print(f"✓ Scraper API: {config.get('scraper_api', 'unknown')}")
            print(f"✓ LLM Service: {config.get('llm_service', 'unknown')}")
            print(f"✓ LLM Base URL: {config.get('llm_base_url', 'unknown')}")
            print(f"✓ LLM Model: {config.get('llm_model', 'unknown')}")
            
            # Check configuration
            if config.get("scraper_api") == "missing":
                print("\n⚠️  WARNING: Scraper API token not configured!")
                print("   Set THORDATA_SCRAPER_TOKEN or THORDATA_API_KEY environment variable")
            
            if config.get("llm_service") == "missing":
                print("\n⚠️  WARNING: LLM service not configured!")
                print("   Agent functionality will not work without OPENAI_API_KEY")
            
            return True
        else:
            print(f"❌ Health check failed with status {resp.status_code}")
            print(f"Response: {resp.text[:200]}")
            return False
    
    except requests.exceptions.ConnectionError:
        print("❌ Connection refused - API server may not be running")
        print("\nTroubleshooting:")
        print("  1. Start the server: python run_server.py")
        print("  2. Or use Docker: docker-compose up -d")
        print("  3. Check if Render instance is awake (cold start takes 15-30s)")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def check_scrape(base_url: str, api_key: str) -> bool:
    """Test scrape functionality."""
    print_section("📄 Scrape Test")
    
    if not api_key:
        print("⚠️  Skipping: No API key provided")
        return True
    
    try:
        payload = {
            "url": "https://www.thordata.com",
            "formats": ["markdown"]
        }
        
        headers = {"Authorization": f"Bearer {api_key}"}
        resp = requests.post(
            f"{base_url}/v1/scrape",
            json=payload,
            headers=headers,
            timeout=30
        )
        
        print(f"Status Code: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success"):
                markdown = data.get("data", {}).get("markdown", "")
                print(f"✓ Scrape successful")
                print(f"  Content length: {len(markdown)} chars")
                return True
            else:
                error = data.get("error", "Unknown error")
                print(f"❌ Scrape failed: {error}")
                
                # Provide troubleshooting tips
                if "authentication" in error.lower():
                    print("\n💡 Tip: Check your API key is correct")
                elif "timeout" in error.lower():
                    print("\n💡 Tip: Try increasing timeout or enabling JavaScript rendering")
                
                return False
        elif resp.status_code == 401:
            print("❌ Authentication failed - invalid API key")
            print("\n💡 Tip: Verify your API key from https://dashboard.thordata.com")
            return False
        else:
            print(f"❌ Request failed: {resp.status_code}")
            print(f"Response: {resp.text[:200]}")
            return False
    
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def check_agent(base_url: str, api_key: str) -> bool:
    """Test agent functionality."""
    print_section("🤖 Agent Test")
    
    if not api_key:
        print("⚠️  Skipping: No API key provided")
        return True
    
    try:
        payload = {
            "prompt": "Extract company name",
            "urls": ["https://www.thordata.com"],
            "formats": ["markdown"]
        }
        
        headers = {"Authorization": f"Bearer {api_key}"}
        resp = requests.post(
            f"{base_url}/v1/agent",
            json=payload,
            headers=headers,
            timeout=60
        )
        
        print(f"Status Code: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success"):
                print(f"✓ Agent extraction successful")
                print(f"  Data: {data.get('data', {})}")
                return True
            else:
                error = data.get("error", "Unknown error")
                print(f"❌ Agent failed: {error}")
                
                # Check if it's LLM configuration issue
                if "LLM" in error or "llm" in error.lower():
                    print("\n⚠️  LLM service not configured")
                    print("   This is optional - set OPENAI_API_KEY to enable")
                    return True  # Not a critical failure
                
                return False
        else:
            print(f"❌ Request failed: {resp.status_code}")
            return False
    
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def check_render_specifics(base_url: str) -> bool:
    """Check Render-specific configurations."""
    print_section("☁️ Render Deployment Check")
    
    if "onrender.com" not in base_url:
        print("ℹ️  Not a Render URL - skipping")
        return True
    
    try:
        # Test cold start
        print("Testing cold start...")
        start = time.time()
        
        resp = requests.get(f"{base_url}/health", timeout=60)
        
        elapsed = int((time.time() - start) * 1000)
        
        if elapsed > 15000:
            print(f"⏱ Cold start detected: {elapsed}ms (>15s)")
            print("   This is normal for Render free tier")
            print("   Consider using UptimeRobot to keep instance warm")
        else:
            print(f"✓ Instance warm: {elapsed}ms")
        
        # Check response
        if resp.status_code == 200:
            print("✓ Render instance responsive")
            return True
        else:
            print(f"❌ Render instance returned {resp.status_code}")
            return False
    
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Thordata Firecrawl Diagnostic Tool")
    parser.add_argument(
        "--url",
        default=os.getenv("FIREFRAWL_BASE_URL", "http://localhost:3002"),
        help="API base URL (default: http://localhost:3002)"
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("THORDATA_SCRAPER_TOKEN") or os.getenv("THORDATA_API_KEY"),
        help="Thordata API key"
    )
    
    args = parser.parse_args()
    
    print("\n" + "█" * 60)
    print("  🔍 Thordata Firecrawl Diagnostic Tool")
    print("█" * 60)
    print(f"\nTarget URL: {args.url}")
    print(f"API Key: {'***' + args.api_key[-4:] if args.api_key else 'None'}")
    print(f"Timestamp: {__import__('datetime').datetime.now().isoformat()}")
    
    # Run diagnostics
    results = []
    
    results.append(("Health Check", check_health(args.url)))
    results.append(("Scrape Test", check_scrape(args.url, args.api_key)))
    results.append(("Agent Test", check_agent(args.url, args.api_key)))
    results.append(("Render Check", check_render_specifics(args.url)))
    
    # Summary
    print_section("📋 Diagnostic Summary")
    
    for name, passed in results:
        icon = "✅" if passed else "❌"
        print(f"{icon} {name}")
    
    all_passed = all(passed for _, passed in results)
    
    print("\n" + "-" * 60)
    if all_passed:
        print("🎉 All diagnostics passed! Your API is ready to use.")
    else:
        print("⚠️  Some diagnostics failed. Please review the issues above.")
        print("\n📚 For detailed troubleshooting, see TROUBLESHOOTING.md")
    
    print("\n" + "=" * 60)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
