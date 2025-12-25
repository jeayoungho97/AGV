#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import math
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import paho.mqtt.client as mqtt


# ----------------------------
# Helpers
# ----------------------------
def load_json(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config not found: {p}")
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def setup_logger(level: str) -> logging.Logger:
    logger = logging.getLogger("planner_node")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("[%(name)s] %(levelname)s: %(message)s"))
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def resolve_map_file(planner_cfg_path: str, map_file_value: str) -> str:
    """
    planner.json 에 있는 map_file은 보통 프로젝트 기준 상대경로 (예: data/poi/store_A_grid_map.json)
    -> planner.json 파일이 있는 위치를 기준으로 상대경로를 해석해서 실제 경로를 만든다.
    """
    cfg_dir = Path(planner_cfg_path).resolve().parent
    p = Path(map_file_value)
    if p.is_absolute():
        return str(p)
    return str((cfg_dir / p).resolve())


# ----------------------------
# Config
# ----------------------------
@dataclass
class MqttCfg:
    broker: str
    port: int
    client_id: str
    username: str
    password: str
    keepalive: int
    topic_items: str
    topic_global_path: str


def parse_mqtt_cfg(d: Dict[str, Any]) -> MqttCfg:
    topics = d.get("topics", {}) or {}
    return MqttCfg(
        broker=str(d.get("broker", "127.0.0.1")),
        port=int(d.get("port", 1883)),
        client_id=str(d.get("client_id", "agv_dev")),
        username=str(d.get("username", "")),
        password=str(d.get("password", "")),
        keepalive=int(d.get("keepalive", 60)),
        topic_items=str(topics.get("items", "agv/ai/items")),
        topic_global_path=str(topics.get("global_path", "agv/planner/global_path")),
    )


@dataclass
class PlannerCfg:
    map_file: str
    frame: str
    use_diagonal: bool
    heuristic: str          # "euclidean" | "manhattan"
    obstacle_clearance_m: float
    turn_penalty: float
    output_topic: Optional[str]


def parse_planner_cfg(d: Dict[str, Any]) -> PlannerCfg:
    return PlannerCfg(
        map_file=str(d.get("map_file", "")),
        frame=str(d.get("frame", "map")),
        use_diagonal=bool(d.get("use_diagonal", True)),
        heuristic=str(d.get("heuristic", "euclidean")).lower(),
        obstacle_clearance_m=float(d.get("obstacle_clearance_m", 0.0)),
        turn_penalty=float(d.get("turn_penalty", 0.0)),
        output_topic=(str(d.get("output_topic")) if d.get("output_topic") else None),
    )


# ----------------------------
# Map / POI
# store_A_grid_map.json:
# {
#   "frame": "map",
#   "width": 14,
#   "height": 30,
#   "resolution": 0.05,
#   "origin": {"x":0.0,"y":0.0},
#   "obstacles": [{"x":..,"y":..}, ...],
#   "poi": [{"id":"ampoule","cell":{"x":4,"y":0}}, ...]
# }
# ----------------------------
@dataclass
class GridMap:
    frame: str
    width: int
    height: int
    resolution: float
    origin_x: float
    origin_y: float
    obstacles: List[Tuple[int, int]]
    poi: Dict[str, Tuple[int, int]]


def load_grid_map(map_path: str) -> GridMap:
    d = load_json(map_path)
    origin = d.get("origin", {}) or {}
    poi_dict: Dict[str, Tuple[int, int]] = {}
    for p in (d.get("poi", []) or []):
        pid = str(p.get("id"))
        cell = p.get("cell", {}) or {}
        poi_dict[pid] = (int(cell.get("x", 0)), int(cell.get("y", 0)))
    obstacles = [(int(o["x"]), int(o["y"])) for o in (d.get("obstacles", []) or [])]
    return GridMap(
        frame=str(d.get("frame", "map")),
        width=int(d.get("width", 0)),
        height=int(d.get("height", 0)),
        resolution=float(d.get("resolution", 1.0)),
        origin_x=float(origin.get("x", 0.0)),
        origin_y=float(origin.get("y", 0.0)),
        obstacles=obstacles,
        poi=poi_dict,
    )


def inflate_obstacles(
    obstacles: List[Tuple[int, int]],
    width: int,
    height: int,
    clearance_cells: int,
) -> set[Tuple[int, int]]:
    """
    clearance_cells 반경 만큼 장애물을 팽창(inflate)해서 안전거리 확보.
    """
    obs = set(obstacles)
    if clearance_cells <= 0:
        return obs

    inflated = set()
    for (ox, oy) in obs:
        for dx in range(-clearance_cells, clearance_cells + 1):
            for dy in range(-clearance_cells, clearance_cells + 1):
                nx, ny = ox + dx, oy + dy
                if 0 <= nx < width and 0 <= ny < height:
                    inflated.add((nx, ny))
    return inflated


