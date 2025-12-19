# AI Node (Python)

Simple publisher that reads `config/dev/mqtt.json`, builds an `items` payload from `data/samples/items_example.json` (or a fallback), and publishes to the `items` topic over MQTT using `paho-mqtt`.

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
