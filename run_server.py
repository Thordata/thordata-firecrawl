#!/usr/bin/env python3
"""
Simple script to run the Thordata Firecrawl API server.
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import uvicorn
from thordata_firecrawl.api import app

if __name__ == "__main__":
    port = int(os.getenv("PORT", "3002"))
    host = os.getenv("HOST", "0.0.0.0")
    
    print(f"Starting Thordata Firecrawl API server on http://{host}:{port}")
    print(f"API docs available at http://{host}:{port}/docs")
    
    uvicorn.run(app, host=host, port=port, log_level="info")
