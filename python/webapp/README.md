# Web Voice UI

Phone-friendly web UI with three roles:
- show the AGV on the store map (MQTT pose topic)
- send `go` / `stop` via MQTT (buttons or voice keywords)
- say "콜라 2개 라면 1개 찾아줘" → AI가 items JSON으로 파싱 → planner가 `global_path`를 발행 → 지도에 예상 경로를 그립니다.

## Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r python/webapp/requirements.txt
```

Create `.env` at repo root:
```bash
cp .env.example .env
# set OPENAI_API_KEY=...
```

## Run (local)
Start your MQTT broker (mosquitto) on the same machine, then:
```bash
source .venv/bin/activate
uvicorn python.webapp.app:app --host 0.0.0.0 --port 8000
```

Open from your phone (same Wi‑Fi):
- `http://<YOUR_PC_LAN_IP>:8000`

## Notes
- SpeechRecognition support depends on browser/OS. If unsupported, type text and publish.
- iOS Safari often requires HTTPS for mic access; for iOS, use a tunnel (ngrok/cloudflared) or run behind HTTPS.

## Simple deployment options
If you need HTTPS for iPhone mic access:
- **cloudflared tunnel** (quick): run server locally, expose HTTPS URL to your phone.
- **ngrok** (quick): same idea.

If you want to host in the cloud:
- Host this FastAPI app on Render/Fly/Railway, but then it must reach your MQTT broker (public broker or VPN).

## MQTT topics
- Pose/telemetry (subscribe): `agv/state/pose`  
  JSON example:
  ```json
  {"x": 1.2, "y": 3.4, "theta": 0.1, "status": "moving", "timestamp_ms": 1720000000000}
  ```
- Go/Stop (publish): `agv/web/command`  
  ```json
  {"action": "go", "source": "voice|button", "utterance": "출발", "requested_ms": 1720000000000}
  ```
- Planner input (publish): `agv/ai/items`
- Planner output (subscribe): `agv/planner/global_path`

All topics/broker settings are read from `config/dev/mqtt.json` by default. Override with env vars:
- `AGV_MQTT_CONFIG` — path to mqtt.json (absolute or repo-relative)
- `AGV_MAP_FILE` — override map file (otherwise planner config's `map_file` is used)
