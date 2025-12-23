from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")

MQTT_CFG_PATH = REPO_ROOT / os.getenv("AGV_MQTT_CONFIG", "config/dev/mqtt.json")
PLANNER_CFG_PATH = REPO_ROOT / os.getenv("AGV_PLANNER_CONFIG", "config/dev/planner.json")
MAP_FILE_OVERRIDE = os.getenv("AGV_MAP_FILE")

# Make `python/` importable so we can reuse `ai_node` modules.
PYTHON_ROOT = REPO_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

try:
    from ai_node.item_parser import parse_items_from_text, validate_items_payload  # type: ignore
except Exception as e:  # pragma: no cover
    raise RuntimeError(f"Failed to import ai_node modules: {e}") from e

from .mqtt_pub import publish_items_payload
from .telemetry import AgvTelemetry


class ParseRequest(BaseModel):
    text: str = Field(..., min_length=1)


class PublishRequest(BaseModel):
    text: Optional[str] = None
    items: Optional[Dict[str, Any]] = None


class CommandRequest(BaseModel):
    action: Literal["go", "stop"]
    source: Optional[str] = "ui"
    utterance: Optional[str] = None


app = FastAPI(title="AGV Voice Web", version="0.1.0")

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

telemetry: Optional[AgvTelemetry] = None
telemetry_error: Optional[str] = None


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_map_path() -> Path:
    if MAP_FILE_OVERRIDE:
        path = Path(MAP_FILE_OVERRIDE)
        if not path.is_absolute():
            path = REPO_ROOT / path
        return path

    try:
        planner_cfg = _load_json(PLANNER_CFG_PATH)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read planner config: {exc}")

    rel = planner_cfg.get("map_file", "data/poi/store_A_grid_map.json")
    path = Path(rel)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def _load_poi_ids() -> list[str]:
    path = _resolve_map_path()
    try:
        data = _load_json(path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load map: {exc}")
    poi_list = data.get("poi", [])
    ids = []
    for p in poi_list:
        pid = p.get("id") if isinstance(p, dict) else None
        if pid:
            ids.append(str(pid))
    return ids


@app.on_event("startup")
def _startup():
    global telemetry, telemetry_error
    try:
        telemetry = AgvTelemetry(MQTT_CFG_PATH)
        telemetry.start()
    except Exception as exc:  # pragma: no cover - startup errors are reported via API
        telemetry_error = str(exc)


@app.on_event("shutdown")
def _shutdown():
    if telemetry:
        telemetry.stop()


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
    try:
        items_payload = parse_items_from_text(req.text, allowed_names=_load_poi_ids())
        validate_items_payload(items_payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Parse failed: {exc}")
    return items_payload


@app.post("/api/publish")
def api_publish(req: PublishRequest):
    if req.items is None and not (req.text and req.text.strip()):
        raise HTTPException(status_code=400, detail="Provide either `items` or `text`.")

    try:
        if req.items is not None:
            payload = req.items
        else:
            if not os.getenv("OPENAI_API_KEY", "").strip():
                raise HTTPException(status_code=400, detail="OPENAI_API_KEY not set (create .env)")
            payload = parse_items_from_text(req.text or "", allowed_names=_load_poi_ids())

        validate_items_payload(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Publish failed: {exc}")

    publish_items_payload(payload, repo_root=REPO_ROOT)
    return {"published": True, "items": payload}


@app.get("/api/config")
def api_config():
    try:
        cfg = _load_json(MQTT_CFG_PATH)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read mqtt config: {e}")
    return {
        "broker": cfg.get("broker", "localhost"),
        "port": cfg.get("port", 1883),
        "items_topic": cfg.get("topics", {}).get("items", "agv/ai/items"),
        "path_topic": cfg.get("topics", {}).get("global_path", "agv/planner/global_path"),
        "pose_topic": cfg.get("topics", {}).get("pose", "agv/state/pose"),
        "command_topic": cfg.get("topics", {}).get("command", "agv/web/command"),
    }


@app.get("/api/map")
def api_map():
    path = _resolve_map_path()
    try:
        data = _load_json(path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load map: {exc}")
    return data


@app.get("/api/state")
def api_state():
    if telemetry:
        return telemetry.snapshot()
    return {"connected": False, "last_error": telemetry_error or "Telemetry not initialized"}


@app.post("/api/command")
def api_command(req: CommandRequest):
    if telemetry is None:
        raise HTTPException(status_code=500, detail="Telemetry not initialized")
    try:
        telemetry.publish_command(req.action, source=req.source or "ui", utterance=req.utterance or "")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to publish command: {exc}")
    return {"ok": True, "action": req.action, "topic": telemetry.cmd_topic}


@app.post("/api/clear_path")
def api_clear_path():
    if telemetry is None:
        raise HTTPException(status_code=500, detail="Telemetry not initialized")
    telemetry.clear_path()
    return {"ok": True}
