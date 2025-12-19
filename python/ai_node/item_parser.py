from __future__ import annotations

import time
from typing import Any, Dict, List

from openai import OpenAI

try:  # script-mode support
    from openai_utils import optional_env, require_env
except ImportError:
    from .openai_utils import optional_env, require_env


_ITEMS_JSON_SCHEMA: Dict[str, Any] = {
    "name": "items_message",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["items", "timestamp_ms"],
        "properties": {
            "items": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["name", "qty"],
                    "properties": {
                        "name": {"type": "string", "minLength": 1},
                        "qty": {"type": "integer", "minimum": 1},
                    },
                },
            },
            "timestamp_ms": {"type": "integer", "minimum": 0},
        },
    },
    "strict": True,
}


def parse_items_from_text(text: str) -> Dict[str, Any]:
    """
    Use an LLM to parse a user utterance into the project's `items` JSON.

    Example input:
      "콜라 1개, 라면 2개 주세요"
    """
    api_key = require_env("OPENAI_API_KEY")
    model = optional_env("OPENAI_PARSE_MODEL", "gpt-4o-mini")

    client = OpenAI(api_key=api_key)
    created_ms = int(time.time() * 1000)

    prompt = (
        "You are an assistant that extracts a shopping list from text.\n"
        "Return ONLY valid JSON that matches the provided JSON schema.\n"
        "Rules:\n"
        "- Normalize item names into short lowercase ids when possible (e.g., coke, ramen).\n"
        "- If quantity is missing, assume qty=1.\n"
        "- If you are unsure, still produce best-effort items.\n"
        f"- timestamp_ms must be {created_ms}.\n"
        "\n"
        f"Input text: {text}\n"
    )

    # Prefer the Responses API with JSON schema output when available.
    resp = client.responses.create(
        model=model,
        input=prompt,
        response_format={"type": "json_schema", "json_schema": _ITEMS_JSON_SCHEMA},
    )

    data = resp.output_parsed
    if not isinstance(data, dict) or "items" not in data:
        raise RuntimeError("Failed to parse items JSON from model output")
    data["timestamp_ms"] = created_ms
    return data


def validate_items_payload(payload: Dict[str, Any]) -> None:
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("items must be a non-empty list")
    for it in items:
        if not isinstance(it, dict):
            raise ValueError("each item must be an object")
        name = it.get("name")
        qty = it.get("qty")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("item.name must be a non-empty string")
        if not isinstance(qty, int) or qty < 1:
            raise ValueError("item.qty must be an int >= 1")
