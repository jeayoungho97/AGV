import yaml
import time
import threading
from jetbot import Camera

from src.communication.mqtt_client import MQTTClient
from src.motion.motor_control import MotorControl
from src.motion.navigator import Navigator
from src.vision.aligner import Aligner
from src.vision.detector import ObjectDetector
from src.manipulation.grasper import Grasper
from src.utils.logger import get_logger

def load_config(path="config/settings.yaml"):
    with open(path, 'r') as f:
        return yaml.safe_load(f)

class RobotController:
    def __init__(self):
        self.config = load_config()
        self.logger = get_logger("Main")
        
        # Hardware & Modules
        self.camera = Camera.instance(width=300, height=300)
        self.motor = MotorControl(self.config)
        self.aligner = Aligner(self.motor, self.config)
        self.detector = ObjectDetector(self.config)
        self.grasper = Grasper(self.config)
        # pass grasper and detector into navigator so navigator can perform ordered grasps and alignment
        self.navigator = Navigator(self.motor, self.aligner, self.config, self.grasper, self.detector)
        
        # MQTT
        self.mqtt = MQTTClient(self.config, self.handle_command)
        
        self.is_running = True
        self.grasp_mode = False
        # Ordered list of object names to pick (from incoming payload 'order')
        self.order = []

    def handle_command(self, payload):
        """
        Payload examples:
        {
            "frame": "map",
            "order": ['lipstick', 'shadow'],
            "waypoints": [
                {"x": 1.0, "y": 1.0},
                {"x": 1.2, "y": 1.0}
            ],
            "total_cost": 12.3,
            "created_ms": 1710000000000
        }
        """
        # New format: accept `waypoints` array with {x,y} objects
        if payload is None:
            return


        # Save order list if present (list of object names)
        if 'order' in payload:
            try:
                order_list = payload.get('order', [])
                # ensure it's a list of strings
                self.order = [str(x) for x in order_list if x is not None]
                self.logger.info(f"Received order: {self.order}")
                # expose runtime order to navigator for selective grasp triggering
                try:
                    self.navigator.full_cfg['runtime_order'] = self.order
                except Exception:
                    pass
            except Exception as e:
                self.logger.error(f"Failed to parse order: {e}")

        if 'waypoints' in payload:
            waypoints = payload.get('waypoints', [])
            path = [[wp.get('x'), wp.get('y')] for wp in waypoints if ('x' in wp and 'y' in wp)]
            if path:
                threading.Thread(target=self.navigator.execute_path, args=(path, self.camera)).start()
                return

    def run(self):
        self.mqtt.start()
        self.grasper.set_move_pose()
        self.logger.info("System Ready.")

        try:
            while self.is_running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.cleanup()

    # on_waypoint_grasp handled inside Navigator now

    def cleanup(self):
        self.mqtt.stop()
        self.grasper.close()
        self.motor.stop()
        self.camera.stop()

if __name__ == "__main__":
    controller = RobotController()
    controller.run()