import argparse
import json
import time
from pathlib import Path

try:
    import paho.mqtt.client as mqtt
except ImportError:  # pragma: no cover
    mqtt = None

try:  # allow both `python main.py` and `python -m python.ai_node.main`
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

try:  # when run as a script from this directory
    from item_parser import parse_items_from_text, validate_items_payload
    from stt import transcribe_audio_file
except ImportError:  # when run as a module
    from .item_parser import parse_items_from_text, validate_items_payload
    from .stt import transcribe_audio_file


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    return load_json(config_path)


def build_items_payload(sample_path: Path) -> dict:
    if sample_path.exists():
        return load_json(sample_path)
    # fallback payload
    return {
        "items": [
            {"name": "coke", "qty": 1},
            {"name": "ramen", "qty": 2},
        ],
        "timestamp_ms": int(time.time() * 1000),
    }


def connect_client(cfg: dict):
    if mqtt is None:
        raise RuntimeError("paho-mqtt not installed. Install via `pip install -r requirements.txt`.")
    base_client_id = cfg.get("client_id", "agv_dev")
    client = mqtt.Client(client_id=f"{base_client_id}_ai")
    username = cfg.get("username")
    password = cfg.get("password")
    if username:
        client.username_pw_set(username, password or "")
    client.connect(cfg.get("broker", "localhost"), cfg.get("port", 1883), cfg.get("keepalive", 60))
    return client


def publish_items():
    parser = argparse.ArgumentParser(description="AI Node (items publisher)")
    parser.add_argument("--text", help="Utterance text to parse into items JSON")
    parser.add_argument("--audio", help="Audio file path to transcribe then parse into items JSON")
    parser.add_argument("--sample", action="store_true", help="Publish sample items from data/samples/items_example.json")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    if load_dotenv is not None:
        load_dotenv(repo_root / ".env")
    config_path = repo_root / "config" / "dev" / "mqtt.json"
    cfg = load_config(config_path)
    topic = cfg.get("topics", {}).get("items", "agv/ai/items")

    if args.sample or (not args.text and not args.audio):
        payload = build_items_payload(repo_root / "data" / "samples" / "items_example.json")
        payload["timestamp_ms"] = int(time.time() * 1000)
    else:
        if args.audio:
            text = transcribe_audio_file(Path(args.audio))
        else:
            text = args.text or ""
        payload = parse_items_from_text(text)

    validate_items_payload(payload)

    print(f"[ai_node] publishing to {topic}: {payload}")

    client = connect_client(cfg)
    client.publish(topic, json.dumps(payload))
    client.loop(timeout=2.0)
    client.disconnect()


def main():
    try:
        publish_items()
    except Exception as exc:  # pragma: no cover
        print(f"[ai_node] failed: {exc}")
        raise


if __name__ == "__main__":
    main()
