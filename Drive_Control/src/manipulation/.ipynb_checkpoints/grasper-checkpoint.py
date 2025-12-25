import time
import numpy as np
import threading
import serial
from SCSCtrl import TTLServo
from ..utils.logger import get_logger

class Grasper:
    def __init__(self, config):
        self.logger = get_logger("Grasper")
        self.cfg = config['manipulation']
        self.grasp_table = self.cfg['grasp_table']
        
        # Distance Sensor
        self.serial_port = self.cfg['serial_port']
        self.baud_rate = self.cfg['baud_rate']
        self.current_distance = 999.0
        self.stop_sensor = False
        self._start_sensor_thread()

    def _start_sensor_thread(self):
        try:
            self.ser = serial.Serial(self.serial_port, self.baud_rate, timeout=1)
            self.t = threading.Thread(target=self._update_distance)
            self.t.start()
        except Exception as e:
            self.logger.error(f"Serial init failed: {e}")

    def _update_distance(self):
        while not self.stop_sensor:
            if self.ser.in_waiting > 0:
                try:
                    line = self.ser.readline().decode('utf-8').rstrip()
                    self.current_distance = float(line.split("cm")[0])
                except:
                    pass
            time.sleep(0.02)

    def get_real_distance(self):
        return self.current_distance - self.cfg['sensor_offset_x']

    def set_move_pose(self):
        TTLServo.servoAngleCtrl(1, 5, 1, 150)
        TTLServo.servoAngleCtrl(2, 0, 1, 150)  # Shoulder
        TTLServo.servoAngleCtrl(3, 90, 1, 150)  # Elbow
        TTLServo.servoAngleCtrl(4, 90, 1, 150) # Gripper (Open)
        TTLServo.servoAngleCtrl(5, -30, 1, 150)
        time.sleep(1.0)
    
    def set_initial_pose(self):
        TTLServo.servoAngleCtrl(1, 5, 1, 150)
        TTLServo.servoAngleCtrl(2, 0, 1, 150)  # Shoulder
        TTLServo.servoAngleCtrl(3, 90, 1, 150) # Elbow
        TTLServo.servoAngleCtrl(4, 90, 1, 150) # Gripper (Open)
        TTLServo.servoAngleCtrl(5, 30, 1, 150)
        time.sleep(1.0)

    def set_drop_pose(self):
        TTLServo.servoAngleCtrl(1, 5, 1, 150)
        TTLServo.servoAngleCtrl(2, 0, 1, 100)
        TTLServo.servoAngleCtrl(2, 45, 1, 150)
        TTLServo.servoAngleCtrl(3, -90, 1, 150)
        time.sleep(5.0)
        TTLServo.servoAngleCtrl(4, 90, 1, 150) # Open
        time.sleep(1.0)

    def execute_grasp(self, class_id, camera_instance=None, detector=None, aligner=None):
        target = self.grasp_table.get(class_id)
        if not target:
            self.logger.warning(f"Class ID {class_id} not in grasp table.")
            return
        
        # 물체 바라보기
        TTLServo.servoAngleCtrl(1, 90, 1, 150)
        time.sleep(1.0)

        # after servo moved, try visual fine alignment if aligner + detector + camera available
        if aligner is not None and detector is not None and camera_instance is not None:
            try:
                aligned = aligner.align_to_object_with_servo(camera_instance, detector, class_id=class_id)
                self.logger.info(f"Visual fine-align result: {aligned}")
            except Exception as e:
                self.logger.warning(f"align_to_object_with_servo failed: {e}")

        self.logger.info(f"Grasping {target['name']}...")
        
        h_cm = target['height'] + self.cfg['height_offset']
        distance_cm = self.current_distance + self.cfg['distance_offset']
        self.logger.info(f"distance : {distance_cm}")
        grip_angle = target['angle']
        
        arm2 = self.cfg['arm2_length']
        arm3 = self.cfg['arm3_length']

        # Inverse Kinematics
        try:
            beta = np.degrees(np.arctan2(h_cm, distance_cm)) + \
                   np.degrees(np.arccos(
                       (arm2**2 + distance_cm**2 + h_cm**2 - arm3**2) /
                       (2 * arm2 * np.sqrt(distance_cm**2 + h_cm**2))
                   ))
            beta = -(90 - beta)
            
            alpha = np.degrees(np.arccos(
                (distance_cm**2 + h_cm**2 - arm2**2 - arm3**2) /
                (2 * arm2 * arm3)
            ))
            
            alpha -= self.cfg['angle3_offset']
            beta -= self.cfg['angle2_offset']

            # Move Arm

            TTLServo.servoAngleCtrl(2, int(beta), 1, 100)
            TTLServo.servoAngleCtrl(3, int(alpha), 1, 100)
            time.sleep(5)
            
            # Grip
            TTLServo.servoAngleCtrl(4, grip_angle, 1, 150)
            time.sleep(5)
            
            # Lift
            TTLServo.servoAngleCtrl(2, 0, 1, 80)
            TTLServo.servoAngleCtrl(3, -50, 1, 80)
            time.sleep(1.0)
            
        except Exception as e:
            self.logger.error(f"IK Calculation Error: {e}")

    def close(self):
        self.stop_sensor = True
        if hasattr(self, 'ser'): self.ser.close()