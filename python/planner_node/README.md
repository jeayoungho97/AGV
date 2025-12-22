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

## Map format (with obstacles)
`config/dev/planner.json` points to `data/poi/store_A_grid_map.json`, which includes the full grid map for obstacle-aware A*:
```json
{
  "frame": "map",
  "width": 12,
  "height": 8,
  "resolution": 0.5,
  "origin": { "x": 0.0, "y": 0.0 },
  "obstacles": [{ "x": 4, "y": 1 }],
  "poi": [
    { "id": "entrance", "cell": { "x": 1, "y": 0 } },
    { "id": "coke", "cell": { "x": 9, "y": 2 } },
    { "id": "ramen", "cell": { "x": 10, "y": 5 } },
    { "id": "checkout", "cell": { "x": 2, "y": 7 } }
  ]
}
```
- `width`/`height`: grid cells (integer)
- `resolution`: meters per cell (waypoints are reported in meters)
- `origin`: world coords for grid (0,0)
- `obstacles`: blocked cells to avoid
- `poi`: items/entrance/checkout in cell coordinates; world coords are auto-derived

If you supply a legacy POI-only file (no `width`/`height`/`resolution`), the planner falls back to straight-line paths without obstacle avoidance.

### Clearance
`obstacle_clearance_m` in `config/dev/planner.json` inflates obstacles by that radius (meters) to keep the AGV body offset. Example: `0.1` (10cm) with 5cm resolution expands each obstacle by 2 cells in all directions.

## Docker Compose (MQTT + Planner)
Cross-platform dev (Mac/Windows) with a shared setup:
```bash
docker compose up --build
```
- MQTT broker: `eclipse-mosquitto` with config at `docker/mosquitto.conf`
- Planner: builds from `docker/Dockerfile.planner`, mounts repo into `/app`, uses `config/dev/mqtt.docker.json` (broker host `mqtt`)

Send `items` to `agv/ai/items` (same as bare-metal), and the planner publishes `agv/planner/global_path`. Stop with `Ctrl+C` or `docker compose down`.
