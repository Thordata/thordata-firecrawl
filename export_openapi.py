#!/usr/bin/env python3
"""
Export OpenAPI spec from FastAPI app to openapi.json.
"""

import json
from pathlib import Path

from thordata_firecrawl.api import app


def main() -> None:
    spec = app.openapi()
    out_path = Path(__file__).parent / "openapi.json"
    out_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    print(f"OpenAPI spec written to {out_path}")


if __name__ == "__main__":
    main()

{
  "cells": [],
  "metadata": {
    "language_info": {
      "name": "python"
    }
  },
  "nbformat": 4,
  "nbformat_minor": 2
}