# ----------------------------
# Planner (A* with optional diagonal + turn penalty)
# ----------------------------
class AStarPlanner:
    def __init__(self, gmap: GridMap, cfg: PlannerCfg, logger: logging.Logger):
        self.log = logger
        self.map = gmap
        self.cfg = cfg

        clearance_cells = int(math.ceil(cfg.obstacle_clearance_m / max(gmap.resolution, 1e-9)))
        self.obstacles = inflate_obstacles(gmap.obstacles, gmap.width, gmap.height, clearance_cells)

        self.poi = gmap.poi
        self.start = self.poi.get("entrance", (0, 0))
        self.end = self.poi.get("checkout", self.start)

        self.moves4 = [
            (1, 0, 1.0),
            (-1, 0, 1.0),
            (0, 1, 1.0),
            (0, -1, 1.0),
        ]
        self.moves8 = self.moves4 + [
            (1, 1, math.sqrt(2)),
            (1, -1, math.sqrt(2)),
            (-1, 1, math.sqrt(2)),
            (-1, -1, math.sqrt(2)),
        ]
        self.moves = self.moves8 if cfg.use_diagonal else self.moves4

        self.log.info(
            f"map loaded: {gmap.width}x{gmap.height}, res={gmap.resolution}, "
            f"obstacles(raw)={len(gmap.obstacles)}, obstacles(inflated)={len(self.obstacles)}, poi={len(self.poi)}"
        )
        self.log.info(f"start(entrance)={self.start}, end(checkout)={self.end}")
        self.log.debug(f"poi keys sample={list(sorted(self.poi.keys()))[:50]}")

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.map.width and 0 <= y < self.map.height

    def passable(self, x: int, y: int) -> bool:
        return (x, y) not in self.obstacles

    def heuristic(self, a: Tuple[int, int], b: Tuple[int, int]) -> float:
        dx = a[0] - b[0]
        dy = a[1] - b[1]
        if self.cfg.heuristic == "manhattan":
            return abs(dx) + abs(dy)
        return math.sqrt(dx * dx + dy * dy)

    def astar(self, s: Tuple[int, int], t: Tuple[int, int]) -> Optional[List[Tuple[int, int]]]:
        """
        turn_penalty를 반영하기 위해 state에 (x,y,dir_idx)를 포함.
        dir_idx = 이전 이동 방향 인덱스, 시작은 -1
        """
        if s == t:
            return [s]

        import heapq

        # priority queue: (f, g, x, y, prev_dir)
        pq: List[Tuple[float, float, int, int, int]] = []
        heapq.heappush(pq, (self.heuristic(s, t), 0.0, s[0], s[1], -1))

        # best_g[(x,y,dir)] = g
        best_g: Dict[Tuple[int, int, int], float] = {(s[0], s[1], -1): 0.0}

        # parent map: (x,y,dir) -> (px,py,pdir)
        parent: Dict[Tuple[int, int, int], Tuple[int, int, int]] = {}

        while pq:
            f, g, x, y, pdir = heapq.heappop(pq)

            # goal reached (any direction)
            if (x, y) == t:
                # reconstruct: pick current state key
                key = (x, y, pdir)
                path = [(x, y)]
                while key in parent:
                    key = parent[key]
                    path.append((key[0], key[1]))
                path.reverse()
                return path

            # expand
            for dir_idx, (dx, dy, step_cost) in enumerate(self.moves):
                nx, ny = x + dx, y + dy
                if not self.in_bounds(nx, ny):
                    continue
                if not self.passable(nx, ny):
                    continue

                turn_cost = 0.0
                if pdir != -1 and dir_idx != pdir:
                    turn_cost = float(self.cfg.turn_penalty)

                ng = g + step_cost + turn_cost
                nkey = (nx, ny, dir_idx)

                if ng < best_g.get(nkey, float("inf")):
                    best_g[nkey] = ng
                    parent[nkey] = (x, y, pdir)
                    nf = ng + self.heuristic((nx, ny), t)
                    heapq.heappush(pq, (nf, ng, nx, ny, dir_idx))

        return None

    def greedy_order(self, item_ids: List[str]) -> List[str]:
        """
        아주 단순한 nearest-neighbor order.
        (원하면 나중에 TSP/DP로 개선 가능)
        """
        # 정확히 매칭되는 id만 남김
        remaining = [i for i in item_ids if i in self.poi and i not in ("entrance", "checkout")]
        order: List[str] = []
        cur = self.start

        while remaining:
            remaining.sort(key=lambda pid: self.heuristic(cur, self.poi[pid]))
            nxt = remaining.pop(0)
            order.append(nxt)
            cur = self.poi[nxt]
        return order

    def cell_to_world(self, cell: Tuple[int, int]) -> Tuple[float, float]:
        """
        cell(x,y) -> world 좌표 (meter)
        origin + cell*resolution
        """
        x = self.map.origin_x + cell[0] * self.map.resolution
        y = self.map.origin_y + cell[1] * self.map.resolution
        return (x, y)

    def plan(self, item_ids: List[str]) -> Dict[str, Any]:
        order = self.greedy_order(item_ids)

        # visit points: start -> items -> end
        points: List[Tuple[int, int]] = [self.start] + [self.poi[i] for i in order] + [self.end]

        full: List[Tuple[int, int]] = []
        for a, b in zip(points, points[1:]):
            seg = self.astar(a, b)
            if seg is None:
                raise RuntimeError(f"No path from {a} to {b}")
            if full and seg and full[-1] == seg[0]:
                full.extend(seg[1:])
            else:
                full.extend(seg)

        # output: both cell + world
        waypoints_cell = [{"x": x, "y": y} for (x, y) in full]
        waypoints_world = []
        for c in full:
            wx, wy = self.cell_to_world(c)
            waypoints_world.append({"x": wx, "y": wy})

        return {
            "frame": self.cfg.frame or self.map.frame,
            "resolution": self.map.resolution,
            "origin": {"x": self.map.origin_x, "y": self.map.origin_y},
            "start_cell": {"x": self.start[0], "y": self.start[1]},
            "end_cell": {"x": self.end[0], "y": self.end[1]},
            "items": item_ids,
            "order": order,
            "waypoints_cell": waypoints_cell,
            "waypoints": waypoints_world,  # meter coordinates
        }


