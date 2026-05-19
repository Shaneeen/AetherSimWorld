import math
import os
import random
import time

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
        self.legacy_status_pub = self.create_publisher(String, "/drone/status", 20)
        self.legacy_pose_pub = self.create_publisher(PoseStamped, "/drone/pose", 10)
        self.legacy_odom_pub = self.create_publisher(Odometry, "/drone/odom", 10)
        self.pose_a_pub = self.create_publisher(PoseStamped, "/drone_a/pose", 10)
        self.pose_b_pub = self.create_publisher(PoseStamped, "/drone_b/pose", 10)
        self.odom_a_pub = self.create_publisher(Odometry, "/drone_a/odom", 10)
        self.odom_b_pub = self.create_publisher(Odometry, "/drone_b/odom", 10)

        self.legacy_cmd_sub = self.create_subscription(
            Twist,
            "/drone/cmd_vel",
            self.cmd_a_callback,
            10,
        )
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
        self.reset_sub = self.create_subscription(
            String,
            "/sim/reset_chase",
            self.reset_chase_callback,
            10,
        )

        self.client = None
        self.connected = False
        self.spawned = False
        self.last_connect_attempt_at = 0.0
        self.reconnect_interval_sec = self._read_float_env("SIMWORLD_BRIDGE_RECONNECT_SEC", 2.0)

        self.host = os.getenv("SIMWORLD_HOST", "127.0.0.1")
        self.port = int(os.getenv("SIMWORLD_PORT", "9000"))
        self.drone_asset = os.getenv(
            "SIMWORLD_DRONE_ASSET",
            "StaticMeshActor",
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
        self.use_existing = os.getenv("SIMWORLD_USE_EXISTING_DRONES", "0").lower() in {"1", "true", "yes"}
        self.tick_dt = self._read_float_env("SIMWORLD_BRIDGE_DT", 0.1)
        self.min_z = self._read_float_env(
            "SIMWORLD_DRONE_MIN_Z",
            self._read_float_env("SIM_DRONE_MIN_Z", 100.0),
        )
        self.max_z = self._read_float_env(
            "SIMWORLD_DRONE_MAX_Z",
            self._read_float_env("SIM_DRONE_MAX_Z", 700.0),
        )
        if self.min_z > self.max_z:
            self.get_logger().warning(
                f"SIMWORLD_DRONE_MIN_Z {self.min_z} is above max {self.max_z}; swapping values"
            )
            self.min_z, self.max_z = self.max_z, self.min_z
        self.swept_movement = os.getenv("SIMWORLD_DRONE_SWEEP", "1").lower() not in {"0", "false", "no"}
        self._swept_move_available = self.swept_movement
        self.drone_collision_radius = self._read_float_env("SIM_DRONE_COLLISION_RADIUS_CM", 70.0)
        self.obstacle_collision_enabled = (
            os.getenv("SIM_OBSTACLE_COLLISION_ENABLED", "1").lower() not in {"0", "false", "no"}
        )
        self.obstacle_name_patterns = [
            pattern.strip().lower()
            for pattern in os.getenv("SIM_OBSTACLE_NAME_PATTERNS", "obstacle").split(",")
            if pattern.strip()
        ]
        self.obstacle_collision_radius = self._read_float_env("SIM_OBSTACLE_RADIUS_CM", 170.0)
        self.obstacle_min_z = self._read_float_env("SIM_OBSTACLE_MIN_Z", self.min_z)
        self.obstacle_max_z = self._read_float_env("SIM_OBSTACLE_MAX_Z", self.max_z)
        self.collision_blockers = self._read_collision_blockers_env()
        self.spawn_bound_x = self._read_float_env(
            "SIM_CHASE_SPAWN_BOUND_X",
            self._read_float_env("SIM_TARGET_BOUND_X", 1800.0),
        )
        self.spawn_bound_y = self._read_float_env(
            "SIM_CHASE_SPAWN_BOUND_Y",
            self._read_float_env("SIM_TARGET_BOUND_Y", 1800.0),
        )
        self.spawn_margin = self._read_float_env("SIM_CHASE_SPAWN_MARGIN", 250.0)
        self.catch_distance = self._read_float_env("SIM_CATCH_DISTANCE", 120.0)
        self.tag_pause_sec = self._read_float_env("SIM_TAG_PAUSE_SEC", 0.0)
        self.tag_release_distance = self._read_float_env(
            "SIM_TAG_RELEASE_DISTANCE",
            max(self.catch_distance * 1.2, self.catch_distance + 25.0),
        )
        self.tag_paused_until = 0.0
        self.tag_latched = False
        self.min_start_distance = self._read_float_env(
            "SIM_CHASE_MIN_START_DISTANCE",
            max(700.0, self.catch_distance * 4.0),
        )
        self.spawn_rng = random.Random(int(self._read_float_env("SIM_CHASE_RANDOM_SEED", random.randrange(1, 2**31))))

        default_y = self._read_float_env("SIMWORLD_DRONE_Y", 0.0)
        default_z = self._clamp_z(self._read_float_env("SIMWORLD_DRONE_Z", 600.0))
        default_yaw = self._read_float_env("SIMWORLD_DRONE_YAW", 0.0)

        self.actor_a = {
            "name": os.getenv("SIMWORLD_DRONE_A_NAME", "DroneA"),
            "x": self._read_float_env("SIMWORLD_DRONE_A_X", 600.0),
            "y": self._read_float_env("SIMWORLD_DRONE_A_Y", default_y),
            "z": self._clamp_z(self._read_float_env("SIMWORLD_DRONE_A_Z", default_z)),
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
            "z": self._clamp_z(self._read_float_env("SIMWORLD_DRONE_B_Z", default_z)),
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

    def _read_collision_blockers_env(self) -> list[dict]:
        value = os.getenv("SIM_COLLISION_BLOCKERS", "")
        blockers = []
        for index, item in enumerate(part.strip() for part in value.split(";")):
            if not item:
                continue
            try:
                parts = [float(part.strip()) for part in item.split(",")]
                if len(parts) not in {3, 5}:
                    raise ValueError("expected x,y,radius or x,y,radius,min_z,max_z")
                min_z = parts[3] if len(parts) == 5 else self.obstacle_min_z
                max_z = parts[4] if len(parts) == 5 else self.obstacle_max_z
                blockers.append(
                    {
                        "name": f"env_blocker_{index}",
                        "x": parts[0],
                        "y": parts[1],
                        "radius": max(0.0, parts[2]),
                        "min_z": min(min_z, max_z),
                        "max_z": max(min_z, max_z),
                    }
                )
            except ValueError:
                self.get_logger().warning(
                    f"Invalid SIM_COLLISION_BLOCKERS item '{item}', expected x,y,radius[,min_z,max_z]"
                )
        return blockers

    def _clamp_z(self, z: float) -> float:
        return max(self.min_z, min(self.max_z, float(z)))

    def _random_spawn_point(self) -> tuple[float, float]:
        min_x = -max(0.0, self.spawn_bound_x - self.spawn_margin)
        max_x = max(0.0, self.spawn_bound_x - self.spawn_margin)
        min_y = -max(0.0, self.spawn_bound_y - self.spawn_margin)
        max_y = max(0.0, self.spawn_bound_y - self.spawn_margin)
        return (
            self.spawn_rng.uniform(min_x, max_x),
            self.spawn_rng.uniform(min_y, max_y),
        )

    def _refresh_collision_blockers(self) -> None:
        blockers = self._read_collision_blockers_env()
        if self.obstacle_collision_enabled and self.obstacle_name_patterns:
            blockers.extend(self._discover_obstacle_blockers())
        self.collision_blockers = blockers
        if blockers:
            self.publish_status(
                f"Bridge collision blockers active: {len(blockers)} obstacle/manual blocker(s), "
                f"drone_radius={self.drone_collision_radius:.1f} cm"
            )

    def _discover_obstacle_blockers(self) -> list[dict]:
        try:
            objects = str(self.client.request("vget /objects")).split()
        except Exception as exc:
            self.get_logger().warning(f"Obstacle discovery failed: {exc}")
            return []

        drone_names = {self.actor_a["name"].lower(), self.actor_b["name"].lower()}
        blockers = []
        for name in objects:
            lowered = name.lower()
            if lowered in drone_names:
                continue
            if not any(pattern in lowered for pattern in self.obstacle_name_patterns):
                continue
            try:
                location = str(self.client.request(f"vget /object/{name}/location")).strip()
                parts = location.split()
                if len(parts) < 3:
                    continue
                blockers.append(
                    {
                        "name": name,
                        "x": float(parts[0]),
                        "y": float(parts[1]),
                        "radius": self.obstacle_collision_radius,
                        "min_z": min(self.obstacle_min_z, self.obstacle_max_z),
                        "max_z": max(self.obstacle_min_z, self.obstacle_max_z),
                    }
                )
            except Exception as exc:
                self.get_logger().warning(f"Obstacle discovery skipped {name}: {exc}")
        return blockers

    def _randomize_chase_start(self) -> None:
        max_attempts = 100
        ax, ay = self._random_spawn_point()
        bx, by = self._random_spawn_point()
        for _ in range(max_attempts):
            bx, by = self._random_spawn_point()
            if math.hypot(ax - bx, ay - by) >= self.min_start_distance:
                break
        else:
            bx = -ax
            by = -ay

        self.actor_a["x"] = ax
        self.actor_a["y"] = ay
        self.actor_b["x"] = bx
        self.actor_b["y"] = by
        self.actor_a["yaw_deg"] = self.spawn_rng.uniform(0.0, 360.0)
        self.actor_b["yaw_deg"] = self.spawn_rng.uniform(0.0, 360.0)
        self.actor_a["z"] = self._clamp_z(self.actor_a["z"])
        self.actor_b["z"] = self._clamp_z(self.actor_b["z"])
        self.tag_paused_until = 0.0
        self.tag_latched = False

    def _push_all_actor_states(self) -> None:
        self._push_actor_state(self.actor_a)
        self._push_actor_state(self.actor_b)

    def _publish_all_poses(self) -> None:
        self._publish_pose(self.actor_a, self.pose_a_pub, "drone_a")
        self._publish_pose(self.actor_a, self.legacy_pose_pub, "drone")
        self._publish_pose(self.actor_b, self.pose_b_pub, "drone_b")
        self._publish_odom(self.actor_a, self.odom_a_pub, "drone_a")
        self._publish_odom(self.actor_a, self.legacy_odom_pub, "drone")
        self._publish_odom(self.actor_b, self.odom_b_pub, "drone_b")

    def publish_status(self, text: str) -> None:
        msg = String()
        msg.data = text
        self.status_pub.publish(msg)
        self.legacy_status_pub.publish(msg)
        self.get_logger().info(text)

    def connect_unrealcv(self) -> None:
        self.last_connect_attempt_at = time.time()
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
            if "object exists" in result_text.lower():
                self.publish_status(
                    f"{label} already exists as {actor['name']}; taking control of existing actor"
                )
            else:
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
        if not self.connected or self.spawned:
            return

        try:
            if self.use_existing:
                self._adopt_existing_actor(self.actor_a, "DroneA")
                self._adopt_existing_actor(self.actor_b, "DroneB")
            elif self.auto_spawn:
                self._spawn_named_actor(self.actor_a, "DroneA")
                self._spawn_named_actor(self.actor_b, "DroneB")
            else:
                return
            self._refresh_collision_blockers()
            self._randomize_chase_start()
            self._push_all_actor_states()
            self.spawned = True
            self._publish_all_poses()
            self.publish_status(
                "Chase start reset: "
                f"DroneA=({self.actor_a['x']:.1f},{self.actor_a['y']:.1f}), "
                f"DroneB=({self.actor_b['x']:.1f},{self.actor_b['y']:.1f}), "
                f"distance_cm={math.hypot(self.actor_a['x'] - self.actor_b['x'], self.actor_a['y'] - self.actor_b['y']):.1f}"
            )
            self.publish_status("UE bridge ready")
        except Exception as exc:
            self.publish_status(f"UE bridge error: spawn failed: {exc}")

    def _adopt_existing_actor(self, actor: dict, label: str) -> None:
        objects = str(self.client.request("vget /objects")).split()
        if actor["name"] not in objects:
            raise RuntimeError(
                f"{label} existing actor '{actor['name']}' not found. Available drone-like actors: "
                + ", ".join(name for name in objects if "drone" in name.lower())
            )

        location = str(self.client.request(f"vget /object/{actor['name']}/location")).strip()
        parts = location.split()
        if len(parts) >= 3:
            actor["x"] = float(parts[0])
            actor["y"] = float(parts[1])
            actor["z"] = self._clamp_z(float(parts[2]))
        self._apply_actor_color(actor)
        self.publish_status(
            f"{label} adopted existing actor {actor['name']} at x={actor['x']:.1f}, y={actor['y']:.1f}, z={actor['z']:.1f}"
        )

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

    def _segment_distance_xy(self, ax: float, ay: float, bx: float, by: float, cx: float, cy: float) -> float:
        dx = bx - ax
        dy = by - ay
        length_sq = dx * dx + dy * dy
        if length_sq <= 0.0001:
            return math.hypot(ax - cx, ay - cy)
        t = ((cx - ax) * dx + (cy - ay) * dy) / length_sq
        t = max(0.0, min(1.0, t))
        px = ax + t * dx
        py = ay + t * dy
        return math.hypot(px - cx, py - cy)

    def _z_overlaps(self, z: float, min_z: float, max_z: float) -> bool:
        radius = self.drone_collision_radius
        return z + radius >= min_z and z - radius <= max_z

    def _blocked_by_obstacle(self, old_pos: tuple[float, float, float], new_pos: tuple[float, float, float]) -> bool:
        for blocker in self.collision_blockers:
            if not self._z_overlaps(new_pos[2], blocker["min_z"], blocker["max_z"]):
                continue
            radius = blocker["radius"] + self.drone_collision_radius
            old_distance = math.hypot(old_pos[0] - blocker["x"], old_pos[1] - blocker["y"])
            new_distance = math.hypot(new_pos[0] - blocker["x"], new_pos[1] - blocker["y"])
            if old_distance <= radius and new_distance >= old_distance:
                continue
            if self._segment_distance_xy(
                old_pos[0],
                old_pos[1],
                new_pos[0],
                new_pos[1],
                blocker["x"],
                blocker["y"],
            ) <= radius:
                return True
        return False

    def _blocked_by_other_drone(self, actor: dict, new_pos: tuple[float, float, float]) -> bool:
        other = self.actor_b if actor is self.actor_a else self.actor_a
        distance = math.sqrt(
            (new_pos[0] - other["x"]) ** 2
            + (new_pos[1] - other["y"]) ** 2
            + (new_pos[2] - other["z"]) ** 2
        )
        return distance < self.drone_collision_radius * 2.0

    def _movement_blocked(
        self,
        actor: dict,
        old_pos: tuple[float, float, float],
        new_pos: tuple[float, float, float],
    ) -> bool:
        return self._blocked_by_obstacle(old_pos, new_pos) or self._blocked_by_other_drone(actor, new_pos)

    def _apply_motion(self, actor: dict, msg: Twist) -> None:
        old_pos = (actor["x"], actor["y"], actor["z"])
        target_pos = (
            actor["x"] + msg.linear.x * self.tick_dt,
            actor["y"] + msg.linear.y * self.tick_dt,
            self._clamp_z(actor["z"] + msg.linear.z * self.tick_dt),
        )
        if self._movement_blocked(actor, old_pos, target_pos):
            slide_candidates = (
                (target_pos[0], old_pos[1], target_pos[2]),
                (old_pos[0], target_pos[1], target_pos[2]),
                (old_pos[0], old_pos[1], target_pos[2]),
                (target_pos[0], old_pos[1], old_pos[2]),
                (old_pos[0], target_pos[1], old_pos[2]),
            )
            for candidate in slide_candidates:
                if not self._movement_blocked(actor, old_pos, candidate):
                    target_pos = candidate
                    break
            else:
                target_pos = old_pos
        actor["x"], actor["y"], actor["z"] = target_pos
        actor["yaw_deg"] += msg.angular.z * 20.0 * self.tick_dt

    def _distance_between_drones(self) -> float:
        return math.sqrt(
            (self.actor_a["x"] - self.actor_b["x"]) ** 2
            + (self.actor_a["y"] - self.actor_b["y"]) ** 2
            + (self.actor_a["z"] - self.actor_b["z"]) ** 2
        )

    def _tag_pause_active(self) -> bool:
        if self.tag_pause_sec < 0.0 and self.tag_latched:
            return True
        return self.tag_paused_until > time.time()

    def _update_tag_pause_state(self) -> None:
        if self.tag_pause_sec == 0.0:
            return

        distance = self._distance_between_drones()
        if self.tag_latched and distance >= self.tag_release_distance:
            self.tag_latched = False

        if self.tag_latched:
            return
        if distance > self.catch_distance:
            return

        self.tag_latched = True
        if self.tag_pause_sec < 0.0:
            self.tag_paused_until = float("inf")
            self.publish_status(
                f"TAG: drones tagged at distance={distance:.1f} cm; pausing forever"
            )
        else:
            self.tag_paused_until = time.time() + self.tag_pause_sec
            self.publish_status(
                f"TAG: drones tagged at distance={distance:.1f} cm; pausing for {self.tag_pause_sec:.1f}s"
            )

    def _sync_actor_location(self, actor: dict) -> None:
        location = str(self.client.request(f"vget /object/{actor['name']}/location")).strip()
        parts = location.split()
        if len(parts) >= 3:
            actor["x"] = float(parts[0])
            actor["y"] = float(parts[1])
            actor["z"] = self._clamp_z(float(parts[2]))

    def _push_actor_location_swept(self, actor: dict) -> bool:
        if not self._swept_move_available:
            return False
        script = (
            "import unreal\n"
            f"target_name = {actor['name']!r}\n"
            "actor = None\n"
            "for candidate in unreal.EditorLevelLibrary.get_all_level_actors():\n"
            "    if candidate.get_name() == target_name or candidate.get_actor_label() == target_name:\n"
            "        actor = candidate\n"
            "        break\n"
            "if actor is None:\n"
            "    raise RuntimeError(f'Actor {target_name} not found')\n"
            f"actor.set_actor_location(unreal.Vector({actor['x']}, {actor['y']}, {actor['z']}), True, False)\n"
        )
        response = self.client.request(f"vrun py exec({script!r})")
        response_text = str(response).strip().lower()
        if response_text.startswith("error"):
            self._swept_move_available = False
            self.publish_status(
                f"UE bridge warning: swept movement unavailable ({response}); falling back to UnrealCV location moves"
            )
            return False
        self._sync_actor_location(actor)
        return True

    def _push_actor_state(self, actor: dict) -> None:
        actor["z"] = self._clamp_z(actor["z"])
        if not self._push_actor_location_swept(actor):
            self.client.request(
                f"vset /object/{actor['name']}/location {actor['x']} {actor['y']} {actor['z']}"
            )
            self._sync_actor_location(actor)
        self.client.request(
            f"vset /object/{actor['name']}/rotation 0 {actor['yaw_deg']} 0"
        )

    def reset_chase_callback(self, msg: String) -> None:
        command = msg.data.strip().lower()
        if command not in {"reset", "reset_chase", "randomize", "randomize_start"}:
            return
        if not self.connected or not self.spawned:
            return
        self._randomize_chase_start()
        try:
            self._push_all_actor_states()
            self._publish_all_poses()
            self.publish_status(
                "Chase start reset: "
                f"DroneA=({self.actor_a['x']:.1f},{self.actor_a['y']:.1f}), "
                f"DroneB=({self.actor_b['x']:.1f},{self.actor_b['y']:.1f}), "
                f"distance_cm={math.hypot(self.actor_a['x'] - self.actor_b['x'], self.actor_a['y'] - self.actor_b['y']):.1f}"
            )
        except Exception as exc:
            self.publish_status(f"UE bridge error: chase reset failed: {exc}")

    def cmd_a_callback(self, msg: Twist) -> None:
        if not self.connected or not self.spawned:
            return
        self._update_tag_pause_state()
        if self._tag_pause_active():
            return
        self._apply_motion(self.actor_a, msg)
        try:
            self._push_actor_state(self.actor_a)
            self._update_tag_pause_state()
        except Exception as exc:
            self.publish_status(f"UE bridge error: DroneA move failed: {exc}")

    def cmd_b_callback(self, msg: Twist) -> None:
        if not self.connected or not self.spawned:
            return
        self._update_tag_pause_state()
        if self._tag_pause_active():
            return
        self._apply_motion(self.actor_b, msg)
        try:
            self._push_actor_state(self.actor_b)
            self._update_tag_pause_state()
        except Exception as exc:
            self.publish_status(f"UE bridge error: DroneB move failed: {exc}")

    def tick(self) -> None:
        if not self.connected:
            if time.time() - self.last_connect_attempt_at >= self.reconnect_interval_sec:
                self.connect_unrealcv()
            return
        if not self.spawned:
            self.spawn_drones_once()
        elif not self.actor_a.get("color_applied") or not self.actor_b.get("color_applied"):
            self._apply_actor_color(self.actor_a)
            self._apply_actor_color(self.actor_b)
        self._update_tag_pause_state()
        self._publish_all_poses()


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


if __name__ == "__main__":
    main()
