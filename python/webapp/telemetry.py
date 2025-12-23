from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

import paho.mqtt.client as mqtt


class AgvTelemetry:
    """Keep the latest AGV pose/status from MQTT and publish go/stop commands."""

    def __init__(self, cfg_path: Path):
        self.cfg_path = cfg_path
        self.cfg = self._load_cfg(cfg_path)
        topics = self.cfg.get("topics", {})
        self.pose_topic = topics.get("pose", "agv/state/pose")
        self.cmd_topic = topics.get("command", "agv/web/command")
        self.path_topic = topics.get("global_path", "agv/planner/global_path")

        base_client_id = self.cfg.get("client_id", "agv_dev")
        self.client = mqtt.Client(client_id=f"{base_client_id}_web_ui")

        username = (self.cfg.get("username") or "").strip()
        password = (self.cfg.get("password") or "").strip()
        if username:
            self.client.username_pw_set(username, password)

        self.broker = self.cfg.get("broker", "localhost")
        self.port = int(self.cfg.get("port", 1883))
        self.keepalive = int(self.cfg.get("keepalive", 60))

        self._lock = threading.Lock()
        self._connected = False
        self._last_error: Optional[str] = None
        self._state: Dict[str, Any] = {
            "pose": None,
            "status": None,
            "velocity": None,
            "last_seen_ms": None,
            "frame": None,
            "path": None,
            "path_last_ms": None,
        }

    def _load_cfg(self, path: Path) -> Dict[str, Any]:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - startup failure is fatal for telemetry only
            raise RuntimeError(f"Failed to load MQTT config at {path}: {exc}") from exc

    def start(self) -> None:
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        try:
            self.client.connect(self.broker, self.port, self.keepalive)
        except Exception as exc:
            self._last_error = f"MQTT connect failed: {exc}"
            return
        self.client.loop_start()

    def stop(self) -> None:
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            pass

    def _on_connect(self, client, userdata, flags, rc):
        if rc != 0:
            self._last_error = f"MQTT connect returned {rc}"
            return
        self._connected = True
        client.subscribe(self.pose_topic, qos=1)
        client.subscribe(self.path_topic, qos=1)

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            return

        topic = getattr(msg, "topic", "")
        if topic == self.pose_topic:
            pose = payload.get("pose") or {
                "x": payload.get("x"),
                "y": payload.get("y"),
                "theta": payload.get("theta"),
            }
            status = payload.get("status")
            velocity = payload.get("velocity")
            frame = payload.get("frame")
            ts = payload.get("timestamp_ms") or payload.get("created_ms") or int(time.time() * 1000)
            with self._lock:
                self._state.update(
                    {
                        "pose": pose,
                        "status": status,
                        "velocity": velocity,
                        "last_seen_ms": ts,
                        "frame": frame,
                    }
                )
        elif topic == self.path_topic:
            ts = payload.get("created_ms") or payload.get("timestamp_ms") or int(time.time() * 1000)
            with self._lock:
                self._state.update(
                    {
                        "path": payload,
                        "path_last_ms": ts,
                    }
                )

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            state = dict(self._state)
        state["connected"] = self._connected
        state["last_error"] = self._last_error
        state["pose_topic"] = self.pose_topic
        state["command_topic"] = self.cmd_topic
        state["path_topic"] = self.path_topic
        return state

    def clear_path(self) -> None:
        with self._lock:
            self._state["path"] = None
            self._state["path_last_ms"] = None

    def publish_command(self, action: str, source: str = "ui", utterance: str = "") -> None:
        payload = {
            "action": action,
            "source": source,
            "utterance": utterance,
            "requested_ms": int(time.time() * 1000),
        }

        if self._connected:
            try:
                self.client.publish(self.cmd_topic, json.dumps(payload), qos=1, retain=False)
                return
            except Exception:
                # Fall back to one-off client below.
                pass

        temp_client = mqtt.Client(client_id=f"{self.cfg.get('client_id', 'agv_dev')}_web_cmd")
        username = (self.cfg.get("username") or "").strip()
        password = (self.cfg.get("password") or "").strip()
        if username:
            temp_client.username_pw_set(username, password)

        temp_client.connect(self.broker, self.port, self.keepalive)
        temp_client.publish(self.cmd_topic, json.dumps(payload), qos=1, retain=False)
        temp_client.loop(timeout=1.5)
        temp_client.disconnect()
