import math
import os

import rclpy
from rclpy.node import Node

from geometry_msgs.msg import PoseStamped
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from std_msgs.msg import String

try:
    import unrealcv
except ImportError:
    unrealcv = None


def quaternion_from_yaw(yaw_deg: float) -> tuple[float, float]:
    yaw_rad = math.radians(yaw_deg)
    return math.sin(yaw_rad / 2.0), math.cos(yaw_rad / 2.0)


class UeBridge(Node):
    def __init__(self) -> None:
        super().__init__("ue_bridge")

        self.status_pub = self.create_publisher(String, "/sim/status", 20)
        self.pose_a_pub = self.create_publisher(PoseStamped, "/drone_a/pose", 10)
        self.pose_b_pub = self.create_publisher(PoseStamped, "/drone_b/pose", 10)
        self.odom_a_pub = self.create_publisher(Odometry, "/drone_a/odom", 10)
        self.odom_b_pub = self.create_publisher(Odometry, "/drone_b/odom", 10)

        self.cmd_a_sub = self.create_subscription(
            Twist,
            "/drone_a/cmd_vel",
            self.cmd_a_callback,
            10,
        )
        self.cmd_b_sub = self.create_subscription(
            Twist,
            "/drone_b/cmd_vel",
            self.cmd_b_callback,
            10,
        )

        self.client = None
        self.connected = False
        self.spawned = False

        self.host = os.getenv("SIMWORLD_HOST", "127.0.0.1")
        self.port = int(os.getenv("SIMWORLD_PORT", "9000"))
        self.drone_asset = os.getenv(
            "SIMWORLD_DRONE_ASSET",
            "/Game/CityDatabase/blueprints/BP_Box3.BP_Box3_C",
        )
        self.drone_a_asset = os.getenv(
            "SIMWORLD_DRONE_A_ASSET",
            os.getenv("SIMWORLD_DRONE_ASSET_A", self.drone_asset),
        )
        self.drone_b_asset = os.getenv(
            "SIMWORLD_DRONE_B_ASSET",
            os.getenv("SIMWORLD_DRONE_ASSET_B", self.drone_asset),
        )
        self.auto_spawn = os.getenv("SIMWORLD_DRONE_AUTO_SPAWN", "1").lower() not in {"0", "false", "no"}
        self.tick_dt = self._read_float_env("SIMWORLD_BRIDGE_DT", 0.1)

        default_y = self._read_float_env("SIMWORLD_DRONE_Y", 0.0)
        default_z = self._read_float_env("SIMWORLD_DRONE_Z", 600.0)
        default_yaw = self._read_float_env("SIMWORLD_DRONE_YAW", 0.0)

        self.actor_a = {
            "name": os.getenv("SIMWORLD_DRONE_A_NAME", "DroneA"),
            "x": self._read_float_env("SIMWORLD_DRONE_A_X", 600.0),
            "y": self._read_float_env("SIMWORLD_DRONE_A_Y", default_y),
            "z": self._read_float_env("SIMWORLD_DRONE_A_Z", default_z),
            "yaw_deg": self._read_float_env("SIMWORLD_DRONE_A_YAW", default_yaw),
            "asset": self.drone_a_asset,
            "scale": self._read_scale_env("SIMWORLD_DRONE_A_SCALE", [0.7, 0.7, 0.08]),
            "color": self._read_color_env("SIMWORLD_DRONE_A_COLOR", [255, 50, 50]),
            "color_applied": False,
        }
        self.actor_b = {
            "name": os.getenv("SIMWORLD_DRONE_B_NAME", "DroneB"),
            "x": self._read_float_env("SIMWORLD_DRONE_B_X", -600.0),
            "y": self._read_float_env("SIMWORLD_DRONE_B_Y", default_y),
            "z": self._read_float_env("SIMWORLD_DRONE_B_Z", default_z),
            "yaw_deg": self._read_float_env("SIMWORLD_DRONE_B_YAW", default_yaw),
            "asset": self.drone_b_asset,
            "scale": self._read_scale_env("SIMWORLD_DRONE_B_SCALE", [0.7, 0.7, 0.08]),
            "color": self._read_color_env("SIMWORLD_DRONE_B_COLOR", [60, 140, 255]),
            "color_applied": False,
        }

        self.timer = self.create_timer(self.tick_dt, self.tick)
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

    def _read_color_env(self, name: str, default: list[int]) -> list[int]:
        value = os.getenv(name)
        if value is None:
            return list(default)
        try:
            parts = [int(part.strip()) for part in value.split(",")]
            if len(parts) != 3:
                raise ValueError("expected 3 components")
            return [max(0, min(255, part)) for part in parts]
        except ValueError:
            self.get_logger().warning(
                f"Invalid {name} value '{value}', using default {default}"
            )
            return list(default)

    def _read_scale_env(self, name: str, default: list[float]) -> list[float]:
        value = os.getenv(name)
        if value is None:
            return list(default)
        try:
            parts = [float(part.strip()) for part in value.split(",")]
            if len(parts) != 3:
                raise ValueError("expected 3 components")
            return parts
        except ValueError:
            self.get_logger().warning(
                f"Invalid {name} value '{value}', using default {default}"
            )
            return list(default)

    def publish_status(self, text: str) -> None:
        msg = String()
        msg.data = text
        self.status_pub.publish(msg)
        self.get_logger().info(text)

    def connect_unrealcv(self) -> None:
        if unrealcv is None:
            self.publish_status("UE bridge error: unrealcv Python package is not installed")
            return

        try:
            self.client = unrealcv.Client((self.host, self.port))
            self.client.connect()
            self.connected = self.client.isconnected()
        except Exception as exc:
            self.connected = False
            self.publish_status(f"UE bridge error: UnrealCV connection failed: {exc}")
            return

        if self.connected:
            self.publish_status(f"UE bridge connected to UnrealCV at {self.host}:{self.port}")
        else:
            self.publish_status(f"UE bridge error: Could not connect to UnrealCV at {self.host}:{self.port}")

    def _spawn_named_actor(self, actor: dict, label: str) -> None:
        asset = actor.get("asset", self.drone_asset)
        if asset.endswith("_C"):
            result = self.client.request(
                f"vset /objects/spawn_bp_asset {asset} {actor['name']}"
            )
        else:
            result = self.client.request(
                f"vset /objects/spawn {asset} {actor['name']}"
            )

        result_text = str(result).strip()
        if result_text.lower().startswith("error"):
            raise RuntimeError(result_text)

        self.client.request(
            f"vset /object/{actor['name']}/location {actor['x']} {actor['y']} {actor['z']}"
        )
        self.client.request(
            f"vset /object/{actor['name']}/rotation 0 {actor['yaw_deg']} 0"
        )
        scale = actor.get("scale")
        if scale is not None:
            self.client.request(
                f"vset /object/{actor['name']}/scale {scale[0]} {scale[1]} {scale[2]}"
            )
        self._apply_actor_color(actor)
        self.publish_status(
            f"{label} spawned as {actor['name']} using {asset} at x={actor['x']:.1f}, y={actor['y']:.1f}, z={actor['z']:.1f}"
        )

    def _apply_actor_color(self, actor: dict) -> None:
        color = actor.get("color")
        if color is None:
            return
        try:
            response = self.client.request(
                f"vset /object/{actor['name']}/color {color[0]} {color[1]} {color[2]}"
            )
            response_text = str(response).strip().lower()
            actor["color_applied"] = not response_text.startswith("error")
            if actor["color_applied"]:
                self.publish_status(
                    f"{actor['name']} color set to rgb({color[0]}, {color[1]}, {color[2]})"
                )
            else:
                self.get_logger().warning(
                    f"Color set failed for {actor['name']}: {response}"
                )
        except Exception as exc:
            actor["color_applied"] = False
            self.get_logger().warning(
                f"Color set failed for {actor['name']}: {exc}"
            )

    def spawn_drones_once(self) -> None:
        if not self.connected or self.spawned or not self.auto_spawn:
            return

        try:
            self._spawn_named_actor(self.actor_a, "DroneA")
            self._spawn_named_actor(self.actor_b, "DroneB")
            self.spawned = True
            self.publish_status("UE bridge ready")
        except Exception as exc:
            self.publish_status(f"UE bridge error: spawn failed: {exc}")

    def _publish_pose(self, actor: dict, publisher: any, frame_id: str) -> None:
        msg = PoseStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = frame_id
        msg.pose.position.x = actor["x"]
        msg.pose.position.y = actor["y"]
        msg.pose.position.z = actor["z"]
        qz, qw = quaternion_from_yaw(actor["yaw_deg"])
        msg.pose.orientation.z = qz
        msg.pose.orientation.w = qw
        publisher.publish(msg)

    def _publish_odom(self, actor: dict, publisher: any, child_frame_id: str) -> None:
        msg = Odometry()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "world"
        msg.child_frame_id = child_frame_id
        msg.pose.pose.position.x = actor["x"]
        msg.pose.pose.position.y = actor["y"]
        msg.pose.pose.position.z = actor["z"]
        qz, qw = quaternion_from_yaw(actor["yaw_deg"])
        msg.pose.pose.orientation.z = qz
        msg.pose.pose.orientation.w = qw
        publisher.publish(msg)

    def _apply_motion(self, actor: dict, msg: Twist) -> None:
        actor["x"] += msg.linear.x * self.tick_dt
        actor["y"] += msg.linear.y * self.tick_dt
        actor["z"] += msg.linear.z * self.tick_dt
        actor["yaw_deg"] += msg.angular.z * 20.0 * self.tick_dt

    def _push_actor_state(self, actor: dict) -> None:
        self.client.request(
            f"vset /object/{actor['name']}/location {actor['x']} {actor['y']} {actor['z']}"
        )
        self.client.request(
            f"vset /object/{actor['name']}/rotation 0 {actor['yaw_deg']} 0"
        )

    def cmd_a_callback(self, msg: Twist) -> None:
        if not self.connected or not self.spawned:
            return
        self._apply_motion(self.actor_a, msg)
        try:
            self._push_actor_state(self.actor_a)
        except Exception as exc:
            self.publish_status(f"UE bridge error: DroneA move failed: {exc}")

    def cmd_b_callback(self, msg: Twist) -> None:
        if not self.connected or not self.spawned:
            return
        self._apply_motion(self.actor_b, msg)
        try:
            self._push_actor_state(self.actor_b)
        except Exception as exc:
            self.publish_status(f"UE bridge error: DroneB move failed: {exc}")

    def tick(self) -> None:
        if not self.connected:
            return
        if not self.spawned:
            self.spawn_drones_once()
        elif not self.actor_a.get("color_applied") or not self.actor_b.get("color_applied"):
            self._apply_actor_color(self.actor_a)
            self._apply_actor_color(self.actor_b)
        self._publish_pose(self.actor_a, self.pose_a_pub, "drone_a")
        self._publish_pose(self.actor_b, self.pose_b_pub, "drone_b")
        self._publish_odom(self.actor_a, self.odom_a_pub, "drone_a")
        self._publish_odom(self.actor_b, self.odom_b_pub, "drone_b")


def main(args=None) -> None:
    rclpy.init(args=args)
    node = UeBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
