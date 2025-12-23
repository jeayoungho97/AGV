import argparse
import heapq
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

Coordinate = Tuple[int, int]


@dataclass(frozen=True)
class GridPoi:
    id: str
    cell: Coordinate
    world: Tuple[float, float]


@dataclass
class GridMap:
    width: int
    height: int
    resolution: float
    origin: Tuple[float, float]
    frame: str
    obstacles: Set[Coordinate]
    poi: Dict[str, GridPoi]


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


def load_grid_map(poi_file: Path) -> Optional[GridMap]:
    """Load map with width/height/obstacles. Returns None if file is POI-only."""
    data = load_json(poi_file)
    required = {"width", "height", "resolution"}
    if not required.issubset(data):
        return None

    width = int(data["width"])
    height = int(data["height"])
    resolution = float(data["resolution"])
    origin_data = data.get("origin", {}) or {}
    origin = (float(origin_data.get("x", 0.0)), float(origin_data.get("y", 0.0)))
    frame = data.get("frame", "map")

    obstacles: Set[Coordinate] = set()
    for obs in data.get("obstacles", []):
        cx = int(obs.get("x"))
        cy = int(obs.get("y"))
        if not (0 <= cx < width and 0 <= cy < height):
            raise ValueError(f"Obstacle outside map bounds: {(cx, cy)}")
        obstacles.add((cx, cy))

    poi: Dict[str, GridPoi] = {}
    for p in data.get("poi", []):
        pid = p.get("id")
        if not pid:
            continue

        if "cell" in p and isinstance(p["cell"], dict):
            cell = (int(p["cell"]["x"]), int(p["cell"]["y"]))
        elif "cell_x" in p and "cell_y" in p:
            cell = (int(p["cell_x"]), int(p["cell_y"]))
        elif "x" in p and "y" in p:
            cell = (
                int(round((float(p["x"]) - origin[0]) / resolution)),
                int(round((float(p["y"]) - origin[1]) / resolution)),
            )
        else:
            raise ValueError(f"POI missing cell or coordinates: {p}")

        if not (0 <= cell[0] < width and 0 <= cell[1] < height):
            raise ValueError(f"POI outside map bounds: {pid} -> {cell}")

        world = (
            origin[0] + cell[0] * resolution,
            origin[1] + cell[1] * resolution,
        )
        poi[pid] = GridPoi(id=pid, cell=cell, world=world)

    if not poi:
        raise ValueError(f"No POIs found in {poi_file}")

    return GridMap(
        width=width,
        height=height,
        resolution=resolution,
        origin=origin,
        frame=frame,
        obstacles=obstacles,
        poi=poi,
    )


def inflate_obstacles(grid: GridMap, clearance_m: float) -> None:
    """Inflate obstacles by a clearance radius in meters."""
    if clearance_m <= 0:
        return
    cells = int(math.ceil(clearance_m / grid.resolution))
    if cells <= 0:
        return
    inflated: Set[Coordinate] = set(grid.obstacles)
    for ox, oy in grid.obstacles:
        for dx in range(-cells, cells + 1):
            for dy in range(-cells, cells + 1):
                nx, ny = ox + dx, oy + dy
                if 0 <= nx < grid.width and 0 <= ny < grid.height:
                    inflated.add((nx, ny))
    grid.obstacles = inflated


def dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _neighbors(cell: Coordinate, grid: GridMap, use_diagonal: bool) -> Iterable[Coordinate]:
    steps = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    if use_diagonal:
        steps += [(-1, -1), (-1, 1), (1, -1), (1, 1)]

    for dx, dy in steps:
        nx, ny = cell[0] + dx, cell[1] + dy
        if 0 <= nx < grid.width and 0 <= ny < grid.height and (nx, ny) not in grid.obstacles:
            yield (nx, ny)


def _heuristic(a: Coordinate, b: Coordinate, name: str) -> float:
    dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
    if name == "manhattan":
        return dx + dy
    if name == "chebyshev":
        return max(dx, dy)
    return math.hypot(dx, dy)


