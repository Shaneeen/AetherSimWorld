from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import math
import os
import re
import time

from geometry_msgs.msg import PoseStamped
import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
import requests
from std_msgs.msg import String

from simworld_drone_ros.team.models import TeamDrone, TeamPlan, build_team, read_team_speed_profile
from simworld_drone_ros.team.tactical_geometry import (
    distance_xy,
    line_of_sight_clear,
    read_tactical_blockers,
    segment_distance_xy,
)
from simworld_drone_ros.vision.scene_parser import compact_scene_for_prompt, normalize_scene


CONTROL_QOS = QoSProfile(depth=10)
CONTROL_QOS.reliability = ReliabilityPolicy.RELIABLE
CONTROL_QOS.durability = DurabilityPolicy.TRANSIENT_LOCAL


class TeamCoordinator(Node):
    """Lightweight strategy layer for team-vs-team support roles."""

    def __init__(self) -> None:
        self.team = os.environ.get("SIM_TEAM", "blue").strip().lower()
        super().__init__(f"{self.team}_team_coordinator")

        self.status_pub = self.create_publisher(String, "/sim/status", 20)
        self.control_sub = self.create_subscription(String, "/team/control", self.control_callback, CONTROL_QOS)
        self.role_pubs: dict[str, object] = {}
        self.drones = self._team_drones(self.team)
        self.red_drones = self._team_drones("red")
        self.blue_drones = self._team_drones("blue")
        self.speed_profile = read_team_speed_profile(self.team)
        self.ollama_enabled = os.environ.get("SIM_TEAM_USE_OLLAMA", os.environ.get("USE_OLLAMA", "1")) != "0"
        self.ollama_model = os.environ.get("SIM_TEAM_OLLAMA_MODEL", os.environ.get("OLLAMA_MODEL", "gpt-oss:latest"))
        self.ollama_urls = self._read_ollama_urls()
        self.ollama_timeout = self._read_float_env("OLLAMA_TIMEOUT_SEC", 60.0)
        self.ollama_decision_cooldown_sec = self._read_float_env("SIM_TEAM_OLLAMA_COOLDOWN_SEC", 12.0)
        self.ollama_failure_backoff_sec = self._read_float_env("SIM_TEAM_OLLAMA_FAILURE_BACKOFF_SEC", 18.0)
        self.ollama_max_backoff_sec = self._read_float_env("SIM_TEAM_OLLAMA_MAX_BACKOFF_SEC", 90.0)
        self.ollama_plan_cache_sec = self._read_float_env("SIM_TEAM_OLLAMA_PLAN_CACHE_SEC", 24.0)
        self.ollama_initial_delay_sec = self._read_float_env(
            "SIM_TEAM_OLLAMA_INITIAL_DELAY_SEC",
            2.5 if self.team == "red" else 6.0,
        )
        self.ollama_num_ctx = int(self._read_float_env("SIM_TEAM_OLLAMA_NUM_CTX", 768.0))
        self.ollama_num_predict = int(self._read_float_env("SIM_TEAM_OLLAMA_NUM_PREDICT", 256.0))
        self.ollama_num_gpu = int(self._read_float_env("SIM_TEAM_OLLAMA_NUM_GPU", -1.0))
        self.ollama_executor = ThreadPoolExecutor(max_workers=1)
        self.ollama_future = None
        self.last_ollama_request_at = time.time() + self.ollama_initial_delay_sec - self.ollama_decision_cooldown_sec
        self.ollama_failure_count = 0
        self.ollama_disabled_until = 0.0
        self.pending_ollama_error = None
        self.cached_ollama_plan: TeamPlan | None = None
        self.cached_ollama_at = 0.0
        self.started = os.environ.get("SIM_TEAM_START_ACTIVE", "1").lower() not in {"0", "false", "no"}
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
        self.latest_vision_scene: dict | None = None
        self.latest_vision_at = 0.0
        self.vision_hint_enabled = os.environ.get("SIM_TEAM_USE_VISION_HINTS", "1").lower() not in {
            "0",
            "false",
            "no",
        }
        self.vision_max_age_sec = self._read_float_env("SIM_TEAM_VISION_MAX_AGE_SEC", 60.0)
        self.vision_min_confidence = self._read_float_env("SIM_TEAM_VISION_MIN_CONFIDENCE", 0.45)
        self.vision_sub = self.create_subscription(String, "/sim/vision_scene", self.vision_callback, 20)

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
            f"ollama={int(self.ollama_enabled)}, ollama_model={self.ollama_model}, "
            f"ollama_urls={','.join(self.ollama_urls)}, "
            f"planner_cooldown={self.ollama_decision_cooldown_sec:.1f}s "
            f"planner_cache={self.ollama_plan_cache_sec:.1f}s "
            f"planner_initial_delay={self.ollama_initial_delay_sec:.1f}s "
            f"vision_hints={int(self.vision_hint_enabled)}, "
            f"tactical_blockers={len(self.blockers)}, "
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

    def _team_drones(self, team: str) -> tuple[TeamDrone, ...]:
        return build_team(team)

    def _read_ollama_urls(self) -> list[str]:
        urls_value = os.environ.get("SIM_TEAM_OLLAMA_API_URLS", os.environ.get("OLLAMA_API_URLS"))
        if not urls_value:
            urls_value = os.environ.get("SIM_TEAM_OLLAMA_API_URL", os.environ.get("OLLAMA_API_URL"))
        if not urls_value:
            urls_value = "http://10.8.0.132:11434/api/generate"
        urls = [url.strip() for url in urls_value.split(",") if url.strip()]
        return urls or ["http://10.8.0.132:11434/api/generate"]

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

    def control_callback(self, msg: String) -> None:
        command = msg.data.strip().lower()
        if command in {"start", "start_all", "start_team"}:
            self.started = True
            self.pending_ollama_error = None
            self.ollama_disabled_until = 0.0
            self.ollama_failure_count = 0
            self.publish_status(f"Team coordinator received START: team={self.team}")
        elif command in {"stop", "stop_all", "stop_team"}:
            self.started = False
            self.pending_ollama_error = None
            self.ollama_disabled_until = float("inf")
            if self.ollama_future is not None:
                self.ollama_future.cancel()
                self.ollama_future = None
            self.publish_status(f"Team coordinator received STOP: team={self.team}")

    def vision_callback(self, msg: String) -> None:
        try:
            parsed = json.loads(msg.data)
            scene = normalize_scene(parsed, observer=str(parsed.get("observer", "unknown")), source=str(parsed.get("source", "vision")))
        except Exception as exc:
            self.publish_status(f"Team coordinator ignored bad vision scene: {exc}")
            return
        self.latest_vision_scene = scene
        self.latest_vision_at = time.time()
        self.publish_status(
            "Team coordinator accepted vision scene: "
            f"team={self.team} source={scene.get('source')} "
            f"confidence={float(scene.get('confidence', 0.0) or 0.0):.2f} "
            f"runner_visible={scene.get('runner_visible')} "
            f"hint={self._vision_hint_reason(scene) or 'none'}"
        )

    def _fresh_vision_scene(self) -> dict | None:
        if not self.vision_hint_enabled or self.latest_vision_scene is None:
            return None
        if time.time() - self.latest_vision_at > self.vision_max_age_sec:
            return None
        confidence = float(self.latest_vision_scene.get("confidence", 0.0) or 0.0)
        if confidence < self.vision_min_confidence:
            return None
        return self.latest_vision_scene

    def _vision_hint_reason(self, scene: dict | None) -> str | None:
        if not scene:
            return None
        bits = []
        if scene.get("runner_visible") is False:
            bits.append("vision says runner is not visible")
        if scene.get("blocked_by"):
            bits.append(f"blocked by {scene['blocked_by']}")
        if scene.get("nearest_cover"):
            bits.append(f"cover {scene['nearest_cover']}")
        if scene.get("recommended_search_area"):
            bits.append(f"search {scene['recommended_search_area']}")
        if scene.get("suggested_tactic"):
            bits.append(str(scene["suggested_tactic"])[:90])
        return "; ".join(bits) if bits else None

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

    def _allowed_roles(self) -> tuple[str, ...]:
        if self.team == "red":
            return ("runner", "screen", "decoy", "hide", "bait")
        return ("interceptor", "flanker", "pressure_screen", "cutoff", "support", "search")

    def _build_ollama_request(self, fallback: TeamPlan) -> dict:
        system, payload_obj = self._ollama_prompt_parts(fallback)
        prompt = f"/no_think\nSystem:\n{system}\n\nUser:\n{json.dumps(payload_obj, separators=(',', ':'))}\n\nJSON:"
        return self._ollama_generate_body(prompt, self.ollama_num_predict)

    def _ollama_prompt_parts(self, fallback: TeamPlan) -> tuple[str, dict]:
        runner = self._pose("red_1")
        chaser = self._pose("blue_1")
        pressure = self._distance("red_1", "blue_1")
        live_poses = {
            drone.name: {
                "x": round(pose[0], 1),
                "y": round(pose[1], 1),
                "z": round(pose[2], 1),
            }
            for drone in self.red_drones + self.blue_drones
            for pose in [self._pose(drone.name)]
            if pose is not None
        }
        payload_obj = {
            "team": self.team,
            "drones": [drone.name for drone in self.drones],
            "allowed_roles": self._allowed_roles(),
            "current_roles": fallback.roles,
            "fallback_reason": fallback.rationale,
            "vision_scene": compact_scene_for_prompt(self._fresh_vision_scene()),
            "red_1": runner,
            "blue_1": chaser,
            "pressure_cm": round(pressure, 1) if pressure is not None else None,
            "poses": live_poses,
            "goal": "red survives and screens" if self.team == "red" else "blue catches all red targets",
        }
        system = (
            "You are the team coordinator for a SimWorld 5v5 drone chase. "
            "Choose one immediate role for every drone on your team. "
            "Return exactly one valid compact JSON object and no other text: "
            "{\"roles\":{\"drone_name\":\"role\"},\"reason\":\"short reason\"}. "
            "Use only the allowed roles. Keep red_1 as runner and blue_1 as interceptor. "
            "Treat vision_scene as a tactical hint only; never assign a role that is not allowed. "
            "For red, spread support between screen, decoy, hide, and bait. "
            "For blue, spread pressure between flanker, pressure_screen, cutoff, support, and search. "
            "Do not explain. Do not think step by step. Do not write markdown. "
            "If uncertain, return the current_roles as valid JSON."
        )
        return system, payload_obj

    def _ollama_generate_body(self, prompt: str, num_predict: int) -> dict:
        options = {
            "temperature": 0.2,
            "num_ctx": max(128, self.ollama_num_ctx),
            "num_predict": max(64, num_predict),
        }
        if self.ollama_num_gpu >= 0:
            options["num_gpu"] = self.ollama_num_gpu
        return {
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "format": "json",
            "keep_alive": os.environ.get("SIM_TEAM_OLLAMA_KEEP_ALIVE", "10m"),
            "options": options,
        }

    def _build_ollama_chat_request(self, fallback: TeamPlan) -> dict:
        system, payload_obj = self._ollama_prompt_parts(fallback)
        options = {
            "temperature": 0.0,
            "num_ctx": max(128, self.ollama_num_ctx),
            "num_predict": max(128, self.ollama_num_predict),
        }
        if self.ollama_num_gpu >= 0:
            options["num_gpu"] = self.ollama_num_gpu
        return {
            "model": self.ollama_model,
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": json.dumps(payload_obj, separators=(",", ":")),
                },
            ],
            "stream": False,
            "think": False,
            "format": "json",
            "keep_alive": os.environ.get("SIM_TEAM_OLLAMA_KEEP_ALIVE", "10m"),
            "options": options,
        }

    def _build_ollama_repair_request(self, raw: str, fallback: TeamPlan) -> dict:
        payload_obj = {
            "team": self.team,
            "drones": [drone.name for drone in self.drones],
            "allowed_roles": self._allowed_roles(),
            "current_roles": fallback.roles,
            "model_text": raw[:2000],
        }
        prompt = (
            "/no_think\n"
            "System:\n"
            "Convert the model_text into exactly one valid compact JSON object with this schema: "
            "{\"roles\":{\"drone_name\":\"role\"},\"reason\":\"short reason\"}. "
            "Use only allowed_roles. Include every drone. Keep red_1 as runner and blue_1 as interceptor. "
            "If model_text is unusable, return current_roles. No markdown. No explanation.\n\n"
            f"User:\n{json.dumps(payload_obj, separators=(',', ':'))}\n\nJSON:"
        )
        options = {
            "temperature": 0,
            "num_ctx": max(512, self.ollama_num_ctx),
            "num_predict": max(256, self.ollama_num_predict),
        }
        if self.ollama_num_gpu >= 0:
            options["num_gpu"] = self.ollama_num_gpu
        return {
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "format": "json",
            "keep_alive": os.environ.get("SIM_TEAM_OLLAMA_KEEP_ALIVE", "10m"),
            "options": options,
        }

    def _build_ollama_repair_chat_request(self, raw: str, fallback: TeamPlan) -> dict:
        payload_obj = {
            "team": self.team,
            "drones": [drone.name for drone in self.drones],
            "allowed_roles": self._allowed_roles(),
            "current_roles": fallback.roles,
            "model_text": raw[:2000],
        }
        content = (
            "Convert model_text into one valid compact JSON object with schema "
            "{\"roles\":{\"drone_name\":\"role\"},\"reason\":\"short reason\"}. "
            "Use only allowed_roles. Include every drone. "
            "Keep red_1 as runner and blue_1 as interceptor. "
            "If model_text is unusable, return current_roles."
        )
        options = {
            "temperature": 0.0,
            "num_ctx": max(512, self.ollama_num_ctx),
            "num_predict": max(256, self.ollama_num_predict),
        }
        if self.ollama_num_gpu >= 0:
            options["num_gpu"] = self.ollama_num_gpu
        return {
            "model": self.ollama_model,
            "messages": [
                {"role": "system", "content": "Return only valid JSON. No prose."},
                {"role": "user", "content": f"{content}\n{json.dumps(payload_obj, separators=(',', ':'))}"},
            ],
            "stream": False,
            "think": False,
            "format": "json",
            "keep_alive": os.environ.get("SIM_TEAM_OLLAMA_KEEP_ALIVE", "10m"),
            "options": options,
        }

    def _parse_ollama_plan(self, raw: str, fallback: TeamPlan) -> TeamPlan:
        text = raw.strip()
        parsed = None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    parsed = json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    parsed = None
        if not isinstance(parsed, dict):
            salvaged = self._salvage_roles_from_text(text, fallback)
            if salvaged is not None:
                return salvaged
            raise RuntimeError(f"Ollama returned no JSON plan: {text[:160]!r}")
        raw_roles = parsed.get("roles", {})
        if not isinstance(raw_roles, dict):
            raise RuntimeError(f"Ollama returned invalid roles: {text[:160]!r}")
        allowed = set(self._allowed_roles())
        roles = dict(fallback.roles)
        for drone in self.drones:
            role = str(raw_roles.get(drone.name, "")).strip().lower()
            if role in allowed:
                roles[drone.name] = role
        if self.team == "red":
            roles["red_1"] = "runner"
        else:
            roles["blue_1"] = "interceptor"
        reason = str(parsed.get("reason", "ollama team role plan")).strip()[:160] or "ollama team role plan"
        return TeamPlan(team=self.team, focus_enemy=fallback.focus_enemy, roles=roles, rationale=reason)

    def _salvage_roles_from_text(self, text: str, fallback: TeamPlan) -> TeamPlan | None:
        allowed = set(self._allowed_roles())
        lower_text = text.lower()
        roles = dict(fallback.roles)
        found = 0
        for drone in self.drones:
            match = re.search(rf"{re.escape(drone.name.lower())}[^a-z0-9_]+([a-z_]+)", lower_text)
            if match and match.group(1) in allowed:
                roles[drone.name] = match.group(1)
                found += 1
        if found == 0:
            mentioned_roles = [role for role in allowed if re.search(rf"\b{re.escape(role)}\b", lower_text)]
            if not mentioned_roles:
                return None
            roles = dict(fallback.roles)
        if self.team == "red":
            roles["red_1"] = "runner"
        else:
            roles["blue_1"] = "interceptor"
        return TeamPlan(
            team=self.team,
            focus_enemy=fallback.focus_enemy,
            roles=roles,
            rationale="live role planner returned malformed text; salvaged safe roles",
        )

    def _ollama_request_worker(self, body: dict, fallback: TeamPlan) -> TeamPlan:
        errors = []
        for url in self.ollama_urls:
            attempts = []
            if os.environ.get("SIM_TEAM_OLLAMA_USE_CHAT", "1").lower() not in {"0", "false", "no"}:
                attempts.append(("chat", _ollama_chat_url(url), self._build_ollama_chat_request(fallback)))
            attempts.append(("generate", url, body))
            for mode, request_url, request_body in attempts:
                try:
                    plan = self._ollama_request_once(mode, request_url, request_body, fallback)
                    if mode == "chat" and not plan.rationale.startswith("chat planner:"):
                        plan.rationale = f"chat planner: {plan.rationale}"[:160]
                    return plan
                except Exception as exc:
                    errors.append(str(exc))
        raise RuntimeError("Ollama endpoints failed: " + " | ".join(errors))

    def _ollama_request_once(self, mode: str, url: str, body: dict, fallback: TeamPlan) -> TeamPlan:
        response = requests.post(url, json=body, timeout=max(1.0, self.ollama_timeout))
        response.raise_for_status()
        try:
            outer = response.json()
        except ValueError as exc:
            raise RuntimeError(f"{url} {mode} returned non-JSON HTTP body: {response.text[:160]!r}") from exc
        raw = _ollama_response_text(outer)
        if not raw:
            raise RuntimeError(f"{url} {mode} empty response ({_ollama_response_debug(outer)})")
        try:
            return self._parse_ollama_plan(raw, fallback)
        except Exception as parse_exc:
            if mode == "chat":
                repair_url = url
                repair_body = self._build_ollama_repair_chat_request(raw, fallback)
            else:
                repair_url = url
                repair_body = self._build_ollama_repair_request(raw, fallback)
            repair_response = requests.post(repair_url, json=repair_body, timeout=max(1.0, self.ollama_timeout))
            repair_response.raise_for_status()
            try:
                repair_outer = repair_response.json()
            except ValueError as exc:
                raise RuntimeError(f"{parse_exc}; {mode} repair returned non-JSON HTTP body") from exc
            repair_raw = _ollama_response_text(repair_outer)
            if not repair_raw:
                raise RuntimeError(
                    f"{parse_exc}; {mode} repair returned empty response ({_ollama_response_debug(repair_outer)})"
                )
            plan = self._parse_ollama_plan(repair_raw, fallback)
            plan.rationale = f"{mode} repaired JSON: {plan.rationale}"[:160]
            return plan

    def _record_ollama_failure(self, exc: Exception) -> None:
        self.ollama_failure_count += 1
        backoff = min(
            self.ollama_max_backoff_sec,
            self.ollama_failure_backoff_sec * (2 ** min(self.ollama_failure_count - 1, 4)),
        )
        self.ollama_disabled_until = time.time() + backoff
        self.pending_ollama_error = f"{exc}; retrying in {backoff:.0f}s"

    def _harvest_ollama_result(self) -> None:
        if self.ollama_future is None or not self.ollama_future.done():
            return
        try:
            plan = self.ollama_future.result()
            self.cached_ollama_plan = plan
            self.cached_ollama_at = time.time()
            self.ollama_failure_count = 0
            self.ollama_disabled_until = 0.0
            self.publish_status(
                f"Team coordinator cached Ollama plan: team={plan.team}, "
                f"roles={json.dumps(plan.roles, separators=(',', ':'))}, reason={plan.rationale}"
            )
        except Exception as exc:
            self._record_ollama_failure(exc)
        finally:
            self.ollama_future = None

    def _maybe_schedule_ollama(self, fallback: TeamPlan) -> None:
        if not self.started or not self.ollama_enabled:
            return
        if self.ollama_future is not None:
            return
        now = time.time()
        if now < self.ollama_disabled_until:
            return
        if now - self.last_ollama_request_at < self.ollama_decision_cooldown_sec:
            return
        body = self._build_ollama_request(fallback)
        self.ollama_future = self.ollama_executor.submit(self._ollama_request_worker, body, fallback)
        self.last_ollama_request_at = now

    def _plan_with_ollama(self) -> TeamPlan:
        fallback = self._fallback_plan()
        self._harvest_ollama_result()
        if self.pending_ollama_error:
            self.publish_status(f"Team coordinator Ollama fallback: team={self.team}, {self.pending_ollama_error}")
            self.pending_ollama_error = None
        self._maybe_schedule_ollama(fallback)
        if self.cached_ollama_plan is not None and time.time() - self.cached_ollama_at <= self.ollama_plan_cache_sec:
            return self.cached_ollama_plan
        return fallback

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
        vision_scene = self._fresh_vision_scene()
        vision_hint = self._vision_hint_reason(vision_scene)
        vision_cover_hint = bool(
            vision_scene
            and (
                vision_scene.get("runner_visible") is False
                or vision_scene.get("nearest_cover")
                or vision_scene.get("blocked_by")
            )
        )
        roles: dict[str, str] = {}
        for drone in self.drones:
            index = _drone_index(drone)
            if index == 1:
                roles[drone.name] = "runner"
                continue
            nearest_enemy = self._nearest_enemy_to("red", drone.name)
            if nearest_enemy is not None and nearest_enemy[1] < self.close_pressure_cm:
                roles[drone.name] = "hide"
            elif vision_cover_hint and index % 2 == 0:
                roles[drone.name] = "hide"
            elif vision_cover_hint:
                roles[drone.name] = "decoy"
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
        if vision_hint:
            reason = f"red blends live geometry with vision hint: {vision_hint}"
        return TeamPlan(team=self.team, focus_enemy="blue_1", roles=roles, rationale=reason)

    def _blue_live_plan(
        self,
        pressure: float,
        los_clear: bool,
        screen_name: str | None,
        active_red_support: str | None,
    ) -> TeamPlan:
        vision_scene = self._fresh_vision_scene()
        vision_hint = self._vision_hint_reason(vision_scene)
        vision_runner_lost = bool(
            vision_scene
            and (
                vision_scene.get("runner_visible") is False
                or vision_scene.get("blocked_by")
                or vision_scene.get("recommended_search_area")
            )
        )
        roles: dict[str, str] = {}
        for drone in self.drones:
            index = _drone_index(drone)
            if index == 1:
                roles[drone.name] = "interceptor"
                continue
            if active_red_support is not None:
                roles[drone.name] = "pressure_screen"
            elif vision_runner_lost:
                roles[drone.name] = "search" if index % 2 == 0 else "cutoff"
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
        elif vision_hint:
            reason = f"blue uses vision hint to split pressure: {vision_hint}"
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
        if not self.started:
            return
        self._publish_plan(self._plan_with_ollama())


