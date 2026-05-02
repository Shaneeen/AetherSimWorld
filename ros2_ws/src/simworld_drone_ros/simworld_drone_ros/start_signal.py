import sys
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class StartSignal(Node):
    def __init__(self, command: str) -> None:
        super().__init__("start_signal")
        self.command = command
        self.pub = self.create_publisher(String, "/sim/control", 10)

    def send(self) -> None:
        msg = String()
        msg.data = self.command
        # Small delay so DDS discovery can settle before we publish.
        time.sleep(0.5)
        for _ in range(3):
            self.pub.publish(msg)
            time.sleep(0.2)
        self.get_logger().info(f"Published control command: {self.command}")


def main(args=None) -> None:
    command = "start"
    if args is None:
        args = sys.argv[1:]
    if args:
        command = args[0].strip().lower()
    rclpy.init(args=None)
    node = StartSignal(command)
    try:
        node.send()
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