def extract_items(payload: Dict[str, Any]) -> List[str]:
    """
    지원 형태:
    1) {"items":[{"name":"ampoule"},{"name":"vitamin"}]}
    2) {"items":["ampoule","vitamin"]}
    """
    items = payload.get("items", [])
    out: List[str] = []
    if isinstance(items, list):
        for it in items:
            if isinstance(it, str):
                out.append(it.strip())
            elif isinstance(it, dict):
                name = it.get("name", it.get("id"))
                if isinstance(name, str):
                    out.append(name.strip())
    # 빈 문자열 제거
    return [x for x in out if x]


# ----------------------------
# MQTT Node
# ----------------------------
class PlannerNode:
    def __init__(self, mqtt_cfg: MqttCfg, planner: AStarPlanner, output_topic: str, logger: logging.Logger):
        self.cfg = mqtt_cfg
        self.planner = planner
        self.output_topic = output_topic
        self.log = logger

        # MQTT v3.1.1
        self.client = mqtt.Client(client_id=f"{self.cfg.client_id}_planner", protocol=mqtt.MQTTv311)

        if self.cfg.username:
            self.client.username_pw_set(self.cfg.username, self.cfg.password)

        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect

        self._should_exit = False

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.log.info(f"connected {self.cfg.broker}:{self.cfg.port}")
            client.subscribe(self.cfg.topic_items)
            self.log.info(f"subscribed {self.cfg.topic_items} -> publishing {self.output_topic}")
        else:
            self.log.error(f"connect failed rc={rc}")

    def on_disconnect(self, client, userdata, rc):
        self.log.warning(f"disconnected rc={rc}")

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8", errors="replace"))
        except Exception as e:
            self.log.error(f"invalid json on {msg.topic}: {e}")
            return

        item_ids = extract_items(payload)
        self.log.info(f"rx {msg.topic}: items={item_ids}")

        try:
            result = self.planner.plan(item_ids)
        except Exception as e:
            self.log.error(f"plan failed: {e}")
            err = {"error": str(e), "items": item_ids}
            client.publish(self.output_topic, json.dumps(err), qos=0, retain=False)
            return

        client.publish(self.output_topic, json.dumps(result), qos=0, retain=False)
        self.log.info(
            f"published {self.output_topic} "
            f"order={result.get('order')} "
            f"waypoints_cell={len(result.get('waypoints_cell', []))}"
        )

    def run(self):
        def handle_sig(_sig, _frame):
            self._should_exit = True

        signal.signal(signal.SIGINT, handle_sig)
        signal.signal(signal.SIGTERM, handle_sig)

        self.client.connect(self.cfg.broker, self.cfg.port, keepalive=self.cfg.keepalive)
        self.client.loop_start()
        try:
            while not self._should_exit:
                time.sleep(0.2)
        finally:
            self.client.loop_stop()
            self.client.disconnect()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mqtt", required=True, help="path to mqtt.json")
    ap.add_argument("--planner", required=True, help="path to planner.json (contains map_file)")
    ap.add_argument("--log", default="info", choices=["debug", "info", "warning", "error"], help="log level")
    args = ap.parse_args()

    logger = setup_logger(args.log)

    mqtt_cfg = parse_mqtt_cfg(load_json(args.mqtt))
    planner_cfg_raw = load_json(args.planner)
    planner_cfg = parse_planner_cfg(planner_cfg_raw)

    if not planner_cfg.map_file:
        raise ValueError("planner.json must contain 'map_file'")

    map_path = resolve_map_file(args.planner, planner_cfg.map_file)
    gmap = load_grid_map(map_path)

    planner = AStarPlanner(gmap, planner_cfg, logger)

    # output topic: planner.json output_topic 우선, 없으면 mqtt.json topics.global_path
    out_topic = planner_cfg.output_topic or mqtt_cfg.topic_global_path

    node = PlannerNode(mqtt_cfg, planner, out_topic, logger)
    node.run()


if __name__ == "__main__":
    main()

