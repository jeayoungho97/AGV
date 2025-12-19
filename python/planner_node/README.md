# Planner Node (Python MQTT bridge)

This is a temporary MQTT-capable planner node implemented in Python to validate the end-to-end flow:

`ai_node` (items) -> `planner_node` (global_path)

It uses the same config files as the rest of the repo:
- `config/dev/mqtt.json`
- `config/dev/planner.json`

## Setup
```bash
cd python/planner_node
pip install -r requirements.txt
```

## Run
In one terminal (broker must be running):
```bash
python main.py
```

In another terminal:
```bash
python ../ai_node/main.py
```

(Optional) Watch outputs:
```bash
mosquitto_sub -t agv/planner/global_path
```

## .env
This node also loads `.env` from the repo root (if present) so you can share settings consistently.
