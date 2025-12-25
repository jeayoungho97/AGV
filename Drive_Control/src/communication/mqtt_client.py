import paho.mqtt.client as mqtt
import json
from ..utils.logger import get_logger

class MQTTClient:
    def __init__(self, config, on_message_callback):
        self.logger = get_logger("MQTT")
        self.broker = config['mqtt']['broker']
        self.port = config['mqtt']['port']
        self.topic = config['mqtt']['topic_sub']
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.callback = on_message_callback

    def on_connect(self, client, userdata, flags, rc):
        self.logger.info(f"Connected with result code {rc}")
        client.subscribe(self.topic)

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            self.logger.info(f"Received message: {payload}")
            self.callback(payload)
        except Exception as e:
            self.logger.error(f"Failed to parse message: {e}")

    def start(self):
        self.client.connect(self.broker, self.port, 60)
        self.client.loop_start()

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()
