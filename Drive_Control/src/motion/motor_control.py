from jetbot import Robot
import time

class MotorControl:
    def __init__(self, config):
        self.robot = Robot()
        self.speed_move = config['motor']['speed_move']
        self.speed_turn = config['motor']['speed_turn']

    def stop(self):
        self.robot.stop()

    def set_motors(self, left_speed, right_speed):
        self.robot.set_motors(left_speed, right_speed)

    def forward(self, duration=None):
        self.robot.forward(self.speed_move)
        if duration:
            time.sleep(duration)
            self.stop()

    def turn_left(self, duration):
        self.robot.left(self.speed_turn)
        time.sleep(duration)

    def turn_right(self, duration):
        self.robot.right(self.speed_turn)
        time.sleep(duration)