from __future__ import annotations

import json
import math
import os
import time

import rclpy
from geometry_msgs.msg import PoseStamped, Twist
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String

from simworld_drone_ros.team.models import TeamDrone, build_team, read_team_speed_profile
from simworld_drone_ros.team.tactical_geometry import (
    cover_point,
    first_blocking_blocker,
    line_of_sight_clear,
    read_tactical_blockers,
    route_around_blockers,
    segment_distance_xy,
)


CONTROL_QOS = QoSProfile(depth=10)
CONTROL_QOS.reliability = ReliabilityPolicy.RELIABLE
CONTROL_QOS.durability = DurabilityPolicy.TRANSIENT_LOCAL


class TeamDroneController(Node):
    """Controls non-primary drones in a configured team-vs-team match.

    The existing duel brains still control red_1/DroneA and blue_1/DroneB.
    This node drives non-primary support drones so team mode is visible without
    replacing the stable one-vs-one brains yet.
    """

    def __init__(self) -> None:
        self.team_scope = os.environ.get("SIM_TEAM", "all").strip().lower()
        if self.team_scope not in {"all", "red", "blue"}:
            self.team_scope = "all"
        node_name = "team_drone_controller" if self.team_scope == "all" else f"{self.team_scope}_team_drone_controller"
        super().__init__(node_name)
        self.status_pub = self.create_publisher(String, "/sim/status", 20)
        self.control_subs = [
            self.create_subscription(String, "/team/control", self.control_callback, CONTROL_QOS),
            self.create_subscription(String, "/drone_a/control", self.control_callback, CONTROL_QOS),
            self.create_subscription(String, "/drone_b/control", self.control_callback, CONTROL_QOS),
        ]

        self.red_drones = build_team("red")
        self.blue_drones = build_team("blue")
        if self.team_scope == "red":
            self.drones = self.red_drones
        elif self.team_scope == "blue":
            self.drones = self.blue_drones
        else:
            self.drones = self.red_drones + self.blue_drones
        self.red_profile = read_team_speed_profile("red")
        self.blue_profile = read_team_speed_profile("blue")
        self.blue_support_speed_scale = self._read_float_env("SIM_BLUE_SUPPORT_SPEED_SCALE", 1.18)
        self.control_primaries = self._read_bool_env("SIM_TEAM_CONTROL_PRIMARIES", False)
        self.tick_dt = self._read_float_env("SIM_TEAM_CONTROLLER_DT", 0.1)
        self.min_z = self._read_float_env("SIMWORLD_DRONE_MIN_Z", self._read_float_env("SIM_DRONE_MIN_Z", 100.0))
        self.max_z = self._read_float_env("SIMWORLD_DRONE_MAX_Z", self._read_float_env("SIM_DRONE_MAX_Z", 700.0))
        if self.min_z > self.max_z:
            self.min_z, self.max_z = self.max_z, self.min_z
        self.vertical_speed = self._read_float_env("SIM_TEAM_VERTICAL_SPEED", 220.0)
        self.arrive_radius = self._read_float_env("SIM_TEAM_ARRIVE_RADIUS_CM", 120.0)
        self.spacing = self._read_float_env("SIM_TEAM_FORMATION_SPACING_CM", 320.0)
        self.min_team_separation = self._read_float_env("SIM_TEAM_MIN_SEPARATION_CM", 520.0)
        self.bounds_x = self._read_float_env("SIM_TARGET_BOUND_X", 1800.0)
        self.bounds_y = self._read_float_env("SIM_TARGET_BOUND_Y", 1800.0)
        self.bound_margin = self._read_float_env("SIM_TEAM_BOUND_MARGIN_CM", 120.0)
        self.screen_distance = self._read_float_env("SIM_TEAM_SCREEN_DISTANCE_CM", 650.0)
        self.screen_lateral = self._read_float_env("SIM_TEAM_SCREEN_LATERAL_CM", 380.0)
        self.decoy_distance = self._read_float_env("SIM_TEAM_DECOY_DISTANCE_CM", 980.0)
        self.red_escape_distance = self._read_float_env("SIM_TEAM_RED_ESCAPE_DISTANCE_CM", 1450.0)
        self.flank_distance = self._read_float_env("SIM_TEAM_FLANK_DISTANCE_CM", 760.0)
        self.cutoff_distance = self._read_float_env("SIM_TEAM_CUTOFF_DISTANCE_CM", 860.0)
        self.screen_hunt_distance = self._read_float_env("SIM_TEAM_SCREEN_HUNT_DISTANCE_CM", 2600.0)
        self.search_radius = self._read_float_env("SIM_TEAM_SEARCH_RADIUS_CM", 950.0)
        self.search_forward = self._read_float_env("SIM_TEAM_SEARCH_FORWARD_CM", 620.0)
        self.tactical_clearance = self._read_float_env("SIM_TACTICAL_CLEARANCE_CM", 180.0)
        self.min_enemy_separation = self._read_float_env(
            "SIM_TEAM_MIN_ENEMY_SEPARATION_CM",
            self._read_float_env("SIM_CATCH_DISTANCE", 160.0) + 210.0,
        )
        self.blockers = read_tactical_blockers(self.min_z, self.max_z)
        self.started = self._read_bool_env("SIM_TEAM_START_ACTIVE", False)
        self.poses: dict[str, tuple[float, float, float, float]] = {}
        self.roles: dict[str, str] = {}
        self.intent: dict[str, str] = {}
        self.pose_subs = []
        self.role_subs = []
        self.cmd_pubs: dict[str, object] = {}
        self.last_status_at = 0.0

        for drone in self.red_drones + self.blue_drones:
            self.pose_subs.append(
                self.create_subscription(
                    PoseStamped,
                    drone.pose_topic,
                    lambda msg, selected=drone: self.pose_callback(selected, msg),
                    10,
                )
            )

        for drone in self.drones:
            self.role_subs.append(
                self.create_subscription(
                    String,
                    drone.role_topic,
                    lambda msg, selected=drone: self.role_callback(selected, msg),
                    10,
                )
            )
            if self._controls_drone(drone):
                self.cmd_pubs[drone.name] = self.create_publisher(Twist, drone.cmd_topic, 10)

        self.timer = self.create_timer(self.tick_dt, self.control_loop)
        self.publish_status(
            "Team support ready: "
            f"scope={self.team_scope} red={len(self.red_drones)} blue={len(self.blue_drones)} "
            f"controlled={','.join(self.cmd_pubs) if self.cmd_pubs else 'none'} "
            f"pose_watch={len(self.red_drones) + len(self.blue_drones)} "
            f"tactical_blockers={len(self.blockers)} "
            f"started={int(self.started)}"
        )

    def _read_float_env(self, name: str, default: float) -> float:
        value = os.environ.get(name)
        if value is None:
            return default
        try:
            return float(value)
        except ValueError:
            return default

    def _read_bool_env(self, name: str, default: bool) -> bool:
        value = os.environ.get(name)
        if value is None:
            return default
        return value.lower() not in {"0", "false", "no"}

    def _controls_drone(self, drone: TeamDrone) -> bool:
        return self.control_primaries or not drone.name.endswith("_1")

    def publish_status(self, text: str) -> None:
        msg = String()
        msg.data = text
        self.status_pub.publish(msg)
        self.get_logger().info(text)

    def pose_callback(self, drone: TeamDrone, msg: PoseStamped) -> None:
        self.poses[drone.name] = (
            msg.pose.position.x,
            msg.pose.position.y,
            self._clamp_z(msg.pose.position.z),
            time.time(),
        )

    def role_callback(self, drone: TeamDrone, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
            role = str(payload.get("role", "")).strip()
        except (json.JSONDecodeError, AttributeError):
            role = msg.data.strip()
        if role:
            self.roles[drone.name] = role

    def control_callback(self, msg: String) -> None:
        command = msg.data.strip().lower()
        if command in {"start", "start_all", "start_team"}:
            already_started = self.started
            self.started = True
            if not already_started:
                self.publish_status("Team support received START")
        elif command in {"stop", "stop_all", "stop_team"}:
            was_started = self.started
            self.started = False
            self._publish_zero_all()
            if was_started:
                self.publish_status("Team support received STOP")

    def _publish_zero_all(self) -> None:
        for pub in self.cmd_pubs.values():
            try:
                pub.publish(Twist())
            except Exception:
                return

    def _clamp_z(self, z: float) -> float:
        return max(self.min_z, min(self.max_z, float(z)))

    def _pose(self, name: str) -> tuple[float, float, float] | None:
        pose = self.poses.get(name)
        if pose is None:
            return None
        return pose[0], pose[1], pose[2]

    def _nearest_enemy(self, drone: TeamDrone) -> tuple[str, tuple[float, float, float]] | None:
        own_pose = self._pose(drone.name)
        if own_pose is None:
            return None
        return self._nearest_enemy_to_pose(drone.team, own_pose)

    def _nearest_enemy_to_pose(
        self,
        team: str,
        pose: tuple[float, float, float],
    ) -> tuple[str, tuple[float, float, float]] | None:
        enemies = self.blue_drones if team == "red" else self.red_drones
        best = None
        best_distance = float("inf")
        for enemy in enemies:
            enemy_pose = self._pose(enemy.name)
            if enemy_pose is None:
                continue
            distance = self._distance(pose, enemy_pose)
            if distance < best_distance:
                best_distance = distance
                best = (enemy.name, enemy_pose)
        return best

    def _primary_pose(self, team: str) -> tuple[float, float, float] | None:
        return self._pose(f"{team}_1")

    def _distance(self, a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
        return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)

    def _normalize_xy(self, x: float, y: float) -> tuple[float, float]:
        length = math.hypot(x, y)
        if length <= 1e-6:
            return 1.0, 0.0
        return x / length, y / length

    def _bounded_xy(self, x: float, y: float) -> tuple[float, float]:
        max_x = max(0.0, self.bounds_x - self.bound_margin)
        max_y = max(0.0, self.bounds_y - self.bound_margin)
        return max(-max_x, min(max_x, x)), max(-max_y, min(max_y, y))

    def _route_xy(
        self,
        own: tuple[float, float, float],
        desired_x: float,
        desired_y: float,
    ) -> tuple[float, float, str | None]:
        x, y, route_reason = route_around_blockers(
            own,
            (desired_x, desired_y),
            self.blockers,
            self.tactical_clearance,
        )
        bounded_x, bounded_y = self._bounded_xy(x, y)
        return bounded_x, bounded_y, route_reason

    def _los_clear(self, first: tuple[float, float, float], second: tuple[float, float, float]) -> bool:
        return line_of_sight_clear(first, second, self.blockers, self.tactical_clearance)

    def _blocking_line_reason(
        self,
        first: tuple[float, float, float],
        second: tuple[float, float, float],
    ) -> str | None:
        blocker = first_blocking_blocker(first, second, self.blockers, self.tactical_clearance)
        if blocker is None:
            return None
        return f"blocked by {blocker.name}"

    def _avoid_enemy_contact(
        self,
        drone: TeamDrone,
        own: tuple[float, float, float],
        desired_x: float,
        desired_y: float,
        ignore_enemy: str | None = None,
    ) -> tuple[float, float, str | None]:
        push_x = 0.0
        push_y = 0.0
        reason = None
        enemies = self.blue_drones if drone.team == "red" else self.red_drones
        for enemy in enemies:
            if enemy.name == ignore_enemy:
                continue
            enemy_pose = self._pose(enemy.name)
            if enemy_pose is None:
                continue
            distance = math.hypot(own[0] - enemy_pose[0], own[1] - enemy_pose[1])
            if distance <= 1e-6 or distance >= self.min_enemy_separation:
                continue
            away_x, away_y = self._normalize_xy(own[0] - enemy_pose[0], own[1] - enemy_pose[1])
            strength = (self.min_enemy_separation - distance) / self.min_enemy_separation
            push_x += away_x * strength * self.min_enemy_separation
            push_y += away_y * strength * self.min_enemy_separation
            reason = f"keeping tag spacing from {enemy.name}"
        if reason is None:
            return desired_x, desired_y, None
        return self._bounded_xy(desired_x + push_x, desired_y + push_y) + (reason,)

    def _separate_from_allies(
        self,
        drone: TeamDrone,
        own: tuple[float, float, float],
        desired_x: float,
        desired_y: float,
    ) -> tuple[float, float]:
        push_x = 0.0
        push_y = 0.0
        for ally in self.red_drones if drone.team == "red" else self.blue_drones:
            if ally.name == drone.name:
                continue
            ally_pose = self._pose(ally.name)
            if ally_pose is None:
                continue
            away_x = own[0] - ally_pose[0]
            away_y = own[1] - ally_pose[1]
            distance = math.hypot(away_x, away_y)
            if distance <= 1e-6 or distance >= self.min_team_separation:
                continue
            away_x, away_y = self._normalize_xy(away_x, away_y)
            strength = (self.min_team_separation - distance) / self.min_team_separation
            push_x += away_x * strength * self.min_team_separation
            push_y += away_y * strength * self.min_team_separation
        return self._bounded_xy(desired_x + push_x, desired_y + push_y)

    def _role_height(self, base_z: float, role: str, index: int) -> float:
        offsets = {
            "screen": 45.0,
            "guard": 45.0,
            "decoy": -70.0,
            "bait": 85.0,
            "hide": -95.0,
            "flanker": 70.0,
            "pressure_screen": -55.0,
            "cutoff": 95.0,
            "support": -85.0,
            "search": 35.0,
            "interceptor": 0.0,
            "runner": 0.0,
        }
        offset = offsets.get(role, 0.0)
        offset += (index - 2) * 25.0 if index > 1 else 0.0
        return self._clamp_z(base_z + offset)

    def _fallback_role_for(self, drone: TeamDrone) -> str:
        if drone.team == "red":
            return {1: "runner", 2: "screen", 3: "decoy", 4: "hide", 5: "bait"}.get(drone_index(drone), "screen")
        return {1: "interceptor", 2: "flanker", 3: "pressure_screen", 4: "cutoff", 5: "search"}.get(
            drone_index(drone),
            "search",
        )

    def _desired_for_red(self, drone: TeamDrone, role: str) -> tuple[float, float, float, float] | None:
        own = self._pose(drone.name)
        runner = self._primary_pose("red")
        if own is None or runner is None:
            return None
        runner_enemy_info = self._nearest_enemy_to_pose("red", runner)
        own_enemy_info = self._nearest_enemy(drone)
        enemy_info = own_enemy_info or runner_enemy_info
        if enemy_info is None:
            away_x, away_y = self._normalize_xy(runner[0], runner[1])
            to_enemy_x, to_enemy_y = -away_x, -away_y
            enemy = runner
        else:
            _, enemy = enemy_info
            to_enemy_x, to_enemy_y = self._normalize_xy(enemy[0] - own[0], enemy[1] - own[1])
            away_x, away_y = -to_enemy_x, -to_enemy_y
        side = 1.0 if drone_index(drone) % 2 == 0 else -1.0
        perp_x, perp_y = -to_enemy_y * side, to_enemy_x * side
        threat_distance = self._distance(own, enemy) if enemy_info is not None else None
        runner_threat_distance = self._distance(runner, runner_enemy_info[1]) if runner_enemy_info is not None else None
        cover = cover_point(own, enemy, self.blockers, self.tactical_clearance) if enemy_info is not None else None

        if role in {"screen", "guard"}:
            pressure = 1.0 if runner_threat_distance is not None and runner_threat_distance < 1200.0 else 0.75
            runner_to_enemy_x, runner_to_enemy_y = self._normalize_xy(enemy[0] - runner[0], enemy[1] - runner[1])
            screen_perp_x, screen_perp_y = -runner_to_enemy_y * side, runner_to_enemy_x * side
            desired_x = runner[0] + runner_to_enemy_x * self.screen_distance * pressure + screen_perp_x * self.screen_lateral
            desired_y = runner[1] + runner_to_enemy_y * self.screen_distance * pressure + screen_perp_y * self.screen_lateral
            if threat_distance is not None and threat_distance < self.min_enemy_separation * 1.35:
                desired_x = own[0] + away_x * self.red_escape_distance + perp_x * self.screen_lateral
                desired_y = own[1] + away_y * self.red_escape_distance + perp_y * self.screen_lateral
                intent = "screen escaping hard after close blue pressure"
            elif cover is not None and not self._los_clear(own, enemy):
                desired_x, desired_y = cover[0], cover[1]
                intent = f"holding cover screen; {cover[2]}"
            else:
                intent = "blocking the chaser lane from a separated screen point"
            speed = self.red_profile.speeds.get("evade", 265.0)
        elif role in {"bait", "decoy"}:
            desired_x = own[0] + away_x * self.red_escape_distance + perp_x * self.decoy_distance * 0.65
            desired_y = own[1] + away_y * self.red_escape_distance + perp_y * self.decoy_distance * 0.65
            if cover is not None and threat_distance is not None and threat_distance < 900.0:
                desired_x = (desired_x + cover[0]) * 0.5
                desired_y = (desired_y + cover[1]) * 0.5
                intent = f"pulling pressure through cover; {cover[2]}"
            else:
                intent = "sprinting into a wide decoy escape lane"
            speed = self.red_profile.speeds.get("evade", 265.0)
        elif role == "hide":
            desired_x = own[0] + away_x * self.red_escape_distance * 1.15 - perp_x * self.decoy_distance * 0.55
            desired_y = own[1] + away_y * self.red_escape_distance * 1.15 - perp_y * self.decoy_distance * 0.55
            if cover is not None:
                desired_x, desired_y = cover[0], cover[1]
                intent = f"staying alive behind cover; {cover[2]}"
            else:
                intent = "opening maximum distance as a reset outlet"
            speed = self.red_profile.speeds.get("evade", 265.0)
        else:
            desired_x = own[0] + away_x * self.red_escape_distance * 0.9 - perp_x * self.decoy_distance * 0.45
            desired_y = own[1] + away_y * self.red_escape_distance * 0.9 - perp_y * self.decoy_distance * 0.45
            speed = self.red_profile.speeds.get("evade", 265.0)
            intent = "holding a safe outlet away from the runner"

        if threat_distance is not None and threat_distance < self.screen_hunt_distance:
            closeness = max(0.0, min(1.0, (self.screen_hunt_distance - threat_distance) / self.screen_hunt_distance))
            speed = max(speed, self.red_profile.speeds.get("burst", speed) * (0.72 + 0.28 * closeness))

        desired_x, desired_y = self._separate_from_allies(drone, own, desired_x, desired_y)
        desired_x, desired_y, avoid_reason = self._avoid_enemy_contact(drone, own, desired_x, desired_y)
        desired_x, desired_y, route_reason = self._route_xy(own, desired_x, desired_y)
        reasons = [intent, avoid_reason, route_reason]
        self.intent[drone.name] = "; ".join(reason for reason in reasons if reason)
        return desired_x, desired_y, self._role_height(runner[2], role, drone_index(drone)), speed

    def _desired_for_blue(self, drone: TeamDrone, role: str) -> tuple[float, float, float, float] | None:
        own = self._pose(drone.name)
        runner = self._primary_pose("red")
        if own is None or runner is None:
            return None
        chaser = self._primary_pose("blue") or own
        screen = self._assigned_red_support_for_blue(drone) or self._nearest_red_support_to_runner()
        if drone_index(drone) > 1 and screen is not None and role in {"flanker", "cutoff", "support"}:
            role = "pressure_screen"
        target = runner
        target_enemy_name = None
        intent = "pressuring runner"
        if role in {"pressure_screen", "support"} and screen is not None:
            screen_name, screen_pose = screen
            target = screen_pose
            target_enemy_name = screen_name
            intent = f"hunting {screen_name} before it can screen"
        blocked_reason = self._blocking_line_reason(chaser, runner)

        runner_from_chaser_x, runner_from_chaser_y = self._normalize_xy(runner[0] - chaser[0], runner[1] - chaser[1])
        side = 1.0 if drone_index(drone) % 2 == 0 else -1.0
        perp_x, perp_y = -runner_from_chaser_y * side, runner_from_chaser_x * side
        if role == "search":
            search_x, search_y = self._blue_search_point(drone, runner, chaser, blocked_reason is not None)
            desired_x = search_x
            desired_y = search_y
            speed = self.blue_profile.speeds.get("search", 190.0)
            intent = "splitting into a search lane around last known red"
            if blocked_reason:
                intent = f"splitting search because runner sight is {blocked_reason}"
        elif role == "support":
            center_x, center_y = self._normalize_xy(-runner[0], -runner[1])
            desired_x = runner[0] + center_x * self.cutoff_distance + perp_x * self.flank_distance * 0.35
            desired_y = runner[1] + center_y * self.cutoff_distance + perp_y * self.flank_distance * 0.35
            speed = self.blue_profile.speeds.get("base", 260.0)
            intent = "denying center escape"
        elif role in {"cutoff", "flanker"}:
            forward_scale = 0.15 if blocked_reason else 0.35
            desired_x = runner[0] + runner_from_chaser_x * self.flank_distance * forward_scale + perp_x * self.cutoff_distance
            desired_y = runner[1] + runner_from_chaser_y * self.flank_distance * forward_scale + perp_y * self.cutoff_distance
            speed = self.blue_profile.speeds.get("intercept", 300.0)
            intent = "holding a pincer lane beside the runner"
            if blocked_reason:
                intent = f"flanking around cover because runner sight is {blocked_reason}"
        elif role == "pressure_screen":
            if screen is not None:
                screen_name, screen_pose = screen
                red_to_screen_x, red_to_screen_y = self._normalize_xy(screen_pose[0] - runner[0], screen_pose[1] - runner[1])
                close_offset = 80.0 + drone_index(drone) * 35.0
                desired_x = screen_pose[0] + red_to_screen_x * close_offset + perp_x * (80.0 + drone_index(drone) * 35.0)
                desired_y = screen_pose[1] + red_to_screen_y * close_offset + perp_y * (80.0 + drone_index(drone) * 35.0)
                intent = f"closing down {screen_name} screen"
            else:
                desired_x = runner[0] + runner_from_chaser_x * self.screen_hunt_distance * 0.35
                desired_y = runner[1] + runner_from_chaser_y * self.screen_hunt_distance * 0.35
                intent = "probing the runner lane for a screen"
            speed = self.blue_profile.speeds.get("intercept", 300.0)
        else:
            desired_x = target[0]
            desired_y = target[1]
            speed = self.blue_profile.speeds.get("intercept", 300.0)

        desired_x, desired_y = self._separate_from_allies(drone, own, desired_x, desired_y)
        desired_x, desired_y, avoid_reason = self._avoid_enemy_contact(
            drone,
            own,
            desired_x,
            desired_y,
            ignore_enemy=target_enemy_name,
        )
        desired_x, desired_y, route_reason = self._route_xy(own, desired_x, desired_y)
        reasons = [intent, avoid_reason, route_reason]
        self.intent[drone.name] = "; ".join(reason for reason in reasons if reason)
        speed *= self.blue_support_speed_scale
        return desired_x, desired_y, self._role_height(target[2], role, drone_index(drone)), speed

    def _assigned_red_support_for_blue(self, drone: TeamDrone) -> tuple[str, tuple[float, float, float]] | None:
        runner = self._primary_pose("red")
        if runner is None:
            return None
        candidates: list[tuple[str, tuple[float, float, float], float]] = []
        for red in self.red_drones:
            if red.name == "red_1":
                continue
            pose = self._pose(red.name)
            if pose is None or pose[2] <= self.min_z + 40.0:
                continue
            distance = self._distance(runner, pose)
            if distance <= self.screen_hunt_distance:
                candidates.append((red.name, pose, distance))
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[2], item[0]))
        slot = max(0, drone_index(drone) - 2)
        name, pose, _ = candidates[slot % len(candidates)]
        return name, pose

    def _blue_search_point(
        self,
        drone: TeamDrone,
        runner: tuple[float, float, float],
        chaser: tuple[float, float, float],
        sight_blocked: bool,
    ) -> tuple[float, float]:
        index = max(2, drone_index(drone))
        runner_from_chaser_x, runner_from_chaser_y = self._normalize_xy(runner[0] - chaser[0], runner[1] - chaser[1])
        perp_x, perp_y = -runner_from_chaser_y, runner_from_chaser_x
        lane_slots = {
            2: (-1.15, 0.35),
            3: (1.15, 0.35),
            4: (-0.55, 1.0),
            5: (0.55, 1.0),
        }
        lateral_scale, forward_scale = lane_slots.get(index, (1.35 if index % 2 else -1.35, 0.7))
        if sight_blocked:
            forward_scale += 0.35
        desired_x = (
            runner[0]
            + runner_from_chaser_x * self.search_forward * forward_scale
            + perp_x * self.search_radius * lateral_scale
        )
        desired_y = (
            runner[1]
            + runner_from_chaser_y * self.search_forward * forward_scale
            + perp_y * self.search_radius * lateral_scale
        )
        return self._bounded_xy(desired_x, desired_y)

    def _nearest_red_support_to_runner(self) -> tuple[str, tuple[float, float, float]] | None:
        runner = self._primary_pose("red")
        if runner is None:
            return None
        chaser = self._primary_pose("blue")
        best = None
        best_distance = float("inf")
        for drone in self.red_drones:
            if drone.name == "red_1":
                continue
            pose = self._pose(drone.name)
            if pose is None:
                continue
            if pose[2] <= self.min_z + 40.0:
                continue
            distance = self._distance(runner, pose)
            if distance > self.screen_hunt_distance:
                continue
            line_bonus = 0.0
            if chaser is not None:
                line_bonus = segment_distance_xy(runner[0], runner[1], chaser[0], chaser[1], pose[0], pose[1])
            score = distance + line_bonus * 0.75
            if score < best_distance:
                best_distance = score
                best = (drone.name, pose)
        return best

    def _command_toward(
        self,
        own: tuple[float, float, float],
        desired: tuple[float, float, float, float],
    ) -> Twist:
        desired_x, desired_y, desired_z, speed = desired
        dx = desired_x - own[0]
        dy = desired_y - own[1]
        distance_xy = math.hypot(dx, dy)
        hx, hy = self._normalize_xy(dx, dy)
        if distance_xy < self.arrive_radius:
            speed *= max(0.2, distance_xy / max(self.arrive_radius, 1.0))
        cmd = Twist()
        cmd.linear.x = hx * speed
        cmd.linear.y = hy * speed
        z_error = self._clamp_z(desired_z) - own[2]
        if abs(z_error) > 5.0:
            cmd.linear.z = max(-self.vertical_speed, min(self.vertical_speed, z_error / max(self.tick_dt, 1e-3)))
        return cmd

    def _publish_periodic_status(self) -> None:
        now = time.time()
        if now - self.last_status_at < 5.0:
            return
        self.last_status_at = now
        roles = {drone.name: self.roles.get(drone.name, self._fallback_role_for(drone)) for drone in self.drones}
        intents = {name: self.intent.get(name, "") for name in roles if self.intent.get(name)}
        self.publish_status(
            "Team support active: "
            f"scope={self.team_scope}, roles={json.dumps(roles, separators=(',', ':'))}, "
            f"intent={json.dumps(intents, separators=(',', ':'))}"
        )

    def control_loop(self) -> None:
        if not self.started:
            self._publish_zero_all()
            return
        self._publish_periodic_status()
        for drone in self.drones:
            pub = self.cmd_pubs.get(drone.name)
            if pub is None:
                continue
            own = self._pose(drone.name)
            if own is None:
                continue
            role = self.roles.get(drone.name, self._fallback_role_for(drone))
            desired = self._desired_for_red(drone, role) if drone.team == "red" else self._desired_for_blue(drone, role)
            if desired is None:
                continue
            pub.publish(self._command_toward(own, desired))


def drone_index(drone: TeamDrone) -> int:
    try:
        return int(drone.name.rsplit("_", 1)[-1])
    except ValueError:
        return 1


def main(args=None) -> None:
    rclpy.init(args=args)
    node = TeamDroneController()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node._publish_zero_all()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
