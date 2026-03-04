"""LLM integration for structured extraction in agent mode.

Supports OpenAI-compatible APIs (OpenAI, SiliconFlow, DeepSeek, etc.) for extracting
structured data from web content.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional, Tuple

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


def get_llm_client() -> Optional[Tuple[Any, str]]:
    """Initialize OpenAI-compatible client from environment variables."""
    if OpenAI is None:
        return None

    api_key = os.getenv("OPENAI_API_KEY")
    api_base = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
    model = os.getenv("OPENAI_MODEL", "auto")

    if not api_key:
        return None

    # Auto-detect model if set to "auto"
    if model == "auto":
        api_base_lower = api_base.lower()
        if "siliconflow" in api_base_lower:
            model = "Qwen/Qwen2.5-7B-Instruct"
        elif "deepseek" in api_base_lower:
            model = "deepseek-chat"
        elif "openai.com" in api_base_lower:
            model = "gpt-3.5-turbo"
        else:
            model = "gpt-3.5-turbo"

    client = OpenAI(api_key=api_key, base_url=api_base)
    return client, model


def _friendly_llm_error(
    *,
    err: Exception,
    api_base: str,
    model: str,
    schema_enabled: bool,
) -> str:
    raw = str(err).strip()
    raw_lower = raw.lower()

    status = getattr(err, "status_code", None)

    # Heuristic detection if SDK doesn't expose status_code
    if status is None:
        if "401" in raw_lower and ("unauthor" in raw_lower or "invalid api key" in raw_lower):
            status = 401
        elif "403" in raw_lower and "forbid" in raw_lower:
            status = 403
        elif "404" in raw_lower and "not found" in raw_lower:
            status = 404
        elif "429" in raw_lower and ("rate" in raw_lower or "quota" in raw_lower):
            status = 429

    hints = []
    if status in (401, 403):
        hints.append(
            "Auth failed: ensure OPENAI_API_KEY matches OPENAI_API_BASE (do not mix keys across providers)."
        )
    if status == 404 and ("model" in raw_lower or "not found" in raw_lower):
        hints.append("Model not found/unavailable: verify OPENAI_MODEL is supported by your provider.")
    if status == 429:
        hints.append("Rate limited/quota exceeded: retry later, reduce concurrency, or use a higher-quota key.")
    if "timeout" in raw_lower or "timed out" in raw_lower:
        hints.append("Request timed out: check network connectivity or use a more stable OPENAI_API_BASE.")
    if schema_enabled and ("response_format" in raw_lower or "json_object" in raw_lower):
        hints.append("Your provider may not support response_format=json_object: try without schema.")

    base = f"LLM call failed (OPENAI_API_BASE={api_base}, OPENAI_MODEL={model})"
    if hints:
        return f"{base}: {raw} | Tips: {' '.join(hints)}"
    return f"{base}: {raw}"


def extract_structured_data(
    prompt: str,
    context: str,
    schema: Optional[Dict[str, Any]] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Extract structured data from context using LLM."""

    api_base = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")

    llm_info = get_llm_client()
    if llm_info is None:
        raise ValueError(
            "LLM not configured: set OPENAI_API_KEY. Optionally set OPENAI_API_BASE and OPENAI_MODEL (OpenAI-compatible providers are supported)."
        )

    client, default_model = llm_info
    model_to_use = model or default_model

    system_prompt = "You are a helpful assistant that extracts structured information from web content."
    if schema:
        system_prompt += f"\n\nExtract data according to this JSON schema:\n{json.dumps(schema, indent=2)}"
        system_prompt += "\n\nReturn ONLY valid JSON that matches the schema. Do not include any explanation or markdown formatting."

    # Limit context length to reduce token overflow risk.
    user_prompt = f"{prompt}\n\nContent to extract from:\n\n{context[:8000]}"

    try:
        kwargs: Dict[str, Any] = {}
        if schema:
            kwargs["response_format"] = {"type": "json_object"}

        response = client.chat.completions.create(
            model=model_to_use,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            **kwargs,
        )

        content = response.choices[0].message.content
        if not content:
            return {}

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            import re

            json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(1))
            return json.loads(content)

    except Exception as e:
        raise ValueError(
            _friendly_llm_error(
                err=e,
                api_base=api_base,
                model=model_to_use,
                schema_enabled=bool(schema),
            )
        ) from e
