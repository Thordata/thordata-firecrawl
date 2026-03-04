#!/usr/bin/env python3
"""
Export OpenAPI spec from FastAPI app to openapi.json and openapi.yaml.
"""

import json
from pathlib import Path

from thordata_firecrawl.api import app


def main() -> None:
    spec = app.openapi()
    root = Path(__file__).parent

    # JSON
    json_path = root / "openapi.json"
    json_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    print(f"OpenAPI JSON written to {json_path}")

    # YAML (optional, requires PyYAML)
    try:
        import yaml  # type: ignore
    except Exception:
        print("PyYAML not installed; skipping openapi.yaml export. Install with `pip install pyyaml`.")
    else:
        yaml_path = root / "openapi.yaml"
        yaml_path.write_text(yaml.dump(spec, sort_keys=False), encoding="utf-8")
        print(f"OpenAPI YAML written to {yaml_path}")


if __name__ == "__main__":
    main()

