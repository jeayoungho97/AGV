# Web Voice UI

Phone-friendly web UI that uses the browser's speech recognition (Web Speech API) to get text, then:
- calls OpenAI to parse text into `items` JSON (optional), and
- publishes `items` to MQTT (`agv/ai/items`) so the planner node can generate `global_path`.

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

