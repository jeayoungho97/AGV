from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")

# Make `python/` importable so we can reuse `ai_node` modules.
PYTHON_ROOT = REPO_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

try:
    from ai_node.item_parser import parse_items_from_text, validate_items_payload  # type: ignore
except Exception as e:  # pragma: no cover
    raise RuntimeError(f"Failed to import ai_node modules: {e}") from e

from .mqtt_pub import publish_items_payload


class ParseRequest(BaseModel):
    text: str = Field(..., min_length=1)


class PublishRequest(BaseModel):
    text: Optional[str] = None
    items: Optional[Dict[str, Any]] = None


app = FastAPI(title="AGV Voice Web", version="0.1.0")

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
def index():
    return FileResponse(static_dir / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/parse")
def api_parse(req: ParseRequest):
    if not os.getenv("OPENAI_API_KEY", "").strip():
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY not set (create .env)")
    items_payload = parse_items_from_text(req.text)
    validate_items_payload(items_payload)
    return items_payload


@app.post("/api/publish")
def api_publish(req: PublishRequest):
    if req.items is None and not (req.text and req.text.strip()):
        raise HTTPException(status_code=400, detail="Provide either `items` or `text`.")

    if req.items is not None:
        payload = req.items
    else:
        if not os.getenv("OPENAI_API_KEY", "").strip():
            raise HTTPException(status_code=400, detail="OPENAI_API_KEY not set (create .env)")
        payload = parse_items_from_text(req.text or "")

    validate_items_payload(payload)
    publish_items_payload(payload, repo_root=REPO_ROOT)
    return {"published": True, "items": payload}


@app.get("/api/config")
def api_config():
    mqtt_cfg_path = REPO_ROOT / "config" / "dev" / "mqtt.json"
    try:
        cfg = json.loads(mqtt_cfg_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read mqtt config: {e}")
    return {
        "items_topic": cfg.get("topics", {}).get("items", "agv/ai/items"),
        "path_topic": cfg.get("topics", {}).get("global_path", "agv/planner/global_path"),
    }

