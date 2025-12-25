import math
import time
import numpy as np
from ..utils.logger import get_logger

class Navigator:
    def __init__(self, motor_control, aligner, config, grasper=None, detector=None):
        self.motor = motor_control
        self.aligner = aligner
        self.grasper = grasper
        self.detector = detector
        self.logger = get_logger("Navigator")
        # keep full config and motor-specific config
        self.full_cfg = config
        self.cfg = config['motor']
        self.current_pos = [0.0, 0.0]
        self.current_angle = 90.0

    def move_straight(self, distance_m):
        if distance_m <= 0: return
        duration = distance_m * self.cfg['time_per_1m']
        self.logger.info(f"Forward {distance_m:.2f}m ({duration:.2f}s)")
        self.motor.forward(duration)

    def turn_to_angle(self, target_angle_deg):
        diff = target_angle_deg - self.current_angle
        while diff > 180: diff -= 360
        while diff <= -180: diff += 360
        
        if abs(diff) < 1.0: return

        # Calculate duration
        if diff > 0: # Left
            duration = diff * (self.cfg['time_per_90_deg_left'] / 90.0)
            self.motor.turn_left(duration)
            lat_offset = -self.cfg['offset_lateral_90']
            lon_offset = self.cfg['offset_longitudinal_90']
        else: # Right
            duration = abs(diff) * (self.cfg['time_per_90_deg_right'] / 90.0)
            self.motor.turn_right(duration)
            lat_offset = self.cfg['offset_lateral_90']
            lon_offset = self.cfg['offset_longitudinal_90']
            
        self.motor.stop()

        # Correct Position (Offset Logic)
        ratio = abs(diff) / 90.0
        rad = math.radians(self.current_angle)
        vec_fwd = np.array([math.cos(rad), math.sin(rad)])
        vec_right = np.array([math.sin(rad), -math.cos(rad)])
        
        delta_pos = (vec_fwd * (lon_offset * ratio)) + (vec_right * (lat_offset * ratio))
        self.current_pos[0] += delta_pos[0]
        self.current_pos[1] += delta_pos[1]
        self.current_angle = target_angle_deg
        
        self.logger.info(f"Turned to {target_angle_deg} deg. Pos corrected by {delta_pos}")

    def execute_path(self, path_data, camera_instance=None, on_grasp=None):
        if not path_data: return
        
        self.current_pos = path_data[0]
        self.logger.info(f"Starting Path from {self.current_pos}")
        # grasp table and tolerance
        grasp_table = self.full_cfg.get('manipulation', {}).get('grasp_table', {})

        for i in range(1, len(path_data)):
            target_pos = path_data[i]
            curr_x, curr_y = self.current_pos
            next_x, next_y = target_pos
            
            dx = next_x - curr_x
            dy = next_y - curr_y
            
            if math.hypot(dx, dy) < 0.005: continue

            # 1. Turn
            target_angle_rad = math.atan2(dy, dx)
            target_angle_deg = math.degrees(target_angle_rad)
            self.turn_to_angle(target_angle_deg)

            # 2. Move
            new_dx = next_x - self.current_pos[0]
            new_dy = next_y - self.current_pos[1]
            dist = math.hypot(new_dx, new_dy)
            self.move_straight(dist)

            if camera_instance:
                self.aligner.align_to_red_marker(camera_instance)
            
            self.current_pos = target_pos

            # 3. Check for grasping opportunity
            do_grasp = False
            wx, wy = float(self.current_pos[0]), float(self.current_pos[1])
            runtime_order = self.full_cfg.get('runtime_order')

            # runtime_order 중에 location에 도달했는지 확인
            for cid, info in grasp_table.items():
                try:
                    name = info.get('name')
                    loc = info.get('location')
                    if name in runtime_order:
                        lx, ly = float(loc[0]), float(loc[1])
                        if lx == wx and ly == wy:
                            do_grasp = True
                            self.logger.info(f"At grasp location {info.get('name')} (class {cid}).")
                            break
                except Exception:
                    continue

            # grasp 실행
            if do_grasp and self.grasper:
                try:
                    self.logger.info(f"Arrived at ordered grasp location {name} (class {cid}). Running grasp.")
                    # stop motors
                    try:
                        self.motor.stop()
                    except Exception:
                        pass
                    # align visually if camera provided
                    if camera_instance:
                        try:
                            self.aligner.align_to_red_marker(camera_instance)
                        except Exception as e:
                            self.logger.warning(f"Aligner failed: {e}")

                    try:
                        # pass camera/detector/aligner so Grasper can perform visual fine-alignment
                        self.grasper.set_initial_pose()
                        self.grasper.execute_grasp(int(cid), camera_instance=camera_instance, detector=self.detector, aligner=self.aligner)
                        self.grasper.set_drop_pose()
                        self.grasper.set_move_pose()
                        # update runtime_order in config
                        try:
                            ro = self.full_cfg.get('runtime_order', [])
                            if name and name in ro:
                                ro.remove(name)
                                self.full_cfg['runtime_order'] = ro
                        except Exception:
                            pass
                    except Exception as e:
                        self.logger.error(f"Grasp failed in navigator: {e}")
                except Exception as e:
                    self.logger.error(f"Navigator grasp error: {e}")
            elif on_grasp:
                try:
                    on_grasp(int(cid))
                except Exception as e:
                    self.logger.error(f"on_grasp callback error: {e}")