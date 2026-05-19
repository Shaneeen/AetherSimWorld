import sys
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class StartSignal(Node):
    def __init__(self, command: str) -> None:
        super().__init__("start_signal")
        self.command = command
        self.target_pub = self.create_publisher(String, "/drone_a/control", 10)
        self.chaser_pub = self.create_publisher(String, "/drone_b/control", 10)
        self.reset_pub = self.create_publisher(String, "/sim/reset_chase", 10)

    def send(self) -> None:
        msg = String()
        msg.data = self.command
        # Small delay so DDS discovery can settle before we publish.
        time.sleep(0.5)
        if self.command in {"reset", "reset_chase", "randomize", "randomize_start"}:
            for _ in range(3):
                self.reset_pub.publish(msg)
                time.sleep(0.2)
            self.get_logger().info(f"Published chase reset command: {self.command}")
            return

        for _ in range(3):
            self.target_pub.publish(msg)
            self.chaser_pub.publish(msg)
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
