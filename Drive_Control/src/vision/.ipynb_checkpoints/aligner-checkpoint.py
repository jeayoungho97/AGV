import cv2
import numpy as np
import time
from ..utils.logger import get_logger

class Aligner:
    def __init__(self, motor_control, config):
        self.motor = motor_control
        self.logger = get_logger("Aligner")
        self.timeout = config['vision']['align_timeout']
        self.error_offset = config['vision']['align_error_offset']
        self.turn_gain = config['vision']['turn_gain']
        self.servo_gain = config['vision'].get('servo_gain', 0.1)
        
        # HSV ranges for Red
        self.lower_red1 = np.array([0, 85, 0])
        self.upper_red1 = np.array([10, 255, 255])
        self.lower_red2 = np.array([110, 45, 50])
        self.upper_red2 = np.array([180, 255, 255])

    def align_to_red_marker(self, camera_instance):
        self.logger.info("Searching for RED marker...")
        start_time = time.time()
        
        while (time.time() - start_time) < self.timeout:
            image = camera_instance.value
            if image is None: continue
            
            hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
            mask1 = cv2.inRange(hsv, self.lower_red1, self.upper_red1)
            mask2 = cv2.inRange(hsv, self.lower_red2, self.upper_red2)
            mask = cv2.bitwise_or(mask1, mask2)
            mask = cv2.erode(mask, None, iterations=2)
            mask = cv2.dilate(mask, None, iterations=2)
            
            cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            if len(cnts) > 0:
                c = max(cnts, key=cv2.contourArea)
                M = cv2.moments(c)
                
                if M["m00"] != 0:
                    cx = int(M["m10"] / M["m00"])
                    center_x = image.shape[1] / 2
                    error = (cx - center_x) / center_x
                    
                    if abs(error) < self.error_offset:
                        self.logger.info(f"Aligned! Error: {error:.4f}")
                        self.motor.stop()
                        return True
                    
                    turn_speed = error * self.turn_gain
                    # Clamp speed
                    min_speed = 0.08
                    max_speed = 0.4
                    if 0 < turn_speed < min_speed: turn_speed = min_speed
                    if -min_speed < turn_speed < 0: turn_speed = -min_speed
                    if turn_speed > max_speed: turn_speed = max_speed
                    if turn_speed < -max_speed: turn_speed = -max_speed
                    
                    self.motor.set_motors(turn_speed, -turn_speed)
                else:
                    self.motor.stop()
            else:
                self.motor.stop()
            time.sleep(0.01)
        
        self.logger.warning("Alignment Timeout")
        self.motor.stop()
        return False

    def align_to_object_with_servo(self, camera_instance, detector, neutral=90, tol_px=12, timeout=3.0, min_angle=-90, max_angle=90, class_id=0):
        """Use detector to find object center and adjust servo 1 so object's center
        aligns with image vertical center. Calls TTLServo.servoAngleCtrl(1, value, 1, 150).

        Args:
            camera_instance: camera providing `.value` images
            detector: ObjectDetector instance with `.detect(image)` returning detections with 'bbox' and 'score'
            neutral: baseline servo angle (degrees)
            gain: degrees to apply for normalized error of 1.0
            tol_px: pixel tolerance for alignment
            timeout: seconds to attempt alignment
            min_angle, max_angle: servo angle clamps

        Returns:
            True if aligned within tolerance, False otherwise
        """
        from SCSCtrl import TTLServo

        gain = self.servo_gain
        start = time.time()
        while (time.time() - start) < timeout:
            image = camera_instance.value
            if image is None:
                time.sleep(0.05)
                continue

            detections = detector.detect(image)
            if not detections:
                time.sleep(0.05)
                continue

            # pick detection whose center is closest to image vertical center
            img_cx = image.shape[1] / 2.0
            best = None
            best_dist = None
            for d in detections:
                if d.get('class_id') != class_id:
                    continue
                try:
                    x1, y1, x2, y2 = d.get('bbox', (0,0,0,0))
                    obj_cx = (x1 + x2) / 2.0
                    dist = abs(obj_cx - img_cx)
                    if best is None or dist < best_dist:
                        best = d
                        best_dist = dist
                except Exception:
                    continue
            if best is None:
                time.sleep(0.05)
                continue
            x1, y1, x2, y2 = best.get('bbox', (0,0,0,0))
            obj_cx = (x1 + x2) / 2.0
            img_cx = image.shape[1] / 2.0
            error_px = obj_cx - img_cx
            self.logger.info(f"{best}")

            # normalized error in [-1,1]
            norm_err = error_px / img_cx
            delta_angle = norm_err * gain
            value = neutral + delta_angle
            # clamp
            if value < min_angle: value = min_angle
            if value > max_angle: value = max_angle

            try:
                TTLServo.servoAngleCtrl(1, int(round(value)), 1, 150)
            except Exception as e:
                self.logger.warning(f"Failed to set servo angle: {e}")

            self.logger.info(f"Align servo -> value={value:.1f} (delta_angle={delta_angle:.1f})")

            if abs(error_px) <= tol_px:
                self.logger.info("Object aligned within tolerance")
                return True

            time.sleep(0.05)

        self.logger.warning("align_to_object_with_servo: timeout")
        return False