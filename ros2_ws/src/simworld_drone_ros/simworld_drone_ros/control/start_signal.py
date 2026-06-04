import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String


CONTROL_QOS = QoSProfile(depth=10)
CONTROL_QOS.reliability = ReliabilityPolicy.RELIABLE
CONTROL_QOS.durability = DurabilityPolicy.TRANSIENT_LOCAL


class StartSignal(Node):
    def __init__(self, command: str) -> None:
        super().__init__("start_signal")
        self.command = command
        self.target_pub = self.create_publisher(String, "/drone_a/control", CONTROL_QOS)
        self.chaser_pub = self.create_publisher(String, "/drone_b/control", CONTROL_QOS)
        self.team_pub = self.create_publisher(String, "/team/control", CONTROL_QOS)
        self.reset_pub = self.create_publisher(String, "/sim/reset_chase", CONTROL_QOS)

    def send(self) -> None:
        msg = String()
        msg.data = self.command
        self._wait_for_discovery()
        if self.command in {"reset", "reset_chase", "randomize", "randomize_start"}:
            for _ in range(40):
                self.reset_pub.publish(msg)
                rclpy.spin_once(self, timeout_sec=0.05)
                time.sleep(0.15)
            end_at = time.time() + 2.0
            while time.time() < end_at:
                rclpy.spin_once(self, timeout_sec=0.05)
                time.sleep(0.05)
            self.get_logger().info(f"Published chase reset command: {self.command}")
            return

        for _ in range(40):
            self.target_pub.publish(msg)
            self.chaser_pub.publish(msg)
            self.team_pub.publish(msg)
            rclpy.spin_once(self, timeout_sec=0.05)
            time.sleep(0.15)
        end_at = time.time() + 2.0
        while time.time() < end_at:
            rclpy.spin_once(self, timeout_sec=0.05)
            time.sleep(0.05)
        self.get_logger().info(f"Published control command: {self.command}")

    def _wait_for_discovery(self) -> None:
        if self.command in {"stop", "stop_a", "stop_b", "stop_all", "stop_team"}:
            return
        deadline = time.time() + 8.0
        while time.time() < deadline:
            if self.command in {"reset", "reset_chase", "randomize", "randomize_start"}:
                if self.reset_pub.get_subscription_count() > 0:
                    return
            elif self.target_pub.get_subscription_count() > 0 and self.chaser_pub.get_subscription_count() > 0:
                return
            rclpy.spin_once(self, timeout_sec=0.1)
            time.sleep(0.1)


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
