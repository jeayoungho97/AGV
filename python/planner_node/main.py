import argparse
import json
import math
import time
from pathlib import Path

import paho.mqtt.client as mqtt
from dotenv import load_dotenv


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_poi_map(poi_file: Path) -> dict:
    data = load_json(poi_file)
    poi_map = {}
    for p in data.get("poi", []):
        poi_map[p["id"]] = (float(p["x"]), float(p["y"]))
    if not poi_map:
        raise ValueError(f"No POIs found in {poi_file}")
    return poi_map


def dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def plan_path(items_payload: dict, poi_map: dict, frame: str) -> dict:
    items = items_payload.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("Invalid items payload: missing items array")

    waypoints = []
    total_cost = 0.0

    current = poi_map.get("entrance", (0.0, 0.0))
    waypoints.append({"x": current[0], "y": current[1]})

    for it in items:
        name = it.get("name")
        if not name:
            continue
        if name not in poi_map:
            raise KeyError(f"POI not found for item name: {name}")
        target = poi_map[name]
        total_cost += dist(current, target)
        waypoints.append({"x": target[0], "y": target[1]})
        current = target

    if "checkout" in poi_map:
        target = poi_map["checkout"]
        total_cost += dist(current, target)
        waypoints.append({"x": target[0], "y": target[1]})

    return {
        "frame": frame,
        "waypoints": waypoints,
        "total_cost": total_cost,
        "created_ms": int(time.time() * 1000),
    }


def main():
    parser = argparse.ArgumentParser(description="AGV Planner Node (Python MQTT bridge)")
    parser.add_argument("--mqtt", default="config/dev/mqtt.json", help="Path to mqtt.json")
    parser.add_argument("--planner", default="config/dev/planner.json", help="Path to planner.json")
    parser.add_argument("--once", action="store_true", help="Exit after processing one items message")
    parser.add_argument("--timeout_s", type=float, default=30.0, help="Exit after N seconds (0 disables)")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    load_dotenv(repo_root / ".env")
    mqtt_cfg = load_json(repo_root / args.mqtt)
    planner_cfg = load_json(repo_root / args.planner)

    broker = mqtt_cfg.get("broker", "localhost")
    port = int(mqtt_cfg.get("port", 1883))
    keepalive = int(mqtt_cfg.get("keepalive", 60))

    topics = mqtt_cfg.get("topics", {})
    items_topic = topics.get("items", "agv/ai/items")
    path_topic = topics.get("global_path", "agv/planner/global_path")

    poi_file = repo_root / planner_cfg.get("map_file", "data/poi/store_A_poi.json")
    frame = planner_cfg.get("frame", "map")
    poi_map = build_poi_map(poi_file)

    base_client_id = mqtt_cfg.get("client_id", "agv_dev")
    client = mqtt.Client(client_id=f"{base_client_id}_planner")
    username = mqtt_cfg.get("username")
    password = mqtt_cfg.get("password")
    if username:
        client.username_pw_set(username, password or "")

    state = {"handled": 0}

    def on_connect(cl, userdata, flags, rc):
        if rc != 0:
            raise RuntimeError(f"MQTT connect failed rc={rc}")
        print(f"[planner_node] connected {broker}:{port}", flush=True)
        cl.subscribe(items_topic, qos=1)
        print(f"[planner_node] subscribed {items_topic} -> publishing {path_topic}", flush=True)

    def on_message(cl, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            out = plan_path(payload, poi_map, frame)
            cl.publish(path_topic, json.dumps(out), qos=1, retain=False)
            print(f"[planner_node] published global_path ({path_topic})", flush=True)
            state["handled"] += 1
            if args.once and state["handled"] >= 1:
                cl.disconnect()
        except Exception as exc:
            print(f"[planner_node] failed to handle message: {exc}", flush=True)

    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(broker, port, keepalive)
    client.loop_start()
    start = time.time()
    try:
        while True:
            if args.once and state["handled"] >= 1:
                break
            if args.timeout_s > 0 and (time.time() - start) >= args.timeout_s:
                break
            time.sleep(0.05)
    finally:
        client.loop_stop()


if __name__ == "__main__":
    main()
