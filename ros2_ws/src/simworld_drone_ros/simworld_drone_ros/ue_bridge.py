import os
import math
import time

import rclpy
from rclpy.node import Node

from geometry_msgs.msg import Twist
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Odometry
from std_msgs.msg import String

try:
    import unrealcv
except ImportError:
    unrealcv = None


class UeBridge(Node):
    def __init__(self) -> None:
        super().__init__("ue_bridge")

        self.pose_pub = self.create_publisher(PoseStamped, "/drone/pose", 10)
        self.odom_pub = self.create_publisher(Odometry, "/drone/odom", 10)
        self.status_pub = self.create_publisher(String, "/drone/status", 10)

        self.cmd_sub = self.create_subscription(
            Twist,
            "/drone/cmd_vel",
            self.cmd_callback,
            10,
        )

        self.client = None
        self.connected = False

        self.host = os.getenv("SIMWORLD_HOST", "127.0.0.1")
        self.port = int(os.getenv("SIMWORLD_PORT", "9000"))
        self.drone_asset = os.getenv(
            "SIMWORLD_DRONE_ASSET",
            "/Game/V1/SM_Drone.SM_Drone",
        )
        self.auto_spawn = os.getenv("SIMWORLD_DRONE_AUTO_SPAWN", "1").lower() not in {"0", "false", "no"}
        self.spawn_two = os.getenv("SIMWORLD_SPAWN_TWO_DRONES", "1").lower() not in {"0", "false", "no"}

        # Match the repo's usual humanoid flow, which starts at the world origin.
        self.x = self._read_float_env("SIMWORLD_DRONE_X", 0.0)
        self.y = self._read_float_env("SIMWORLD_DRONE_Y", 0.0)
        self.z = self._read_float_env("SIMWORLD_DRONE_Z", 600.0)
        self.yaw_deg = self._read_float_env("SIMWORLD_DRONE_YAW", 0.0)
        self.drone_a_name = os.getenv("SIMWORLD_DRONE_A_NAME", "DroneA")
        self.drone_b_name = os.getenv("SIMWORLD_DRONE_B_NAME", "DroneB")
        self.drone_a_x = self._read_float_env("SIMWORLD_DRONE_A_X", 600.0)
        self.drone_b_x = self._read_float_env("SIMWORLD_DRONE_B_X", -600.0)
        self.drone_a_y = self._read_float_env("SIMWORLD_DRONE_A_Y", self.y)
        self.drone_b_y = self._read_float_env("SIMWORLD_DRONE_B_Y", self.y)
        self.drone_a_z = self._read_float_env("SIMWORLD_DRONE_A_Z", self.z)
        self.drone_b_z = self._read_float_env("SIMWORLD_DRONE_B_Z", self.z)

        self.spawned = False

        self.timer = self.create_timer(0.1, self.tick)

        self.connect_unrealcv()

    def _read_float_env(self, name: str, default: float) -> float:
        value = os.getenv(name)
        if value is None:
            return default
        try:
            return float(value)
        except ValueError:
            self.get_logger().warning(
                f"Invalid {name} value '{value}', using default {default}"
            )
            return default

    def connect_unrealcv(self) -> None:
        if unrealcv is None:
            self.get_logger().error("unrealcv Python package is not installed")
            return

        try:
            self.client = unrealcv.Client((self.host, self.port))
            self.client.connect()
            self.connected = self.client.isconnected()
            if self.connected:
                self.get_logger().info(f"Connected to UnrealCV at {self.host}:{self.port}")
                self.publish_status("connected")
            else:
                self.get_logger().error("Could not connect to UnrealCV")
                self.publish_status("disconnected")
        except Exception as e:
            self.get_logger().error(f"UnrealCV connection failed: {e}")
            self.publish_status("connection_failed")

    def publish_status(self, text: str) -> None:
        msg = String()
        msg.data = text
        self.status_pub.publish(msg)

    def _spawn_named_actor(self, name: str, x: float, y: float, z: float) -> None:
        if self.drone_asset.endswith("_C"):
            result = self.client.request(
                f"vset /objects/spawn_bp_asset {self.drone_asset} {name}"
            )
        else:
            result = self.client.request(
                f"vset /objects/spawn {self.drone_asset} {name}"
            )
        self.get_logger().info(
            f"Spawn result for asset '{self.drone_asset}' as '{name}': {result}"
        )
        self.client.request(f"vset /object/{name}/location {x} {y} {z}")
        self.client.request(f"vset /object/{name}/rotation 0 {self.yaw_deg} 0")
        self.get_logger().info(
            f"Placed '{name}' at x={x}, y={y}, z={z}, yaw={self.yaw_deg}"
        )

    def spawn_drone_once(self) -> None:
        if not self.connected or self.spawned or not self.auto_spawn:
            return

        try:
            self._spawn_named_actor(self.drone_a_name, self.drone_a_x, self.drone_a_y, self.drone_a_z)
            if self.spawn_two:
                self._spawn_named_actor(self.drone_b_name, self.drone_b_x, self.drone_b_y, self.drone_b_z)
            self.spawned = True
            self.publish_status("spawned")
        except Exception as e:
            self.get_logger().warning(f"Drone spawn skipped/failed: {e}")

    def tick(self) -> None:
        if not self.connected:
            return

        if not self.spawned:
            self.spawn_drone_once()

        self.publish_pose()
        self.publish_odom()

    def publish_pose(self) -> None:
        msg = PoseStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "world"

        msg.pose.position.x = self.x
        msg.pose.position.y = self.y
        msg.pose.position.z = self.z

        yaw_rad = math.radians(self.yaw_deg)
        msg.pose.orientation.z = math.sin(yaw_rad / 2.0)
        msg.pose.orientation.w = math.cos(yaw_rad / 2.0)

        self.pose_pub.publish(msg)

    def publish_odom(self) -> None:
        msg = Odometry()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "world"
        msg.child_frame_id = "drone"

        msg.pose.pose.position.x = self.x
        msg.pose.pose.position.y = self.y
        msg.pose.pose.position.z = self.z

        yaw_rad = math.radians(self.yaw_deg)
        msg.pose.pose.orientation.z = math.sin(yaw_rad / 2.0)
        msg.pose.pose.orientation.w = math.cos(yaw_rad / 2.0)

        self.odom_pub.publish(msg)

    def cmd_callback(self, msg: Twist) -> None:
        dt = 0.1

        self.x += msg.linear.x * dt
        self.y += msg.linear.y * dt
        self.z += msg.linear.z * dt
        self.yaw_deg += msg.angular.z * 20.0 * dt
        self.drone_a_x += msg.linear.x * dt
        self.drone_a_y += msg.linear.y * dt
        self.drone_a_z += msg.linear.z * dt

        if self.connected:
            try:
                self.client.request(
                    f"vset /object/{self.drone_a_name}/location {self.drone_a_x} {self.drone_a_y} {self.drone_a_z}"
                )
                self.client.request(
                    f"vset /object/{self.drone_a_name}/rotation 0 {self.yaw_deg} 0"
                )
                if self.spawn_two:
                    self.drone_b_x += msg.linear.x * dt
                    self.drone_b_y += msg.linear.y * dt
                    self.drone_b_z += msg.linear.z * dt
                    self.client.request(
                        f"vset /object/{self.drone_b_name}/location {self.drone_b_x} {self.drone_b_y} {self.drone_b_z}"
                    )
                    self.client.request(
                        f"vset /object/{self.drone_b_name}/rotation 0 {self.yaw_deg} 0"
                    )
            except Exception as e:
                self.get_logger().warning(f"Move update failed: {e}")


def main(args=None) -> None:
    rclpy.init(args=args)
    node = UeBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
