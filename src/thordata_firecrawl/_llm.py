"""
LLM integration for structured extraction in agent mode.

Supports OpenAI-compatible APIs (OpenAI, SiliconFlow, etc.) for extracting
structured data from web content.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


def get_llm_client() -> Optional[Any]:
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
        elif "openai.com" in api_base_lower:
            model = "gpt-3.5-turbo"
        else:
            model = "gpt-3.5-turbo"

    client = OpenAI(api_key=api_key, base_url=api_base)
    return client, model


def extract_structured_data(
    prompt: str,
    context: str,
    schema: Optional[Dict[str, Any]] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Extract structured data from context using LLM.

    :param prompt: Extraction prompt or task description.
    :param context: Web content to extract from (markdown or HTML).
    :param schema: Optional JSON schema for structured output.
    :param model: Optional model override.
    :return: Extracted structured data.
    """
    llm_info = get_llm_client()
    if llm_info is None:
        raise ValueError(
            "LLM client not available. Set OPENAI_API_KEY environment variable. "
            "Optionally set OPENAI_API_BASE and OPENAI_MODEL."
        )

    client, default_model = llm_info
    model_to_use = model or default_model

    # Build system prompt
    system_prompt = "You are a helpful assistant that extracts structured information from web content."
    if schema:
        system_prompt += f"\n\nExtract data according to this JSON schema:\n{json.dumps(schema, indent=2)}"
        system_prompt += "\n\nReturn ONLY valid JSON that matches the schema. Do not include any explanation or markdown formatting."

    # Build user prompt
    user_prompt = f"{prompt}\n\nContent to extract from:\n\n{context[:8000]}"  # Limit context length

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

        # Parse JSON response
        try:
            extracted = json.loads(content)
            return extracted
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks
            import re

            json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(1))
            # Last resort: try to parse as-is
            return json.loads(content)

    except Exception as e:
        raise ValueError(f"LLM extraction failed: {e}") from e
