#!/usr/bin/env python3
"""
Quick test script to verify the API server works.
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Set test API key if not set
if not os.getenv("THORDATA_API_KEY"):
    os.environ["THORDATA_API_KEY"] = "test-key"

from thordata_firecrawl.api import app

def test_health():
    """Test health endpoint."""
    from fastapi.testclient import TestClient
    
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    print("[OK] Health check passed")

def test_docs():
    """Test that docs are accessible."""
    from fastapi.testclient import TestClient
    
    client = TestClient(app)
    response = client.get("/docs")
    assert response.status_code == 200
    print("[OK] API docs accessible")

if __name__ == "__main__":
    print("Testing Thordata Firecrawl API...")
    try:
        test_health()
        test_docs()
        print("\n[OK] All tests passed! API server is ready.")
    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        sys.exit(1)