def a_star(start: Coordinate, goal: Coordinate, grid: GridMap, use_diagonal: bool, heuristic: str, turn_penalty: float) -> List[Coordinate]:
    if start == goal:
        return [start]

    open_set: List[Tuple[float, Coordinate]] = []
    heapq.heappush(open_set, (0.0, start))
    came_from: Dict[Coordinate, Coordinate] = {}
    g_score: Dict[Coordinate, float] = {start: 0.0}
    dir_from: Dict[Coordinate, Coordinate] = {}

    while open_set:
        _, current = heapq.heappop(open_set)
        if current == goal:
            # Reconstruct path.
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            path.reverse()
            return path

        for nb in _neighbors(current, grid, use_diagonal):
            step_cost = math.hypot(nb[0] - current[0], nb[1] - current[1])
            penalty = 0.0
            if current in came_from:
                prev = came_from[current]
                prev_dir = (current[0] - prev[0], current[1] - prev[1])
                new_dir = (nb[0] - current[0], nb[1] - current[1])
                if prev_dir != new_dir:
                    penalty = max(0.0, float(turn_penalty))
            tentative = g_score[current] + step_cost + penalty
            if tentative >= g_score.get(nb, math.inf):
                continue
            came_from[nb] = current
            dir_from[nb] = (nb[0] - current[0], nb[1] - current[1])
            g_score[nb] = tentative
            f_score = tentative + _heuristic(nb, goal, heuristic)
            heapq.heappush(open_set, (f_score, nb))

    raise RuntimeError(f"No path found from {start} to {goal}")


def _grid_cells_to_world(path: List[Coordinate], grid: GridMap) -> List[Tuple[float, float]]:
    return [(grid.origin[0] + cx * grid.resolution, grid.origin[1] + cy * grid.resolution) for cx, cy in path]


def plan_path_grid(items_payload: dict, grid: GridMap, use_diagonal: bool, heuristic: str, turn_penalty: float) -> dict:
    items = items_payload.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("Invalid items payload: missing items array")

    route: List[str] = []
    if "entrance" in grid.poi:
        route.append("entrance")

    for it in items:
        name = it.get("name")
        if not name:
            raise ValueError("Item missing name")
        if name not in grid.poi:
            raise KeyError(f"POI not found for item name: {name}")
        route.append(name)

    if "checkout" in grid.poi:
        route.append("checkout")

    if len(route) < 2:
        raise ValueError("Route must contain at least a start and a goal")

    cell_path: List[Coordinate] = []
    for idx in range(len(route) - 1):
        start = grid.poi[route[idx]].cell
        goal = grid.poi[route[idx + 1]].cell
        segment = a_star(start, goal, grid, use_diagonal, heuristic, turn_penalty)
        if idx > 0 and segment and cell_path and segment[0] == cell_path[-1]:
            segment = segment[1:]
        cell_path.extend(segment)

    world_points = _grid_cells_to_world(cell_path, grid)
    waypoints = [{"x": round(x, 2), "y": round(y, 2)} for x, y in world_points]
    total_cost = sum(dist(world_points[i - 1], world_points[i]) for i in range(1, len(world_points)))

    return {
        "frame": grid.frame,
        "waypoints": waypoints,
        "total_cost": total_cost,
        "created_ms": int(time.time() * 1000),
    }


def plan_path_direct(items_payload: dict, poi_map: dict, frame: str) -> dict:
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
    parser.add_argument("--timeout_s", type=float, default=0.0, help="Exit after N seconds (0 disables)")
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
    grid_map = load_grid_map(poi_file)
    frame = planner_cfg.get("frame", "map")
    poi_map = None
    if grid_map:
        clearance_m = float(planner_cfg.get("obstacle_clearance_m", 0.0))
        inflate_obstacles(grid_map, clearance_m)
        frame = grid_map.frame or frame
    else:
        poi_map = build_poi_map(poi_file)
    use_diagonal = bool(planner_cfg.get("use_diagonal", True))
    heuristic = planner_cfg.get("heuristic", "euclidean")
    turn_penalty = float(planner_cfg.get("turn_penalty", 0.0))

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
            if grid_map:
                out = plan_path_grid(payload, grid_map, use_diagonal=use_diagonal, heuristic=heuristic, turn_penalty=turn_penalty)
            else:
                out = plan_path_direct(payload, poi_map, frame)
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
