import json
import math
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor

import requests
import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy

from geometry_msgs.msg import PoseStamped
from geometry_msgs.msg import Twist
from std_msgs.msg import String
from simworld_drone_ros.team.tactical_geometry import (
    read_tactical_blockers,
    route_around_blockers,
)


CONTROL_QOS = QoSProfile(depth=10)
CONTROL_QOS.reliability = ReliabilityPolicy.RELIABLE
CONTROL_QOS.durability = DurabilityPolicy.TRANSIENT_LOCAL


class ChaserBrain(Node):
    def __init__(self) -> None:
        super().__init__("chaser_brain")

        self.cmd_pub = self.create_publisher(Twist, "/drone_b/cmd_vel", 10)
        self.status_pub = self.create_publisher(String, "/sim/status", 20)
        self.target_pose_sub = self.create_subscription(
            PoseStamped,
            "/drone_a/pose",
            self.target_pose_callback,
            10,
        )
        self.self_pose_sub = self.create_subscription(
            PoseStamped,
            "/drone_b/pose",
            self.self_pose_callback,
            10,
        )
        self.control_sub = self.create_subscription(
            String,
            "/drone_b/control",
            self.control_callback,
            CONTROL_QOS,
        )

        self.base_speed = self._read_float_env("SIM_CHASER_SPEED", 260.0)
        self.intercept_speed = self._read_float_env("SIM_CHASER_INTERCEPT_SPEED", 300.0)
        self.search_speed = self._read_float_env("SIM_CHASER_SEARCH_SPEED", 200.0)
        self.catch_distance = self._read_float_env("SIM_CATCH_DISTANCE", 160.0)
        self.tick_dt = self._read_float_env("SIM_CHASER_DT", 0.1)

        self.reaction_delay_sec = self._read_float_env("SIM_CHASER_REACTION_DELAY_SEC", 0.75)
        self.commit_sec = self._read_float_env("SIM_CHASER_COMMIT_SEC", 1.2)
        self.turn_rate_deg = self._read_float_env("SIM_CHASER_TURN_RATE_DEG", 95.0)
        self.aim_noise_cm = self._read_float_env("SIM_CHASER_AIM_NOISE_CM", 120.0)
        self.search_radius_cm = self._read_float_env("SIM_CHASER_SEARCH_RADIUS_CM", 500.0)
        self.memory_timeout_sec = self._read_float_env("SIM_CHASER_MEMORY_TIMEOUT_SEC", 6.0)
        self.visible_range_cm = self._read_float_env("SIM_CHASER_VISIBLE_RANGE_CM", 5000.0)
        self.los_enabled = os.environ.get("SIM_LOS_ENABLED", "1").lower() not in {"0", "false", "no"}
        self.fov_deg = self._read_float_env("SIM_CHASER_FOV_DEG", 200.0)
        self.close_detect_range_cm = self._read_float_env("SIM_CHASER_CLOSE_DETECT_RANGE_CM", 220.0)
        self.fake_occlusion_prob = self._read_float_env("SIM_CHASER_FAKE_OCCLUSION_PROB", 0.0)
        self.los_blockers = self._read_los_blockers()
        self.tactical_clearance = self._read_float_env("SIM_TACTICAL_CLEARANCE_CM", 180.0)
        self.tactic_ttl_sec = self._read_float_env("SIM_CHASER_TACTIC_TTL_SEC", 4.0)
        self.finish_range_cm = self._read_float_env("SIM_CHASER_FINISH_RANGE_CM", 260.0)
        self.finish_speed = self._read_float_env("SIM_CHASER_FINISH_SPEED", 235.0)
        self.finish_commit_sec = self._read_float_env("SIM_CHASER_FINISH_COMMIT_SEC", 0.8)
        self.min_z = self._read_float_env("SIMWORLD_DRONE_MIN_Z", self._read_float_env("SIM_DRONE_MIN_Z", 100.0))
        self.max_z = self._read_float_env("SIMWORLD_DRONE_MAX_Z", self._read_float_env("SIM_DRONE_MAX_Z", 700.0))
        if self.min_z > self.max_z:
            self.min_z, self.max_z = self.max_z, self.min_z
        self.tactical_blockers = read_tactical_blockers(self.min_z, self.max_z)
        self.cruise_z = self._clamp_z(self._read_float_env("SIM_CHASER_CRUISE_Z", 450.0))
        self.vertical_speed = self._read_float_env("SIM_CHASER_VERTICAL_SPEED", 170.0)
        self.mistake_chance = self._read_float_env("SIM_CHASER_MISTAKE_CHANCE", 0.18)
        self.pressure_hold_chance = self._read_float_env("SIM_CHASER_PRESSURE_HOLD_CHANCE", 0.35)
        self.pressure_speed_scale = self._read_float_env("SIM_CHASER_PRESSURE_SPEED_SCALE", 0.78)
        self.cutoff_bias_cm = self._read_float_env("SIM_CHASER_CUTOFF_BIAS_CM", 320.0)
        self.intercept_lead_sec = self._read_float_env("SIM_CHASER_INTERCEPT_LEAD_SEC", 0.8)
        self.stall_speed_threshold_cm_s = self._read_float_env("SIM_CHASER_STALL_SPEED_CM_S", 60.0)
        self.orbit_range_cm = self._read_float_env("SIM_CHASER_ORBIT_RANGE_CM", 850.0)
        self.orbit_bias_cm = self._read_float_env("SIM_CHASER_ORBIT_BIAS_CM", 260.0)
        self.orbit_commit_sec = self._read_float_env("SIM_CHASER_ORBIT_COMMIT_SEC", 2.4)
        self.heat_max = self._read_float_env("SIM_CHASER_HEAT_MAX", 100.0)
        self.heat_cool_per_sec = self._read_float_env("SIM_CHASER_HEAT_COOL_PER_SEC", 14.0)
        self.heat_intercept_per_sec = self._read_float_env("SIM_CHASER_INTERCEPT_HEAT_PER_SEC", 11.0)
        self.heat_finish_per_sec = self._read_float_env("SIM_CHASER_FINISH_HEAT_PER_SEC", 18.0)
        self.overheated_speed_scale = self._read_float_env("SIM_CHASER_OVERHEATED_SPEED_SCALE", 0.72)

        self.ollama_enabled = os.environ.get("SIM_CHASER_USE_OLLAMA", os.environ.get("USE_OLLAMA", "1")) != "0"
        self.ollama_model = os.environ.get("SIM_CHASER_OLLAMA_MODEL", os.environ.get("OLLAMA_MODEL", "gpt-oss:latest"))
        self.ollama_urls = self._read_ollama_urls()
        self.ollama_timeout = self._read_float_env("OLLAMA_TIMEOUT_SEC", 20.0)
        self.ollama_decision_cooldown_sec = self._read_float_env("SIM_CHASER_OLLAMA_COOLDOWN_SEC", 2.0)
        self.ollama_failure_backoff_sec = self._read_float_env("SIM_CHASER_OLLAMA_FAILURE_BACKOFF_SEC", 8.0)
        self.ollama_max_backoff_sec = self._read_float_env("SIM_CHASER_OLLAMA_MAX_BACKOFF_SEC", 60.0)
        self.ollama_num_ctx = int(self._read_float_env("SIM_CHASER_OLLAMA_NUM_CTX", 512.0))
        self.ollama_num_predict = int(self._read_float_env("SIM_CHASER_OLLAMA_NUM_PREDICT", 512.0))
        self.ollama_num_gpu = int(self._read_float_env("SIM_CHASER_OLLAMA_NUM_GPU", -1.0))

        self.rng = random.Random(int(self._read_float_env("SIM_CHASER_RANDOM_SEED", 24)))

        self.target_x = None
        self.target_y = None
        self.target_z = None
        self.self_x = None
        self.self_y = None
        self.self_z = self.cruise_z
        self.target_vx = 0.0
        self.target_vy = 0.0
        self.prev_target_x = None
        self.prev_target_y = None
        self.prev_target_t = None
        self.reported_ready = False
        self.is_catching = False
        self.started = False

        self.last_seen_x = None
        self.last_seen_y = None
        self.last_seen_at = None
        self.last_visibility_state = None
        self.last_visibility_reason = "unknown"
        self.last_visibility_distance = None
        self.last_target_visible = False
        self.lock_x = None
        self.lock_y = None
        self.lock_updated_at = 0.0
        self.commit_until = 0.0
        self.current_heading_x = 1.0
        self.current_heading_y = 0.0
        self.cached_tactic = "chase_direct"
        self.cached_strategy = "shadow_until_close"
        self.cached_tactic_at = 0.0
        self.pending_ollama_error = None
        self.ollama_executor = ThreadPoolExecutor(max_workers=1)
        self.ollama_future = None
        self.last_ollama_request_at = 0.0
        self.ollama_failure_count = 0
        self.ollama_disabled_until = 0.0
        self.finish_until = 0.0
        self.orbit_until = 0.0
        self.orbit_sign = 1.0
        self.heat = 0.0
        self.last_heat_update_at = time.time()
        self.allowed_ollama_tactics = (
            "chase_direct",
            "intercept",
            "cutoff_left",
            "cutoff_right",
            "pressure",
            "search_last_seen",
            "orbit_pincer",
        )
        self.allowed_ollama_strategies = (
            "herd_to_boundary",
            "shadow_until_close",
            "fake_left_cut_right",
            "predict_and_camp",
            "deny_center",
            "spiral_search",
            "encircle_stalled",
        )

        self.timer = self.create_timer(self.tick_dt, self.control_loop)

    def _clamp_z(self, z: float) -> float:
        return max(self.min_z, min(self.max_z, float(z)))

    def _read_float_env(self, name: str, default: float) -> float:
        env_value = os.environ.get(name)
        if env_value is not None:
            try:
                return float(env_value)
            except (TypeError, ValueError):
                pass
        value = self.declare_parameter(name, default).value
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _read_los_blockers(self) -> list[tuple[float, float, float]]:
        value = os.getenv("SIM_LOS_BLOCKERS", "")
        blockers = []
        for item in value.split(";"):
            if not item.strip():
                continue
            try:
                x_text, y_text, radius_text = item.split(",", 2)
                blockers.append((float(x_text), float(y_text), float(radius_text)))
            except ValueError:
                self.get_logger().warning(f"Invalid SIM_LOS_BLOCKERS item '{item}', expected x,y,radius")
        for item in os.getenv("SIM_COLLISION_BLOCKERS", "").split(";"):
            if not item.strip():
                continue
            try:
                parts = [float(part.strip()) for part in item.split(",")]
                if len(parts) not in {3, 5}:
                    raise ValueError("expected x,y,radius[,min_z,max_z]")
                blockers.append((parts[0], parts[1], parts[2]))
            except ValueError:
                self.get_logger().warning(
                    f"Invalid SIM_COLLISION_BLOCKERS item '{item}' for LOS, expected x,y,radius[,min_z,max_z]"
                )
        return blockers

    def _read_ollama_urls(self) -> list[str]:
        urls_value = os.environ.get("SIM_CHASER_OLLAMA_API_URLS", os.environ.get("OLLAMA_API_URLS"))
        if not urls_value:
            urls_value = os.environ.get("SIM_CHASER_OLLAMA_API_URL", os.environ.get("OLLAMA_API_URL"))
        if not urls_value:
            urls_value = "http://10.8.0.132:11434/api/generate"
        urls = [url.strip() for url in urls_value.split(",") if url.strip()]
        return urls or ["http://10.8.0.132:11434/api/generate"]

    def publish_status(self, text: str) -> None:
        msg = String()
        msg.data = text
        self.status_pub.publish(msg)
        self.get_logger().info(text)

    def target_pose_callback(self, msg: PoseStamped) -> None:
        now = time.time()
        new_x = msg.pose.position.x
        new_y = msg.pose.position.y
        new_z = self._clamp_z(msg.pose.position.z)

        if self.prev_target_x is not None and self.prev_target_t is not None:
            dt = max(1e-3, now - self.prev_target_t)
            self.target_vx = (new_x - self.prev_target_x) / dt
            self.target_vy = (new_y - self.prev_target_y) / dt

        self.target_x = new_x
        self.target_y = new_y
        self.target_z = new_z
        self.prev_target_x = new_x
        self.prev_target_y = new_y
        self.prev_target_t = now
        self._maybe_report_ready()

    def self_pose_callback(self, msg: PoseStamped) -> None:
        self.self_x = msg.pose.position.x
        self.self_y = msg.pose.position.y
        self.self_z = self._clamp_z(msg.pose.position.z)
        self._maybe_report_ready()

    def _maybe_report_ready(self) -> None:
        if self.reported_ready:
            return
        if self.target_x is None or self.self_x is None:
            return
        self.reported_ready = True
        self.publish_status(
            "Chaser brain ready: "
            f"base={self.base_speed:.1f}, intercept={self.intercept_speed:.1f}, search={self.search_speed:.1f}, "
            f"catch_distance={self.catch_distance:.1f}, reaction_delay={self.reaction_delay_sec:.2f}s, "
            f"ollama={int(self.ollama_enabled)}, ollama_model={self.ollama_model}, "
            f"ollama_urls={','.join(self.ollama_urls)}, z_range={self.min_z:.0f}-{self.max_z:.0f}, waiting_for_start=1"
        )

    def control_callback(self, msg: String) -> None:
        command = msg.data.strip().lower()
        if command in ("start", "start_b", "start_all"):
            if not self.started:
                self.started = True
                now = time.time()
                self.last_heat_update_at = now
                self.heat = 0.0
                self.commit_until = 0.0
                self.finish_until = 0.0
                self.publish_status(f"Chaser brain received {command.upper()}")
        elif command in ("stop", "stop_b", "stop_all"):
            self.started = False
            self.cmd_pub.publish(Twist())
            self.publish_status(f"Chaser brain received {command.upper()}")

    def _distance_to_target(self, x: float | None, y: float | None) -> float | None:
        if x is None or y is None or self.self_x is None or self.self_y is None:
            return None
        z = self.target_z if self.target_z is not None else self.self_z
        return math.sqrt((x - self.self_x) ** 2 + (y - self.self_y) ** 2 + (z - self.self_z) ** 2)

    def _recent_memory_available(self) -> bool:
        if self.last_seen_at is None or self.last_seen_x is None or self.last_seen_y is None:
            return False
        return (time.time() - self.last_seen_at) <= self.memory_timeout_sec

    def _line_intersects_circle(
        self,
        ax: float,
        ay: float,
        bx: float,
        by: float,
        cx: float,
        cy: float,
        radius: float,
    ) -> bool:
        dx = bx - ax
        dy = by - ay
        length_sq = dx * dx + dy * dy
        if length_sq <= 1e-6:
            return False
        t = ((cx - ax) * dx + (cy - ay) * dy) / length_sq
        t = max(0.0, min(1.0, t))
        closest_x = ax + t * dx
        closest_y = ay + t * dy
        return math.hypot(closest_x - cx, closest_y - cy) <= radius

    def _los_to_point(self, other_x: float, other_y: float, max_distance: float) -> tuple[bool, str, float]:
        if self.self_x is None or self.self_y is None:
            return False, "unknown", 0.0
        distance = math.hypot(self.self_x - other_x, self.self_y - other_y)
        if distance > max_distance:
            return False, "range", distance
        if self.los_enabled:
            for bx, by, radius in self.los_blockers:
                if self._line_intersects_circle(self.self_x, self.self_y, other_x, other_y, bx, by, radius):
                    return False, "blocked", distance
            if distance <= self.close_detect_range_cm:
                return True, "close", distance
            heading_len = math.hypot(self.current_heading_x, self.current_heading_y)
            if heading_len > 1e-6:
                to_x = (other_x - self.self_x) / max(distance, 1e-6)
                to_y = (other_y - self.self_y) / max(distance, 1e-6)
                hx = self.current_heading_x / heading_len
                hy = self.current_heading_y / heading_len
                dot = max(-1.0, min(1.0, hx * to_x + hy * to_y))
                angle_deg = math.degrees(math.acos(dot))
                if angle_deg > self.fov_deg * 0.5:
                    return False, "fov", distance
        if self.fake_occlusion_prob > 0.0 and self.rng.random() < self.fake_occlusion_prob:
            return False, "noise", distance
        return True, "clear", distance

    def _refresh_lock(self) -> None:
        now = time.time()
        if self.target_x is None or self.target_y is None:
            return
        if now - self.lock_updated_at < self.reaction_delay_sec:
            return
        self.lock_x = self.target_x
        self.lock_y = self.target_y
        self.lock_updated_at = now

    def _build_ollama_request(self, distance: float | None, target_visible: bool, target_mode: str) -> dict:
        payload_obj = {
            "self_x": round(self.self_x, 1) if self.self_x is not None else None,
            "self_y": round(self.self_y, 1) if self.self_y is not None else None,
            "target_x": round(self.target_x, 1) if self.target_x is not None else None,
            "target_y": round(self.target_y, 1) if self.target_y is not None else None,
            "target_vx": round(self.target_vx, 1),
            "target_vy": round(self.target_vy, 1),
            "distance_cm": round(distance, 1) if distance is not None else None,
            "catch_distance_cm": self.catch_distance,
            "target_visible": target_visible,
            "visibility_reason": self.last_visibility_reason,
            "heat_pct": round((self.heat / max(self.heat_max, 1.0)) * 100.0, 1),
            "thermal_state": self._thermal_state(),
            "target_mode": target_mode,
            "memory_available": self._recent_memory_available(),
            "arena_center_x": 0,
            "arena_center_y": 0,
            "current_strategy": self.cached_strategy,
            "current_tactic": self.cached_tactic,
        }
        system = (
            "You are a tactical controller for a blue chaser drone pursuing a red target drone. "
            "Pick a multi-step chase strategy and one immediate tactic. "
            "If the target is visible and barely moving at mid range, prefer encircle_stalled:orbit_pincer. "
            "If target_visible is false, prefer spiral_search:search_last_seen unless distance is very close. "
            "If visibility_reason is fov, prefer predict_and_camp:intercept to turn back toward the target. "
            "If visibility_reason is blocked, prefer spiral_search:search_last_seen or herd_to_boundary:cutoff_left. "
            "Valid strategies: herd_to_boundary, shadow_until_close, fake_left_cut_right, predict_and_camp, deny_center, spiral_search, encircle_stalled. "
            "Valid tactics: chase_direct, intercept, cutoff_left, cutoff_right, pressure, search_last_seen, orbit_pincer. "
            "Answer exactly as strategy:tactic with no explanation."
        )
        prompt = f"System:\n{system}\n\nUser:\n{json.dumps(payload_obj)}\n\nPlan:"
        options = {
            "temperature": 0.2,
            "num_ctx": max(128, self.ollama_num_ctx),
            "num_predict": max(16, self.ollama_num_predict),
        }
        if self.ollama_num_gpu >= 0:
            options["num_gpu"] = self.ollama_num_gpu
        return {
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "options": options,
        }

    def _infer_strategy_for_tactic(self, tactic: str) -> str:
        return {
            "intercept": "predict_and_camp",
            "cutoff_left": "herd_to_boundary",
            "cutoff_right": "herd_to_boundary",
            "pressure": "shadow_until_close",
            "search_last_seen": "spiral_search",
            "orbit_pincer": "encircle_stalled",
        }.get(tactic, "shadow_until_close")

    def _parse_ollama_plan(self, raw: str, default_tactic: str) -> dict:
        text = raw.strip()
        lower = text.lower()
        strategy = None
        tactic = None
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                parsed_strategy = str(parsed.get("strategy", "")).strip().lower()
                parsed_tactic = str(parsed.get("tactic", "")).strip().lower()
                if parsed_strategy in self.allowed_ollama_strategies:
                    strategy = parsed_strategy
                if parsed_tactic in self.allowed_ollama_tactics:
                    tactic = parsed_tactic
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    parsed = json.loads(text[start : end + 1])
                    parsed_strategy = str(parsed.get("strategy", "")).strip().lower()
                    parsed_tactic = str(parsed.get("tactic", "")).strip().lower()
                    if parsed_strategy in self.allowed_ollama_strategies:
                        strategy = parsed_strategy
                    if parsed_tactic in self.allowed_ollama_tactics:
                        tactic = parsed_tactic
                except (json.JSONDecodeError, AttributeError):
                    pass

        compact = lower.strip("`'\" \r\n\t.")
        if ":" in compact:
            left, right = compact.split(":", 1)
            left = left.strip()
            right = right.strip()
            if left in self.allowed_ollama_strategies:
                strategy = left
            if right in self.allowed_ollama_tactics:
                tactic = right
        elif compact in self.allowed_ollama_tactics:
            tactic = compact
        elif compact in self.allowed_ollama_strategies:
            strategy = compact

        for phrase in ("choose", "select", "use", "best tactic is", "tactic is", "answer is", "return"):
            for tactic in self.allowed_ollama_tactics:
                if f"{phrase} {tactic}" in lower:
                    return {"strategy": strategy or self._infer_strategy_for_tactic(tactic), "tactic": tactic}

        for candidate in self.allowed_ollama_strategies:
            if lower.rfind(candidate) >= 0:
                strategy = candidate
        for candidate in self.allowed_ollama_tactics:
            if lower.rfind(candidate) >= 0:
                tactic = candidate

        if tactic:
            return {"strategy": strategy or self._infer_strategy_for_tactic(tactic), "tactic": tactic}
        if strategy:
            tactic = {
                "herd_to_boundary": "cutoff_left",
                "shadow_until_close": "chase_direct",
                "fake_left_cut_right": "cutoff_right",
                "predict_and_camp": "intercept",
                "deny_center": "cutoff_left",
                "spiral_search": "search_last_seen",
                "encircle_stalled": "orbit_pincer",
            }.get(strategy, default_tactic)
            return {"strategy": strategy, "tactic": tactic}

        excerpt = text[:160].replace("\r", " ").replace("\n", " ")
        raise RuntimeError(f"Ollama returned no allowed strategy/tactic: {excerpt!r}")

    def _ollama_request_worker(self, body: dict) -> dict:
        errors = []
        for url in self.ollama_urls:
            try:
                response = requests.post(url, json=body, timeout=max(1.0, self.ollama_timeout))
                try:
                    response.raise_for_status()
                except requests.exceptions.HTTPError as exc:
                    detail = response.text.strip().replace("\r", " ").replace("\n", " ")
                    if len(detail) > 260:
                        detail = detail[:257] + "..."
                    if detail:
                        raise RuntimeError(f"{url} HTTP {response.status_code}: {detail}") from exc
                    raise RuntimeError(f"{url} HTTP {response.status_code}") from exc
                outer = response.json()
                raw = outer.get("response", "") if isinstance(outer, dict) else ""
                if not raw and isinstance(outer, dict):
                    raw = outer.get("thinking", "")
                if not raw:
                    done_reason = outer.get("done_reason", "unknown") if isinstance(outer, dict) else "unknown"
                    raise RuntimeError(f"{url} empty response; done_reason={done_reason}")
                return self._parse_ollama_plan(raw, "chase_direct")
            except Exception as exc:
                errors.append(str(exc))
        raise RuntimeError("Ollama endpoints failed: " + " | ".join(errors))

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
            result = self.ollama_future.result()
            self.cached_tactic = result.get("tactic", "chase_direct")
            self.cached_strategy = result.get("strategy", self._infer_strategy_for_tactic(self.cached_tactic))
            self.cached_tactic_at = time.time()
            self.ollama_failure_count = 0
            self.ollama_disabled_until = 0.0
            self.publish_status(f"Chaser brain cached Ollama strategy={self.cached_strategy} tactic={self.cached_tactic}")
        except Exception as exc:
            self._record_ollama_failure(exc)
        finally:
            self.ollama_future = None

    def _maybe_schedule_ollama(self, distance: float | None, target_visible: bool, target_mode: str) -> None:
        if not self.ollama_enabled:
            return
        if self.ollama_future is not None:
            return
        now = time.time()
        if now < self.ollama_disabled_until:
            return
        if now - self.last_ollama_request_at < self.ollama_decision_cooldown_sec:
            return
        body = self._build_ollama_request(distance, target_visible, target_mode)
        self.ollama_future = self.ollama_executor.submit(self._ollama_request_worker, body)
        self.last_ollama_request_at = now

    def _estimate_target_mode(self, distance: float | None) -> str:
        if distance is None:
            return "unknown"
        if distance <= 500.0:
            return "panic"
        if distance <= 1500.0:
            return "evade"
        return "patrol"

    def _target_visible(self) -> bool:
        if self.target_x is None or self.target_y is None:
            return False
        visible, reason, distance = self._los_to_point(self.target_x, self.target_y, self.visible_range_cm)
        self.last_visibility_reason = reason
        self.last_visibility_distance = distance
        self.last_target_visible = visible
        if self.last_visibility_state is not None and self.last_visibility_state != visible:
            state = "regained sight of target" if visible else f"lost sight of target ({reason})"
            self.publish_status(f"Chaser brain visibility: {state}, distance_cm={distance:.1f}")
        self.last_visibility_state = visible
        if visible:
            self.last_seen_x = self.target_x
            self.last_seen_y = self.target_y
            self.last_seen_at = time.time()
        return visible

    def _thermal_state(self) -> str:
        if self.heat >= self.heat_max:
            return "overheated"
        if self.heat >= self.heat_max * 0.72:
            return "hot"
        if self.heat <= self.heat_max * 0.25:
            return "cool"
        return "warm"

    def _update_heat(self, tactic: str | None = None) -> None:
        now = time.time()
        dt = max(0.0, now - self.last_heat_update_at)
        self.last_heat_update_at = now
        if dt <= 0.0:
            return
        heat_delta = -self.heat_cool_per_sec * dt
        if tactic in ("intercept", "cutoff_left", "cutoff_right"):
            heat_delta = self.heat_intercept_per_sec * dt
        elif tactic == "finish_commit":
            heat_delta = self.heat_finish_per_sec * dt
        elif tactic == "orbit_pincer":
            heat_delta = self.heat_intercept_per_sec * 0.75 * dt
        elif tactic == "chase_direct":
            heat_delta = -self.heat_cool_per_sec * 0.35 * dt
        elif tactic == "pressure":
            heat_delta = -self.heat_cool_per_sec * 0.65 * dt
        elif tactic == "search_last_seen":
            heat_delta = -self.heat_cool_per_sec * dt
        self.heat = max(0.0, min(self.heat_max, self.heat + heat_delta))

    def _apply_heat_limit(self, tactic: str, speed: float) -> float:
        self._update_heat(tactic)
        if self.heat >= self.heat_max:
            return min(speed, self.base_speed) * self.overheated_speed_scale
        if self.heat >= self.heat_max * 0.85 and tactic in (
            "intercept",
            "cutoff_left",
            "cutoff_right",
            "finish_commit",
            "orbit_pincer",
        ):
            return min(speed, self.base_speed)
        return speed

    def _target_speed_cm_s(self) -> float:
        return math.hypot(self.target_vx, self.target_vy)

    def _should_orbit_pincer(self, distance: float | None) -> bool:
        if distance is None:
            return False
        if distance <= self.finish_range_cm or distance > self.orbit_range_cm:
            return False
        return self._target_speed_cm_s() <= self.stall_speed_threshold_cm_s

    def _prepare_orbit_pincer(self) -> None:
        now = time.time()
        if now < self.orbit_until:
            return
        self.orbit_until = now + self.orbit_commit_sec
        to_target_x = (self.target_x or 0.0) - (self.self_x or 0.0)
        to_target_y = (self.target_y or 0.0) - (self.self_y or 0.0)
        cross = to_target_x * self.target_vy - to_target_y * self.target_vx
        if abs(cross) > 1e-3:
            self.orbit_sign = -1.0 if cross > 0.0 else 1.0
        else:
            self.orbit_sign = -self.orbit_sign if self.orbit_sign else self.rng.choice([-1.0, 1.0])

    def _choose_tactic(self, distance: float | None) -> str:
        self._harvest_ollama_result()
        if self.pending_ollama_error:
            self.publish_status(f"Chaser brain Ollama fallback: {self.pending_ollama_error}")
            self.pending_ollama_error = None

        visible = self._target_visible()
        target_mode = self._estimate_target_mode(distance)
        self._maybe_schedule_ollama(distance, visible, target_mode)

        if not visible:
            return "search_last_seen"

        if self.heat >= self.heat_max * 0.85 and distance is not None and distance > self.catch_distance * 1.2:
            return "pressure"
        if self.heat >= self.heat_max * 0.96 and distance is not None and distance <= self.finish_range_cm:
            return "pressure"

        if distance is not None and distance <= self.finish_range_cm:
            self.finish_until = time.time() + self.finish_commit_sec
            if self.rng.random() < self.pressure_hold_chance:
                return "pressure"
            return "finish_commit"

        if self._should_orbit_pincer(distance):
            self._prepare_orbit_pincer()
            return "orbit_pincer"

        tactic_age = time.time() - self.cached_tactic_at
        if self.cached_tactic and tactic_age <= self.tactic_ttl_sec:
            tactic = self.cached_tactic
        elif distance is not None and distance > 1200.0:
            tactic = "intercept"
        else:
            tactic = "chase_direct"

        if tactic == "orbit_pincer" and not self._should_orbit_pincer(distance):
            tactic = "intercept" if distance is not None and distance > self.finish_range_cm else "finish_commit"

        if distance is not None and distance > self.finish_range_cm:
            if self.rng.random() < self.mistake_chance:
                tactic = self.rng.choice(["cutoff_left", "cutoff_right", "search_last_seen"])
            elif distance > 1400.0 and self.rng.random() < 0.45:
                tactic = self.rng.choice(["intercept", "cutoff_left", "cutoff_right"])
            elif distance < 800.0 and self.rng.random() < 0.25:
                tactic = self.rng.choice(["pressure", "cutoff_left", "cutoff_right"])

        if self.cached_strategy == "deny_center" and self.target_x is not None and self.target_y is not None:
            tactic = "cutoff_left" if self.target_y >= 0 else "cutoff_right"
        elif self.cached_strategy == "fake_left_cut_right":
            tactic = "cutoff_right" if tactic == "cutoff_left" else "cutoff_left"
        elif self.cached_strategy == "predict_and_camp" and distance is not None and distance > self.finish_range_cm:
            tactic = "intercept"
        elif self.cached_strategy == "encircle_stalled" and self._should_orbit_pincer(distance):
            self._prepare_orbit_pincer()
            tactic = "orbit_pincer"
        elif self.cached_strategy == "spiral_search" and not visible:
            tactic = "search_last_seen"

        if self.heat >= self.heat_max * 0.85 and tactic in ("intercept", "cutoff_left", "cutoff_right", "orbit_pincer"):
            tactic = "pressure"

        return tactic

    def _normalize(self, vx: float, vy: float) -> tuple[float, float]:
        length = math.hypot(vx, vy) or 1.0
        return vx / length, vy / length

    def _rotate(self, vx: float, vy: float, angle_rad: float) -> tuple[float, float]:
        return (
            vx * math.cos(angle_rad) - vy * math.sin(angle_rad),
            vx * math.sin(angle_rad) + vy * math.cos(angle_rad),
        )

    def _apply_turn_limit(self, desired_x: float, desired_y: float) -> tuple[float, float]:
        desired_x, desired_y = self._normalize(desired_x, desired_y)
        current_angle = math.atan2(self.current_heading_y, self.current_heading_x)
        desired_angle = math.atan2(desired_y, desired_x)
        delta = desired_angle - current_angle
        while delta > math.pi:
            delta -= 2.0 * math.pi
        while delta < -math.pi:
            delta += 2.0 * math.pi
        max_turn = math.radians(self.turn_rate_deg) * self.tick_dt
        delta = max(-max_turn, min(max_turn, delta))
        next_angle = current_angle + delta
        self.current_heading_x = math.cos(next_angle)
        self.current_heading_y = math.sin(next_angle)
        return self.current_heading_x, self.current_heading_y

    def _desired_heading_from_tactic(self, tactic: str) -> tuple[float, float, float]:
        target_x = self.target_x
        target_y = self.target_y
        speed = self.base_speed

        if tactic == "search_last_seen" and self._recent_memory_available():
            angle = (time.time() * 1.3) % (2.0 * math.pi)
            target_x = self.last_seen_x + math.cos(angle) * self.search_radius_cm
            target_y = self.last_seen_y + math.sin(angle) * self.search_radius_cm
            speed = self.search_speed
        elif tactic == "search_last_seen":
            angle = (time.time() * 0.9) % (2.0 * math.pi)
            target_x = (self.self_x or 0.0) + math.cos(angle) * self.search_radius_cm
            target_y = (self.self_y or 0.0) + math.sin(angle) * self.search_radius_cm
            speed = self.search_speed

        elif tactic == "intercept" and self.target_x is not None and self.target_y is not None:
            lead_time = self.intercept_lead_sec
            target_x = self.target_x + self.target_vx * lead_time
            target_y = self.target_y + self.target_vy * lead_time
            speed = self.intercept_speed

        elif tactic in ("cutoff_left", "cutoff_right") and self.target_x is not None and self.target_y is not None:
            vx = self.target_x - (self.self_x or 0.0)
            vy = self.target_y - (self.self_y or 0.0)
            vx, vy = self._normalize(vx, vy)
            sign = 1.0 if tactic.endswith("left") else -1.0
            vx, vy = self._rotate(vx, vy, sign * math.radians(35.0))
            target_x = (self.target_x or 0.0) + vx * self.cutoff_bias_cm
            target_y = (self.target_y or 0.0) + vy * self.cutoff_bias_cm
            speed = self.intercept_speed

        elif tactic == "orbit_pincer" and self.target_x is not None and self.target_y is not None:
            to_target_x = self.target_x - (self.self_x or 0.0)
            to_target_y = self.target_y - (self.self_y or 0.0)
            to_target_x, to_target_y = self._normalize(to_target_x, to_target_y)
            tangent_x, tangent_y = self._rotate(to_target_x, to_target_y, self.orbit_sign * math.pi * 0.5)
            target_x = self.target_x + tangent_x * self.orbit_bias_cm
            target_y = self.target_y + tangent_y * self.orbit_bias_cm
            speed = self.intercept_speed * 0.92

        elif tactic == "pressure":
            speed = self.base_speed * self.pressure_speed_scale

        elif tactic == "finish_commit":
            speed = self.finish_speed

        if target_x is None or target_y is None or self.self_x is None or self.self_y is None:
            return self.current_heading_x, self.current_heading_y, speed

        routed_x, routed_y, route_reason = route_around_blockers(
            (self.self_x, self.self_y, self.self_z),
            (target_x, target_y),
            self.tactical_blockers,
            self.tactical_clearance,
        )
        if route_reason is not None:
            target_x, target_y = routed_x, routed_y

        desired_x = target_x - self.self_x
        desired_y = target_y - self.self_y

        noise_scale = 1.0
        if tactic == "finish_commit":
            noise_scale = 0.35
        elif tactic == "pressure":
            noise_scale = 1.25
        elif tactic == "search_last_seen":
            noise_scale = 1.4
        elif tactic == "orbit_pincer":
            noise_scale = 0.45

        noise_x = self.rng.uniform(-self.aim_noise_cm, self.aim_noise_cm) * noise_scale
        noise_y = self.rng.uniform(-self.aim_noise_cm, self.aim_noise_cm) * noise_scale
        desired_x += noise_x
        desired_y += noise_y

        heading_x, heading_y = self._apply_turn_limit(desired_x, desired_y)
        return heading_x, heading_y, speed

    def _desired_altitude_for_tactic(self, tactic: str) -> float:
        if tactic == "search_last_seen" or self.target_z is None:
            return self.cruise_z
        if tactic in ("intercept", "finish_commit", "chase_direct", "orbit_pincer"):
            return self._clamp_z(self.target_z)
        if tactic == "pressure":
            return self._clamp_z((self.target_z + self.cruise_z) * 0.5)
        return self._clamp_z(self.target_z)

    def _vertical_velocity(self, tactic: str) -> float:
        desired_z = self._desired_altitude_for_tactic(tactic)
        error = desired_z - self.self_z
        if abs(error) < 5.0:
            return 0.0
        return max(-self.vertical_speed, min(self.vertical_speed, error / max(self.tick_dt, 1e-3)))

    def control_loop(self) -> None:
        if self.target_x is None or self.self_x is None:
            return
        if not self.started:
            self.cmd_pub.publish(Twist())
            return

        distance = self._distance_to_target(self.target_x, self.target_y)
        if distance is not None and distance <= self.catch_distance:
            if not self.is_catching:
                self.publish_status(f"Chaser brain catch zone reached at distance={distance:.1f}")
                self.is_catching = True
            self.cmd_pub.publish(Twist())
            return

        self.is_catching = False
        now = time.time()
        if now >= self.commit_until:
            tactic = self._choose_tactic(distance)
            self.cached_tactic = tactic
            if tactic == "search_last_seen":
                self.cached_strategy = "spiral_search"
            elif tactic == "intercept":
                self.cached_strategy = "predict_and_camp"
            elif tactic.startswith("cutoff"):
                self.cached_strategy = "herd_to_boundary"
            elif tactic == "orbit_pincer":
                self.cached_strategy = "encircle_stalled"
            self.cached_tactic_at = now
            self.commit_until = now + (self.finish_commit_sec if tactic == "finish_commit" else self.commit_sec)
            visible = int(self.last_target_visible)
            seen_distance = self.last_visibility_distance if self.last_visibility_distance is not None else distance
            self.publish_status(
                "Chaser brain commit "
                f"strategy={self.cached_strategy} tactic={tactic}, visible={visible}, "
                f"visibility_reason={self.last_visibility_reason}, "
                f"distance_cm={seen_distance if seen_distance is not None else 'unknown'}, "
                f"heat={self.heat:.1f}, thermal={self._thermal_state()}"
            )

        if now < self.finish_until and (self.cached_tactic in ("pressure", "chase_direct")):
            self.cached_tactic = "pressure" if self.heat >= self.heat_max * 0.85 else "finish_commit"

        tactic = self.cached_tactic or "chase_direct"
        heading_x, heading_y, speed = self._desired_heading_from_tactic(tactic)
        speed = self._apply_heat_limit(tactic, speed)

        cmd = Twist()
        cmd.linear.x = heading_x * speed
        cmd.linear.y = heading_y * speed
        cmd.linear.z = self._vertical_velocity(tactic)
        self.cmd_pub.publish(cmd)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ChaserBrain()
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
