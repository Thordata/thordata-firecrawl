#!/usr/bin/env python3
"""Simple script to run the Thordata Firecrawl API server."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import uvicorn

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency at runtime
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Thordata Firecrawl API server (FastAPI + Uvicorn)."
    )
    parser.add_argument(
        "--host",
        default=None,
        help='Bind host. Overrides $HOST if set. Default: "0.0.0.0".',
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Bind port. Overrides $PORT if set. Default: 3002.",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload (dev only). Equivalent to uvicorn --reload.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    port = args.port if args.port is not None else int(os.getenv("PORT", "3002"))
    host = args.host if args.host is not None else os.getenv("HOST", "0.0.0.0")

    print(f"Starting Thordata Firecrawl API server on http://{host}:{port}")
    print(f"API docs available at http://{host}:{port}/docs")

    # Use import string so --reload works reliably.
    uvicorn.run(
        "thordata_firecrawl.api:app",
        host=host,
        port=port,
        log_level="info",
        reload=args.reload,
    )