def _drone_index(drone: TeamDrone) -> int:
    try:
        return int(drone.name.rsplit("_", 1)[-1])
    except ValueError:
        return 1


def _ollama_response_text(data: object) -> str:
    if not isinstance(data, dict):
        return ""
    response = data.get("response", "")
    if response:
        return str(response).strip()
    message = data.get("message", {})
    if isinstance(message, dict) and message.get("content"):
        return str(message.get("content", "")).strip()
    return str(data.get("thinking", "")).strip()


def _ollama_response_debug(data: object) -> str:
    if not isinstance(data, dict):
        return f"type={type(data).__name__}"
    parts = []
    for key in ("done_reason", "done", "eval_count", "prompt_eval_count", "total_duration"):
        if key in data:
            parts.append(f"{key}={data.get(key)!r}")
    message = data.get("message")
    if isinstance(message, dict):
        content = str(message.get("content", ""))
        thinking = str(message.get("thinking", ""))
        parts.append(f"message.content_len={len(content)}")
        parts.append(f"message.thinking_len={len(thinking)}")
    parts.append(f"response_len={len(str(data.get('response', '')))}")
    parts.append(f"thinking_len={len(str(data.get('thinking', '')))}")
    return ", ".join(parts)


def _ollama_chat_url(generate_url: str) -> str:
    if generate_url.endswith("/api/generate"):
        return generate_url[: -len("/api/generate")] + "/api/chat"
    if generate_url.endswith("/generate"):
        return generate_url[: -len("/generate")] + "/chat"
    return generate_url.rstrip("/") + "/api/chat"


def main(args=None) -> None:
    rclpy.init(args=args)
    node = TeamCoordinator()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.ollama_executor.shutdown(wait=False, cancel_futures=True)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
