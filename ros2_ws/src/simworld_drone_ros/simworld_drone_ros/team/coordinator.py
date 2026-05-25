from __future__ import annotations

import json
import math
import os
import time

from geometry_msgs.msg import PoseStamped
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from simworld_drone_ros.team.models import TeamDrone, TeamPlan, build_team, read_team_speed_profile
from simworld_drone_ros.team.tactical_geometry import (
    distance_xy,
    line_of_sight_clear,
    read_tactical_blockers,
    segment_distance_xy,
)


class TeamCoordinator(Node):
    """Lightweight strategy layer for team-vs-team support roles."""

    def __init__(self) -> None:
        self.team = os.environ.get("SIM_TEAM", "blue").strip().lower()
        super().__init__(f"{self.team}_team_coordinator")

        self.status_pub = self.create_publisher(String, "/sim/status", 20)
        self.role_pubs: dict[str, object] = {}
        self.drones = self._team_drones(self.team)
        self.red_drones = self._team_drones("red")
        self.blue_drones = self._team_drones("blue")
        self.speed_profile = read_team_speed_profile(self.team)
        for drone in self.drones:
            self.role_pubs[drone.name] = self.create_publisher(String, drone.role_topic, 10)

        self.poses: dict[str, tuple[float, float, float, float]] = {}
        self.pose_subs = []
        for drone in self.red_drones + self.blue_drones:
            self.pose_subs.append(
                self.create_subscription(
                    PoseStamped,
                    drone.pose_topic,
                    lambda msg, selected=drone: self.pose_callback(selected, msg),
                    10,
                )
            )

        self.started_at = time.time()
        self.plan_sec = self._read_float_env("SIM_TEAM_PLAN_SEC", 3.0)
        self.close_pressure_cm = self._read_float_env("SIM_TEAM_COORD_CLOSE_PRESSURE_CM", 650.0)
        self.mid_pressure_cm = self._read_float_env("SIM_TEAM_COORD_MID_PRESSURE_CM", 1250.0)
        self.screen_line_cm = self._read_float_env("SIM_TEAM_COORD_SCREEN_LINE_CM", 420.0)
        self.active_support_max_cm = self._read_float_env("SIM_TEAM_COORD_ACTIVE_SUPPORT_MAX_CM", 2600.0)
        self.min_z = self._read_float_env("SIMWORLD_DRONE_MIN_Z", self._read_float_env("SIM_DRONE_MIN_Z", 100.0))
        self.tactical_clearance = self._read_float_env("SIM_TACTICAL_CLEARANCE_CM", 170.0)
        self.blockers = read_tactical_blockers(
            self.min_z,
            self._read_float_env("SIMWORLD_DRONE_MAX_Z", self._read_float_env("SIM_DRONE_MAX_Z", 700.0)),
        )
        self.timer = self.create_timer(self.plan_sec, self.control_loop)
        speeds = json.dumps(self.speed_profile.speeds, separators=(",", ":"))
        self.publish_status(
            f"Team coordinator ready: team={self.team}, drones={','.join(d.name for d in self.drones)}, "
            f"speeds={speeds}, model={self.speed_profile.model_reference}, mode=live_state, "
            f"tactical_blockers={len(self.blockers)}"
        )

    def _read_float_env(self, name: str, default: float) -> float:
        value = os.environ.get(name)
        if value is None:
            return default
        try:
            return float(value)
        except ValueError:
            return default

    def _team_drones(self, team: str) -> tuple[TeamDrone, ...]:
        return build_team(team)

    def publish_status(self, text: str) -> None:
        msg = String()
        msg.data = text
        self.status_pub.publish(msg)
        self.get_logger().info(text)

    def pose_callback(self, drone: TeamDrone, msg: PoseStamped) -> None:
        self.poses[drone.name] = (
            msg.pose.position.x,
            msg.pose.position.y,
            msg.pose.position.z,
            time.time(),
        )

    def _pose(self, name: str) -> tuple[float, float, float] | None:
        pose = self.poses.get(name)
        if pose is None:
            return None
        return pose[0], pose[1], pose[2]

    def _distance(self, first: str, second: str) -> float | None:
        first_pose = self._pose(first)
        second_pose = self._pose(second)
        if first_pose is None or second_pose is None:
            return None
        return math.sqrt(
            (first_pose[0] - second_pose[0]) ** 2
            + (first_pose[1] - second_pose[1]) ** 2
            + (first_pose[2] - second_pose[2]) ** 2
        )

    def _nearest_enemy_to(self, team: str, drone_name: str) -> tuple[str, float] | None:
        pose = self._pose(drone_name)
        if pose is None:
            return None
        enemies = self.blue_drones if team == "red" else self.red_drones
        best_name = None
        best_distance = float("inf")
        for enemy in enemies:
            enemy_pose = self._pose(enemy.name)
            if enemy_pose is None:
                continue
            distance = math.sqrt(
                (pose[0] - enemy_pose[0]) ** 2
                + (pose[1] - enemy_pose[1]) ** 2
                + (pose[2] - enemy_pose[2]) ** 2
            )
            if distance < best_distance:
                best_distance = distance
                best_name = enemy.name
        if best_name is None:
            return None
        return best_name, best_distance

    def _red_support_screening(self, runner: tuple[float, float, float], chaser: tuple[float, float, float]) -> str | None:
        best_name = None
        best_score = float("inf")
        for drone in self.red_drones:
            if drone.name == "red_1":
                continue
            pose = self._pose(drone.name)
            if pose is None:
                continue
            if pose[2] <= self.min_z + 40.0:
                continue
            runner_distance = distance_xy(pose, runner)
            if runner_distance > self.active_support_max_cm:
                continue
            line_distance = segment_distance_xy(runner[0], runner[1], chaser[0], chaser[1], pose[0], pose[1])
            if line_distance > self.screen_line_cm * 2.0:
                continue
            score = line_distance + abs(runner_distance - 650.0) * 0.2
            if score < best_score:
                best_score = score
                best_name = drone.name
        return best_name

    def _active_red_support(self, runner: tuple[float, float, float]) -> str | None:
        best_name = None
        best_distance = float("inf")
        for drone in self.red_drones:
            if drone.name == "red_1":
                continue
            pose = self._pose(drone.name)
            if pose is None or pose[2] <= self.min_z + 40.0:
                continue
            distance = distance_xy(pose, runner)
            if distance < best_distance and distance <= self.active_support_max_cm:
                best_distance = distance
                best_name = drone.name
        return best_name

    def _los_clear(self, first: tuple[float, float, float], second: tuple[float, float, float]) -> bool:
        return line_of_sight_clear(first, second, self.blockers, self.tactical_clearance)

    def _assign_roles(self, role_order: tuple[str, ...]) -> dict[str, str]:
        return {
            drone.name: role_order[index] if index < len(role_order) else role_order[-1]
            for index, drone in enumerate(self.drones)
        }

    def _fallback_plan(self) -> TeamPlan:
        live = self._live_plan()
        if live is not None:
            return live
        if self.team == "red":
            roles = self._assign_roles(("runner", "screen", "decoy", "hide", "bait"))
            return TeamPlan(
                team=self.team,
                roles=roles,
                rationale="runner escapes while support screens, splits, and baits pressure",
            )

        roles = self._assign_roles(("interceptor", "flanker", "pressure_screen", "cutoff", "support"))
        return TeamPlan(
            team=self.team,
            roles=roles,
            rationale="primary chases runner while support clears screens and cuts escape lanes",
        )

    def _live_plan(self) -> TeamPlan | None:
        runner = self._pose("red_1")
        chaser = self._pose("blue_1")
        if runner is None or chaser is None:
            return None
        pressure = self._distance("red_1", "blue_1")
        if pressure is None:
            return None
        los_clear = self._los_clear(runner, chaser)
        screen_name = self._red_support_screening(runner, chaser)
        active_red_support = screen_name or self._active_red_support(runner)
        if self.team == "red":
            return self._red_live_plan(pressure, los_clear)
        return self._blue_live_plan(pressure, los_clear, screen_name, active_red_support)

    def _red_live_plan(self, pressure: float, los_clear: bool) -> TeamPlan:
        roles: dict[str, str] = {}
        for drone in self.drones:
            index = _drone_index(drone)
            if index == 1:
                roles[drone.name] = "runner"
                continue
            nearest_enemy = self._nearest_enemy_to("red", drone.name)
            if nearest_enemy is not None and nearest_enemy[1] < self.close_pressure_cm:
                roles[drone.name] = "hide"
            elif pressure < self.close_pressure_cm:
                roles[drone.name] = "bait" if index % 2 else "screen"
            elif pressure < self.mid_pressure_cm and los_clear:
                roles[drone.name] = "screen" if index <= 3 else "decoy"
            elif pressure < self.mid_pressure_cm:
                roles[drone.name] = "decoy" if index % 2 else "hide"
            else:
                roles[drone.name] = "decoy" if index % 2 else "hide"
        reason = "red protects runner with adaptive screens and survival outlets"
        if not los_clear:
            reason = "red uses cover/outlets because runner-to-chaser sight is already broken"
        return TeamPlan(team=self.team, focus_enemy="blue_1", roles=roles, rationale=reason)

    def _blue_live_plan(
        self,
        pressure: float,
        los_clear: bool,
        screen_name: str | None,
        active_red_support: str | None,
    ) -> TeamPlan:
        roles: dict[str, str] = {}
        for drone in self.drones:
            index = _drone_index(drone)
            if index == 1:
                roles[drone.name] = "interceptor"
                continue
            if active_red_support is not None:
                roles[drone.name] = "pressure_screen"
            elif not los_clear:
                roles[drone.name] = "search" if index % 2 == 0 else "cutoff"
            elif pressure > self.mid_pressure_cm:
                roles[drone.name] = "cutoff" if index % 2 == 0 else "flanker"
            elif pressure < self.close_pressure_cm:
                roles[drone.name] = "pressure_screen" if screen_name is not None else "support"
            else:
                roles[drone.name] = "flanker" if index % 2 == 0 else "cutoff"
        reason = "blue adapts between screen clear, flank, and cutoff pressure"
        if screen_name:
            reason = f"blue clears active red screen {screen_name}"
        elif active_red_support:
            reason = f"blue hunts red support {active_red_support} before it can screen"
        elif not los_clear:
            reason = "blue splits into search lanes around blocked runner sight"
        return TeamPlan(team=self.team, focus_enemy="red_1", roles=roles, rationale=reason)

    def _publish_plan(self, plan: TeamPlan) -> None:
        payload = {
            "team": plan.team,
            "focus_enemy": plan.focus_enemy,
            "roles": plan.roles,
            "rationale": plan.rationale,
        }
        for drone_name, role in plan.roles.items():
            pub = self.role_pubs.get(drone_name)
            if pub is None:
                continue
            msg = String()
            msg.data = json.dumps({"role": role, "plan": payload}, separators=(",", ":"))
            pub.publish(msg)
        self.publish_status(
            f"Team coordinator plan: team={plan.team}, roles={json.dumps(plan.roles, separators=(',', ':'))}, "
            f"reason={plan.rationale}"
        )

    def control_loop(self) -> None:
        self._publish_plan(self._fallback_plan())


def _drone_index(drone: TeamDrone) -> int:
    try:
        return int(drone.name.rsplit("_", 1)[-1])
    except ValueError:
        return 1


def main(args=None) -> None:
    rclpy.init(args=args)
    node = TeamCoordinator()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
