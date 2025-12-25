# AI Node (Python)

Publisher that reads `config/dev/mqtt.json` and publishes `items` to MQTT.

Modes:
- Sample mode: publish `data/samples/items_example.json`
- AI parse mode: (optional) speech-to-text from an audio file + LLM parsing into `items` JSON

## Setup
```bash
cd python/ai_node
pip install -r requirements.txt
```

## Run
```bash
python main.py
```
The script logs the payload and exits after one publish. Extend it to pull real speech/AI results and loop as needed.

## AI Parse (optional)
Create `.env` from `.env.example` (recommended) or set `OPENAI_API_KEY` in your shell, then use one of:
```bash
python main.py --text "콜라 1개 라면 2개"
python main.py --audio /path/to/recording.wav
```
