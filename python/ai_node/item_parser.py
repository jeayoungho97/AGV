from __future__ import annotations

import json
import re
import time
from difflib import get_close_matches
from typing import Any, Dict, Iterable, List, Optional

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

_KEYWORDS = {
    "lipstick": ["립스틱", "립 ", "립스 "],
    "ampoule": ["앰플", "앰풀"],
    "shadow": ["섀도", "섀도우", "아이섀도우"],
    "vitamin": ["비타민"],
    "choco": ["초코", "초콜릿", "초콜렛"],
    "tissue": ["휴지", "티슈"],
    "thor": ["토르"],
    "hulk": ["헐크"],
}

# 한글/숫자 수량 매핑
_NUM_WORDS = {
    "한": 1,
    "하나": 1,
    "1": 1,
    "두": 2,
    "둘": 2,
    "2": 2,
    "세": 3,
    "셋": 3,
    "3": 3,
    "네": 4,
    "넷": 4,
    "넉": 4,
    "4": 4,
    "다섯": 5,
    "5": 5,
    "여섯": 6,
    "6": 6,
    "일곱": 7,
    "7": 7,
    "여덟": 8,
    "8": 8,
    "아홉": 9,
    "9": 9,
    "열": 10,
    "10": 10,
}


def _normalize_items_to_allowed(items: List[Dict[str, Any]], allowed: Iterable[str]) -> List[Dict[str, Any]]:
    allowed_list = list(allowed)
    if not allowed_list:
        return items

    allowed_lower = {name.lower(): name for name in allowed_list}
    normalized: List[Dict[str, Any]] = []
    unmatched: List[str] = []
    for it in items:
        raw = str(it.get("name") or "").strip()
        if not raw:
            continue
        lower = raw.lower()
        if lower in allowed_lower:
            canonical = allowed_lower[lower]
        else:
            # fuzzy match to nearest POI id
            matches = get_close_matches(lower, allowed_lower.keys(), n=1, cutoff=0.55)
            if not matches:
                unmatched.append(raw)
                continue
            canonical = allowed_lower[matches[0]]
        qty = it.get("qty", 1)
        try:
            qty = int(qty)
        except Exception:
            qty = 1
        if qty < 1:
            qty = 1
        normalized.append({"name": canonical, "qty": qty})

    # If everything was unmatched, try a more permissive match to avoid empty results.
    if not normalized and unmatched:
        for raw in unmatched:
            lower = raw.lower()
            matches = get_close_matches(lower, allowed_lower.keys(), n=1, cutoff=0.0)
            if not matches:
                continue
            canonical = allowed_lower[matches[0]]
            normalized.append({"name": canonical, "qty": 1})

    return normalized


def _heuristic_items_from_text(text: str, allowed: Iterable[str]) -> List[Dict[str, Any]]:
    allowed_set = set(allowed)
    if not allowed_set:
        return []
    lower_text = text.lower()
    items: List[Dict[str, Any]] = []
    for pid, kws in _KEYWORDS.items():
        if pid not in allowed_set:
            continue
        count = 0
        for kw in kws:
            if kw.lower() in lower_text:
                count = max(count, lower_text.count(kw.lower()))
        if count > 0:
            items.append({"name": pid, "qty": count})
    return items


def _detect_quantity(text: str, keywords: List[str]) -> int:
    if not keywords:
        return 0
    lower = text.lower()
    qty = 0
    for kw in keywords:
        kw_lower = kw.lower()
        # 키워드 + 숫자 패턴 (수량은 키워드 뒤쪽에 붙은 것으로만 계산)
        for m in re.finditer(rf"{re.escape(kw_lower)}\s*개?\s*(\d+)", lower):
            try:
                qty = max(qty, int(m.group(1)))
            except Exception:
                pass
        # 한글 수량어는 키워드 뒤쪽에서만 인식
        for word, val in _NUM_WORDS.items():
            if re.search(rf"{re.escape(kw_lower)}\s*개?\s*{re.escape(word)}", lower):
                qty = max(qty, val)
        # 키워드 출현 횟수로 보정
        for kw in keywords:
            count = lower.count(kw.lower())
            if count > qty:
                qty = count
    return qty


def parse_items_from_text(text: str, allowed_names: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """
    Use an LLM to parse a user utterance into the project's `items` JSON.

    Example input:
      "콜라 1개, 라면 2개 주세요"
    """
    api_key = require_env("OPENAI_API_KEY")
    model = optional_env("OPENAI_PARSE_MODEL", "gpt-4o-mini")

    client = OpenAI(api_key=api_key)
    created_ms = int(time.time() * 1000)

    allowed_hint = ""
    allowed_list = list(allowed_names or [])
    if allowed_list:
        allowed_hint = (
            "You must choose item names ONLY from this allowed list (case-insensitive): "
            + ", ".join(allowed_list)
            + ". Do not invent new names. If you are unsure, pick the closest allowed name.\n"
        )

    prompt = (
        "You are an assistant that extracts a shopping list from text.\n"
        "Return ONLY valid JSON that matches the provided JSON schema.\n"
        "Rules:\n"
        "- Use the allowed item ids, do not create new names.\n"
        "- Normalize item names into short lowercase ids when possible (e.g., coke, ramen).\n"
        "- If quantity is missing, assume qty=1.\n"
        "- If you are unsure, still produce best-effort items using the closest allowed id.\n"
        f"- timestamp_ms must be {created_ms}.\n"
        f"{allowed_hint}"
        "\n"
        f"Input text: {text}\n"
    )

    # Use chat completions with JSON output for compatibility across SDK versions.
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Extract a shopping list as JSON that matches the provided schema."},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )

    content = completion.choices[0].message.content
    data = json.loads(content or "{}")

    if not isinstance(data, dict) or "items" not in data:
        raise RuntimeError("Failed to parse items JSON from model output")
    items = data.get("items", [])
    cleaned = _normalize_items_to_allowed(items, allowed_list)

    if not cleaned:
        cleaned = _heuristic_items_from_text(text, allowed_list)

    # 보정: 수량이 1로 떨어졌을 때 텍스트 기반으로 보강
    if cleaned:
        for it in cleaned:
            kw = _KEYWORDS.get(it["name"], [])
            detected = _detect_quantity(text, kw)
            if detected > 0:
                it["qty"] = detected

    if not cleaned:
        raise RuntimeError("No valid items parsed from text")

    return {"items": cleaned, "timestamp_ms": created_ms}


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
