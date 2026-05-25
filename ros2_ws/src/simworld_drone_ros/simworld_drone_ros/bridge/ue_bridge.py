import math
import os
import random
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy

from geometry_msgs.msg import PoseStamped
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from std_msgs.msg import String

from simworld_drone_ros.team.match_rules import MatchRules

try:
    import unrealcv
except ImportError:
    unrealcv = None


CONTROL_QOS = QoSProfile(depth=10)
CONTROL_QOS.reliability = ReliabilityPolicy.RELIABLE
CONTROL_QOS.durability = DurabilityPolicy.TRANSIENT_LOCAL


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
        self.control_a_pub = self.create_publisher(String, "/drone_a/control", CONTROL_QOS)
        self.control_b_pub = self.create_publisher(String, "/drone_b/control", CONTROL_QOS)
        self.team_control_pub = self.create_publisher(String, "/team/control", CONTROL_QOS)

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
        self.team_cmd_subs = []
        self.last_connect_attempt_at = 0.0
        self.reconnect_interval_sec = self._read_float_env("SIMWORLD_BRIDGE_RECONNECT_SEC", 2.0)
        self.red_team_size = self._read_int_env("SIM_RED_TEAM_SIZE", 1, 1, 5)
        self.blue_team_size = self._read_int_env("SIM_BLUE_TEAM_SIZE", 1, 1, 5)
        self.team_mode = self.red_team_size > 1 or self.blue_team_size > 1

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
        self.red_team_asset = os.getenv("SIM_RED_TEAM_ASSET", self.drone_a_asset)
        self.blue_team_asset = os.getenv("SIM_BLUE_TEAM_ASSET", self.drone_b_asset)
        self.auto_spawn = os.getenv("SIMWORLD_DRONE_AUTO_SPAWN", "1").lower() not in {"0", "false", "no"}
        self.auto_spawn_team_extras = os.getenv("SIMWORLD_TEAM_AUTO_SPAWN", "1").lower() not in {
            "0",
            "false",
            "no",
        }
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
        self.direct_on_sweep_block = os.getenv("SIMWORLD_DIRECT_ON_SWEEP_BLOCK", "0").lower() not in {
            "0",
            "false",
            "no",
        }
        self._swept_move_available = self.swept_movement
        self.drone_collision_radius = self._read_float_env("SIM_DRONE_COLLISION_RADIUS_CM", 70.0)
        self.obstacle_collision_enabled = (
            os.getenv("SIM_OBSTACLE_COLLISION_ENABLED", "1").lower() not in {"0", "false", "no"}
        )
        self.obstacle_name_patterns = [
            pattern.strip().lower()
            for pattern in os.getenv(
                "SIM_OBSTACLE_NAME_PATTERNS",
                "obstacle,wall,building,barrier,blocker",
            ).split(",")
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
        if self.team_mode and os.getenv("SIM_CHASE_SPAWN_MARGIN") is None:
            self.spawn_margin = max(self.spawn_margin, 450.0)
        self.arena_boundary_collision_enabled = os.getenv(
            "SIM_ARENA_BOUNDARY_COLLISION_ENABLED",
            "1",
        ).lower() not in {
            "0",
            "false",
            "no",
        }
        self.arena_boundary_margin = max(
            0.0,
            self._read_float_env("SIM_ARENA_BOUNDARY_MARGIN_CM", self.drone_collision_radius),
        )
        self.catch_distance = self._read_float_env("SIM_CATCH_DISTANCE", 160.0)
        raw_team_catch_mode = os.getenv("SIM_TEAM_CATCH_MODE", "primary").strip().lower()
        self.team_catch_mode = MatchRules.normalize_catch_mode(raw_team_catch_mode)
        if self.team_catch_mode != raw_team_catch_mode:
            self.get_logger().warning(
                f"Invalid SIM_TEAM_CATCH_MODE value '{raw_team_catch_mode}', using primary"
            )
        raw_team_round_mode = os.getenv("SIM_TEAM_ROUND_MODE", "tag").strip().lower()
        self.team_round_mode = MatchRules.normalize_round_mode(raw_team_round_mode)
        if self.team_round_mode != raw_team_round_mode:
            self.get_logger().warning(
                f"Invalid SIM_TEAM_ROUND_MODE value '{raw_team_round_mode}', using tag"
            )
        self.match_rules = MatchRules(self.team_mode, self.team_catch_mode, self.team_round_mode)
        self.ignore_duel_primary_cmds = os.getenv(
            "SIM_TEAM_IGNORE_DUEL_PRIMARY_CMDS",
            "0",
        ).lower() not in {
            "0",
            "false",
            "no",
        }
        self.eliminated_actor_ids: set[str] = set()
        self.elimination_ground_z = self._read_float_env("SIM_TEAM_ELIMINATION_GROUND_Z", 0.0)
        self.elimination_grace_sec = max(0.0, self._read_float_env("SIM_TEAM_ELIMINATION_GRACE_SEC", 3.0))
        self.primary_elimination_resets = os.getenv("SIM_TEAM_PRIMARY_ELIMINATION_RESETS", "0").lower() not in {
            "0",
            "false",
            "no",
        }
        self.round_started_at = time.time()
        self.tag_pause_sec = self._read_float_env("SIM_TAG_PAUSE_SEC", 0.0)
        self.tag_release_distance = self._read_float_env(
            "SIM_TAG_RELEASE_DISTANCE",
            max(self.catch_distance * 1.2, self.catch_distance + 25.0),
        )
        self.tag_paused_until = 0.0
        self.tag_latched = False
        default_min_start_distance = max(700.0, self.catch_distance * 4.0)
        if self.team_mode:
            default_min_start_distance = max(1800.0, self.catch_distance * 8.0)
        self.min_start_distance = self._read_float_env(
            "SIM_CHASE_MIN_START_DISTANCE",
            default_min_start_distance,
        )
        self.park_inactive_drones = os.getenv("SIM_INACTIVE_DRONE_PARK_ENABLED", "1").lower() not in {
            "0",
            "false",
            "no",
        }
        self.inactive_park_x = self._read_float_env("SIM_INACTIVE_DRONE_PARK_X", 2800.0)
        self.inactive_park_y = self._read_float_env("SIM_INACTIVE_DRONE_PARK_Y", 2800.0)
        self.inactive_park_z = self._clamp_z(self._read_float_env("SIM_INACTIVE_DRONE_PARK_Z", 150.0))
        self.inactive_park_spacing = self._read_float_env("SIM_INACTIVE_DRONE_PARK_SPACING", 160.0)
        self.spawn_rng = random.Random(int(self._read_float_env("SIM_CHASE_RANDOM_SEED", random.randrange(1, 2**31))))

        default_y = self._read_float_env("SIMWORLD_DRONE_Y", 0.0)
        default_z = self._clamp_z(self._read_float_env("SIMWORLD_DRONE_Z", 600.0))
        self.start_z = self._clamp_z(self._read_float_env("SIM_CHASE_START_Z", default_z))
        default_yaw = self._read_float_env("SIMWORLD_DRONE_YAW", 0.0)

        self.actor_a = {
            "id": "red_1",
            "team": "red",
            "index": 1,
            "label": "DroneA",
            "name": os.getenv("SIMWORLD_DRONE_A_NAME", "DroneA"),
            "x": self._read_float_env("SIMWORLD_DRONE_A_X", 600.0),
            "y": self._read_float_env("SIMWORLD_DRONE_A_Y", default_y),
            "z": self._clamp_z(self._read_float_env("SIMWORLD_DRONE_A_Z", default_z)),
            "yaw_deg": self._read_float_env("SIMWORLD_DRONE_A_YAW", default_yaw),
            "asset": self.drone_a_asset,
            "scale": self._read_scale_env("SIMWORLD_DRONE_A_SCALE", [0.7, 0.7, 0.08]),
            "color": self._read_color_env("SIMWORLD_DRONE_A_COLOR", [255, 50, 50]),
            "color_applied": False,
            "vx": 0.0,
            "vy": 0.0,
            "vz": 0.0,
        }
        self.actor_b = {
            "id": "blue_1",
            "team": "blue",
            "index": 1,
            "label": "DroneB",
            "name": os.getenv("SIMWORLD_DRONE_B_NAME", "DroneB"),
            "x": self._read_float_env("SIMWORLD_DRONE_B_X", -600.0),
            "y": self._read_float_env("SIMWORLD_DRONE_B_Y", default_y),
            "z": self._clamp_z(self._read_float_env("SIMWORLD_DRONE_B_Z", default_z)),
            "yaw_deg": self._read_float_env("SIMWORLD_DRONE_B_YAW", default_yaw),
            "asset": self.drone_b_asset,
            "scale": self._read_scale_env("SIMWORLD_DRONE_B_SCALE", [0.7, 0.7, 0.08]),
            "color": self._read_color_env("SIMWORLD_DRONE_B_COLOR", [245, 245, 245]),
            "color_applied": False,
            "vx": 0.0,
            "vy": 0.0,
            "vz": 0.0,
        }
        self.actors = [self.actor_a, self.actor_b]
        self.actors.extend(
            self._make_team_extra_actor("red", index, default_y, default_z, default_yaw)
            for index in range(2, self.red_team_size + 1)
        )
        self.actors.extend(
            self._make_team_extra_actor("blue", index, default_y, default_z, default_yaw)
            for index in range(2, self.blue_team_size + 1)
        )
        self.inactive_existing_actors = self._make_inactive_existing_actors(default_yaw)
        self._configure_team_topics()

        self.timer = self.create_timer(self.tick_dt, self.tick)
        self.connect_unrealcv()
        self.publish_status(
            "UE bridge movement config: "
            f"ignore_duel_primary={int(self.ignore_duel_primary_cmds)} "
            f"sweep={int(self.swept_movement)} direct_on_sweep_block={int(self.direct_on_sweep_block)} "
            f"round={self.team_round_mode} catch_mode={self.match_rules.scoring_mode}"
        )
        self.publish_status(
            "UE bridge arena guard: "
            f"enabled={int(self.arena_boundary_collision_enabled)} "
            f"bounds=({self.spawn_bound_x:.1f},{self.spawn_bound_y:.1f}) "
            f"margin={self.arena_boundary_margin:.1f} "
            f"elimination_ground_z={self.elimination_ground_z:.1f}"
        )

    def _read_int_env(self, name: str, default: int, minimum: int, maximum: int) -> int:
        value = os.getenv(name)
        if value is None:
            return default
        try:
            number = int(float(value))
        except ValueError:
            self.get_logger().warning(f"Invalid {name} value '{value}', using default {default}")
            return default
        return max(minimum, min(maximum, number))

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

    def _team_env_prefix(self, team: str, index: int) -> str:
        return f"SIM_{team.upper()}_{index}_"

    def _make_team_extra_actor(
        self,
        team: str,
        index: int,
        default_y: float,
        default_z: float,
        default_yaw: float,
    ) -> dict:
        prefix = self._team_env_prefix(team, index)
        side = 1.0 if team == "red" else -1.0
        asset = self.red_team_asset if team == "red" else self.blue_team_asset
        default_color = [255, 95, 95] if team == "red" else [220, 245, 255]
        default_name = f"{'DroneA' if team == 'red' else 'DroneB'}{index - 1}"
        return {
            "id": f"{team}_{index}",
            "team": team,
            "index": index,
            "label": f"{team.title()}{index}",
            "name": os.getenv(prefix + "NAME", default_name),
            "x": self._read_float_env(prefix + "X", side * (600.0 + index * 120.0)),
            "y": self._read_float_env(prefix + "Y", default_y + (index - 1) * 180.0),
            "z": self._clamp_z(self._read_float_env(prefix + "Z", default_z)),
            "yaw_deg": self._read_float_env(prefix + "YAW", default_yaw),
            "asset": os.getenv(prefix + "ASSET", asset),
            "scale": self._read_scale_env(prefix + "SCALE", [0.7, 0.7, 0.08]),
            "color": self._read_color_env(prefix + "COLOR", default_color),
            "color_applied": False,
            "vx": 0.0,
            "vy": 0.0,
            "vz": 0.0,
        }

    def _manual_drone_name(self, team: str, index: int) -> str:
        if index == 1:
            env_name = "SIMWORLD_DRONE_A_NAME" if team == "red" else "SIMWORLD_DRONE_B_NAME"
            default_name = "DroneA" if team == "red" else "DroneB"
            return os.getenv(env_name, default_name)
        prefix = self._team_env_prefix(team, index)
        default_name = f"{'DroneA' if team == 'red' else 'DroneB'}{index - 1}"
        return os.getenv(prefix + "NAME", default_name)

    def _make_inactive_existing_actors(self, default_yaw: float) -> list[dict]:
        active_names = {actor["name"] for actor in self.actors}
        inactive = []
        for team, active_count, color in (
            ("red", self.red_team_size, [130, 45, 45]),
            ("blue", self.blue_team_size, [110, 125, 135]),
        ):
            for index in range(active_count + 1, 6):
                name = self._manual_drone_name(team, index)
                if name in active_names:
                    continue
                inactive.append(
                    {
                        "id": f"{team}_{index}",
                        "team": team,
                        "index": index,
                        "label": f"Inactive{team.title()}{index}",
                        "name": name,
                        "x": self.inactive_park_x,
                        "y": self.inactive_park_y,
                        "z": self.inactive_park_z,
                        "yaw_deg": default_yaw,
                        "color": color,
                        "color_applied": False,
                        "vx": 0.0,
                        "vy": 0.0,
                        "vz": 0.0,
                    }
                )
        return inactive

    def _configure_team_topics(self) -> None:
        for actor in self.actors:
            team = actor["team"]
            drone_id = actor["id"]
            actor["team_pose_pub"] = self.create_publisher(
                PoseStamped,
                f"/team/{team}/{drone_id}/pose",
                10,
            )
            actor["team_odom_pub"] = self.create_publisher(
                Odometry,
                f"/team/{team}/{drone_id}/odom",
                10,
            )
            self.team_cmd_subs.append(
                self.create_subscription(
                    Twist,
                    f"/team/{team}/{drone_id}/cmd_vel",
                    lambda msg, selected=actor: self.cmd_actor_callback(selected, msg, source="team"),
                    10,
                )
            )

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

    def _actor_z_for_push(self, actor: dict) -> float:
        if actor["id"] in self.eliminated_actor_ids:
            return float(self.elimination_ground_z)
        return self._clamp_z(actor["z"])

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

        drone_names = {actor["name"].lower() for actor in self.actors + self.inactive_existing_actors}
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

        red_heading = self.spawn_rng.uniform(0.0, math.tau)
        blue_heading = red_heading + math.pi
        self._place_team("red", ax, ay, red_heading)
        self._place_team("blue", bx, by, blue_heading)
        self.tag_paused_until = 0.0
        self.tag_latched = False
        self.eliminated_actor_ids.clear()
        for actor in self.actors:
            actor["vx"] = 0.0
            actor["vy"] = 0.0
            actor["vz"] = 0.0
        self.round_started_at = time.time()

    def _team_actors(self, team: str) -> list[dict]:
        return [actor for actor in self.actors if actor["team"] == team]

    def _formation_offsets(self, count: int) -> list[tuple[float, float]]:
        spacing = self._read_float_env("SIM_TEAM_SPAWN_SPACING_CM", 220.0)
        if count <= 1:
            return [(0.0, 0.0)]
        if count == 2:
            return [(0.0, -spacing * 0.5), (0.0, spacing * 0.5)]
        offsets = [(0.0, 0.0)]
        rows = [
            (-spacing * 0.55, spacing * 0.75),
            (-spacing * 0.55, -spacing * 0.75),
            (-spacing * 1.25, spacing * 0.38),
            (-spacing * 1.25, -spacing * 0.38),
        ]
        return offsets + rows[: count - 1]

    def _bounded_xy(self, x: float, y: float) -> tuple[float, float]:
        max_x = max(0.0, self.spawn_bound_x - self.spawn_margin)
        max_y = max(0.0, self.spawn_bound_y - self.spawn_margin)
        return max(-max_x, min(max_x, x)), max(-max_y, min(max_y, y))

    def _bounded_motion_xy(self, x: float, y: float) -> tuple[float, float]:
        max_x = max(0.0, self.spawn_bound_x - self.arena_boundary_margin)
        max_y = max(0.0, self.spawn_bound_y - self.arena_boundary_margin)
        return max(-max_x, min(max_x, x)), max(-max_y, min(max_y, y))

    def _place_team(self, team: str, anchor_x: float, anchor_y: float, heading_rad: float) -> None:
        actors = self._team_actors(team)
        cos_h = math.cos(heading_rad)
        sin_h = math.sin(heading_rad)
        for actor, (forward, lateral) in zip(actors, self._formation_offsets(len(actors))):
            x = anchor_x + forward * cos_h - lateral * sin_h
            y = anchor_y + forward * sin_h + lateral * cos_h
            actor["x"], actor["y"] = self._bounded_xy(x, y)
            actor["yaw_deg"] = math.degrees(heading_rad)
            actor["z"] = self.start_z

    def _inactive_park_position(self, slot: int) -> tuple[float, float, float]:
        columns = 3
        row = slot // columns
        column = slot % columns
        return (
            self.inactive_park_x + column * self.inactive_park_spacing,
            self.inactive_park_y + row * self.inactive_park_spacing,
            self.inactive_park_z,
        )

    def _park_inactive_existing_drones(self) -> None:
        if not self.park_inactive_drones or not self.inactive_existing_actors:
            return
        try:
            objects = set(str(self.client.request("vget /objects")).split())
        except Exception as exc:
            self.get_logger().warning(f"Inactive drone parking skipped: {exc}")
            return

        parked = []
        for slot, actor in enumerate(self.inactive_existing_actors):
            if actor["name"] not in objects:
                continue
            actor["x"], actor["y"], actor["z"] = self._inactive_park_position(slot)
            try:
                self.client.request(
                    f"vset /object/{actor['name']}/location {actor['x']} {actor['y']} {actor['z']}"
                )
                self.client.request(f"vset /object/{actor['name']}/rotation 0 {actor['yaw_deg']} 0")
                self._apply_actor_color(actor)
                parked.append(actor["name"])
            except Exception as exc:
                self.get_logger().warning(f"Inactive drone parking skipped {actor['name']}: {exc}")
        if parked:
            self.publish_status(
                "Inactive manual drones parked: "
                + ",".join(parked)
                + f" at x={self.inactive_park_x:.0f}, y={self.inactive_park_y:.0f}"
            )

    def _push_all_actor_states(self) -> None:
        for actor in self.actors:
            self._push_actor_state(actor)
        self._park_inactive_existing_drones()

    def _publish_all_poses(self) -> None:
        self._publish_pose(self.actor_a, self.pose_a_pub, "drone_a")
        self._publish_pose(self.actor_a, self.legacy_pose_pub, "drone")
        self._publish_pose(self.actor_b, self.pose_b_pub, "drone_b")
        self._publish_odom(self.actor_a, self.odom_a_pub, "drone_a")
        self._publish_odom(self.actor_a, self.legacy_odom_pub, "drone")
        self._publish_odom(self.actor_b, self.odom_b_pub, "drone_b")
        for actor in self.actors:
            self._publish_pose(actor, actor["team_pose_pub"], actor["id"])
            self._publish_odom(actor, actor["team_odom_pub"], actor["id"])

    def publish_status(self, text: str) -> None:
        msg = String()
        msg.data = text
        self.status_pub.publish(msg)
        self.legacy_status_pub.publish(msg)
        self.get_logger().info(text)

    def _publish_control_command(self, command: str) -> None:
        msg = String()
        msg.data = command
        self.control_a_pub.publish(msg)
        self.control_b_pub.publish(msg)
        self.team_control_pub.publish(msg)

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
                for actor in self.actors:
                    self._adopt_existing_actor(actor, actor["label"])
            elif self.auto_spawn:
                for actor in self.actors:
                    self._spawn_named_actor(actor, actor["label"])
            else:
                return
            self._park_inactive_existing_drones()
            self._refresh_collision_blockers()
            self._randomize_chase_start()
            self._push_all_actor_states()
            self.spawned = True
            self._publish_all_poses()
            self.publish_status(
                "Chase start reset: "
                f"DroneA=({self.actor_a['x']:.1f},{self.actor_a['y']:.1f}), "
                f"DroneB=({self.actor_b['x']:.1f},{self.actor_b['y']:.1f}), "
                f"distance_cm={self._primary_pair_distance():.1f}, "
                f"scoring_distance_cm={self._nearest_opposing_pair()[0]:.1f}, "
                f"teams=red:{len(self._team_actors('red'))} blue:{len(self._team_actors('blue'))}, "
                f"catch_mode={self.match_rules.scoring_mode}"
            )
            if self.team_mode:
                self.publish_status(
                    "Team bridge ready: "
                    f"red={','.join(actor['name'] for actor in self._team_actors('red'))}; "
                    f"blue={','.join(actor['name'] for actor in self._team_actors('blue'))}; "
                    f"catch_mode={self.match_rules.scoring_mode}; "
                    f"round_mode={self.team_round_mode}"
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
        msg.twist.twist.linear.x = actor.get("vx", 0.0)
        msg.twist.twist.linear.y = actor.get("vy", 0.0)
        msg.twist.twist.linear.z = actor.get("vz", 0.0)
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
        for other in self.actors:
            if other is actor:
                continue
            if other["id"] in self.eliminated_actor_ids:
                continue
            distance = math.sqrt(
                (new_pos[0] - other["x"]) ** 2
                + (new_pos[1] - other["y"]) ** 2
                + (new_pos[2] - other["z"]) ** 2
            )
            if distance < self.drone_collision_radius * 2.0:
                return True
        return False

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
        if self.arena_boundary_collision_enabled:
            bounded_x, bounded_y = self._bounded_motion_xy(target_pos[0], target_pos[1])
            target_pos = (bounded_x, bounded_y, target_pos[2])
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
        actor["_last_requested_pos"] = target_pos
        actor["_last_motion_old_pos"] = old_pos
        actor["vx"] = (target_pos[0] - old_pos[0]) / max(self.tick_dt, 1e-3)
        actor["vy"] = (target_pos[1] - old_pos[1]) / max(self.tick_dt, 1e-3)
        actor["vz"] = (target_pos[2] - old_pos[2]) / max(self.tick_dt, 1e-3)
        actor["x"], actor["y"], actor["z"] = target_pos
        actor["yaw_deg"] += msg.angular.z * 20.0 * self.tick_dt

    def _nearest_opposing_pair(self) -> tuple[float, dict, dict]:
        contact = self.match_rules.scoring_contact(
            self.actors,
            self.actor_a,
            self.actor_b,
            excluded_ids=self.eliminated_actor_ids,
        )
        red = next((actor for actor in self.actors if actor["id"] == contact.red_id), self.actor_a)
        blue = next((actor for actor in self.actors if actor["id"] == contact.blue_id), self.actor_b)
        return contact.distance_cm, red, blue

    def _primary_pair_distance(self) -> float:
        return self.match_rules.distance(self.actor_a, self.actor_b)

    def _distance_between_drones(self) -> float:
        return self._nearest_opposing_pair()[0]

    def _tag_pause_active(self) -> bool:
        if self.tag_pause_sec < 0.0 and self.tag_latched:
            return True
        return self.tag_paused_until > time.time()

    def _elimination_active(self) -> bool:
        return self.team_mode and self.team_round_mode == "red_elimination"

    def _active_red_actors(self) -> list[dict]:
        return [
            actor
            for actor in self._team_actors("red")
            if actor["id"] not in self.eliminated_actor_ids
        ]

    def _eliminate_actor(self, actor: dict, caught_by: dict, distance: float) -> None:
        if actor["id"] in self.eliminated_actor_ids:
            return
        self.eliminated_actor_ids.add(actor["id"])
        actor["z"] = self.elimination_ground_z
        self._push_actor_state(actor)
        self.publish_status(
            f"Team elimination: {actor['id']} caught by {caught_by['id']} "
            f"at {distance:.1f} cm; dropped to z={self.elimination_ground_z:.1f}"
        )

    def _reset_after_elimination_round(self) -> None:
        self.publish_status("Team elimination round complete: all red drones caught; resetting")
        self._publish_control_command("stop_all")
        self._randomize_chase_start()
        self._push_all_actor_states()
        self._publish_all_poses()
        self._publish_control_command("start_all")
        self.publish_status(
            "Chase start reset: "
            f"DroneA=({self.actor_a['x']:.1f},{self.actor_a['y']:.1f}), "
            f"DroneB=({self.actor_b['x']:.1f},{self.actor_b['y']:.1f}), "
            f"distance_cm={self._primary_pair_distance():.1f}, "
            f"scoring_distance_cm={self._nearest_opposing_pair()[0]:.1f}, "
            f"teams=red:{len(self._team_actors('red'))} blue:{len(self._team_actors('blue'))}, "
            f"catch_mode={self.match_rules.scoring_mode}"
        )

    def _update_tag_pause_state(self) -> None:
        distance, red, blue = self._nearest_opposing_pair()
        if self._elimination_active():
            if time.time() - self.round_started_at < self.elimination_grace_sec:
                return
            if distance > self.catch_distance:
                return
            self._eliminate_actor(red, blue, distance)
            if self.primary_elimination_resets and red["id"] == "red_1":
                self.publish_status("Team elimination primary runner caught; resetting round")
                self._reset_after_elimination_round()
            elif not self._active_red_actors():
                self._reset_after_elimination_round()
            else:
                remaining = ",".join(actor["id"] for actor in self._active_red_actors())
                self.publish_status(f"Team elimination continues: remaining_red={remaining}")
            return

        if self.tag_latched and distance >= self.tag_release_distance:
            self.tag_latched = False

        if self.tag_latched:
            return
        if distance > self.catch_distance:
            return

        self.tag_latched = True
        if self.tag_pause_sec == 0.0:
            self.publish_status(
                f"Bridge catch zone reached: red={red['id']} blue={blue['id']} distance={distance:.1f}"
            )
            return
        if self.tag_pause_sec < 0.0:
            self.tag_paused_until = float("inf")
            self.publish_status(
                f"Bridge catch zone reached: red={red['id']} blue={blue['id']} distance={distance:.1f}; pausing forever"
            )
        else:
            self.tag_paused_until = time.time() + self.tag_pause_sec
            self.publish_status(
                f"Bridge catch zone reached: red={red['id']} blue={blue['id']} distance={distance:.1f}; pausing for {self.tag_pause_sec:.1f}s"
            )

    def _sync_actor_location(self, actor: dict) -> None:
        location = str(self.client.request(f"vget /object/{actor['name']}/location")).strip()
        parts = location.split()
        if len(parts) >= 3:
            actor["x"] = float(parts[0])
            actor["y"] = float(parts[1])
            z = float(parts[2])
            actor["z"] = z if actor["id"] in self.eliminated_actor_ids else self._clamp_z(z)

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
        requested = actor.get("_last_requested_pos")
        old_pos = actor.get("_last_motion_old_pos")
        if requested is not None and old_pos is not None:
            requested_step = math.sqrt(
                (requested[0] - old_pos[0]) ** 2
                + (requested[1] - old_pos[1]) ** 2
                + (requested[2] - old_pos[2]) ** 2
            )
            actual_step = math.sqrt(
                (actor["x"] - old_pos[0]) ** 2
                + (actor["y"] - old_pos[1]) ** 2
                + (actor["z"] - old_pos[2]) ** 2
            )
            if self.direct_on_sweep_block and requested_step > 1.0 and actual_step < requested_step * 0.2:
                actor["x"], actor["y"], actor["z"] = requested
                self.client.request(
                    f"vset /object/{actor['name']}/location {actor['x']} {actor['y']} {actor['z']}"
                )
                self._sync_actor_location(actor)
        return True

    def _push_actor_state(self, actor: dict) -> None:
        old_pos = actor.get("_last_motion_old_pos")
        actor["z"] = self._actor_z_for_push(actor)
        if not self._push_actor_location_swept(actor):
            self.client.request(
                f"vset /object/{actor['name']}/location {actor['x']} {actor['y']} {actor['z']}"
            )
            self._sync_actor_location(actor)
        if old_pos is not None:
            actor["vx"] = (actor["x"] - old_pos[0]) / max(self.tick_dt, 1e-3)
            actor["vy"] = (actor["y"] - old_pos[1]) / max(self.tick_dt, 1e-3)
            actor["vz"] = (actor["z"] - old_pos[2]) / max(self.tick_dt, 1e-3)
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
                f"distance_cm={self._primary_pair_distance():.1f}, "
                f"scoring_distance_cm={self._nearest_opposing_pair()[0]:.1f}, "
                f"teams=red:{len(self._team_actors('red'))} blue:{len(self._team_actors('blue'))}, "
                f"catch_mode={self.match_rules.scoring_mode}"
            )
        except Exception as exc:
            self.publish_status(f"UE bridge error: chase reset failed: {exc}")

    def cmd_a_callback(self, msg: Twist) -> None:
        self.cmd_actor_callback(self.actor_a, msg, source="duel")

    def cmd_b_callback(self, msg: Twist) -> None:
        self.cmd_actor_callback(self.actor_b, msg, source="duel")

    def cmd_actor_callback(self, actor: dict, msg: Twist, source: str = "team") -> None:
        if not self.connected or not self.spawned:
            return
        if source == "duel" and self.ignore_duel_primary_cmds and actor["id"] in {"red_1", "blue_1"}:
            return
        if actor["id"] in self.eliminated_actor_ids:
            actor["z"] = self.elimination_ground_z
            try:
                self._push_actor_state(actor)
            except Exception as exc:
                self.publish_status(f"UE bridge error: eliminated {actor['label']} move hold failed: {exc}")
            return
        self._update_tag_pause_state()
        if self._tag_pause_active():
            return
        self._apply_motion(actor, msg)
        try:
            self._push_actor_state(actor)
            self._update_tag_pause_state()
        except Exception as exc:
            self.publish_status(f"UE bridge error: {actor['label']} move failed: {exc}")

    def tick(self) -> None:
        if not self.connected:
            if time.time() - self.last_connect_attempt_at >= self.reconnect_interval_sec:
                self.connect_unrealcv()
            return
        if not self.spawned:
            self.spawn_drones_once()
        else:
            for actor in self.actors:
                if not actor.get("color_applied"):
                    self._apply_actor_color(actor)
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
