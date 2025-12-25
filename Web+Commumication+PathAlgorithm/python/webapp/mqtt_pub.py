from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

import paho.mqtt.client as mqtt


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def publish_items_payload(payload: Dict[str, Any], *, repo_root: Optional[Path] = None) -> None:
    root = repo_root or Path(__file__).resolve().parents[2]
    cfg = _load_json(root / "config" / "dev" / "mqtt.json")
    topic = cfg.get("topics", {}).get("items", "agv/ai/items")

    base_client_id = cfg.get("client_id", "agv_dev")
    client = mqtt.Client(client_id=f"{base_client_id}_web_{int(time.time())}")

    username = (cfg.get("username") or "").strip()
    password = (cfg.get("password") or "").strip()
    if username:
        client.username_pw_set(username, password)

    client.connect(cfg.get("broker", "localhost"), int(cfg.get("port", 1883)), int(cfg.get("keepalive", 60)))
    client.publish(topic, json.dumps(payload), qos=1, retain=False)
    client.loop(timeout=2.0)
    client.disconnect()

