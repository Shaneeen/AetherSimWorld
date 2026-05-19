import json
import math
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor

import requests
import rclpy
from rclpy.node import Node

from geometry_msgs.msg import PoseStamped
from geometry_msgs.msg import Twist
from std_msgs.msg import String


class TargetBrain(Node):
    def __init__(self) -> None:
        super().__init__("target_brain")

        self.cmd_pub = self.create_publisher(Twist, "/drone_a/cmd_vel", 10)
        self.status_pub = self.create_publisher(String, "/sim/status", 20)
        self.pose_sub = self.create_subscription(
            PoseStamped,
            "/drone_a/pose",
            self.pose_callback,
            10,
        )
        self.chaser_pose_sub = self.create_subscription(
            PoseStamped,
            "/drone_b/pose",
            self.chaser_pose_callback,
            10,
        )
        self.control_sub = self.create_subscription(
            String,
            "/drone_a/control",
            self.control_callback,
            10,
        )
        self.reset_sub = self.create_subscription(
            String,
            "/sim/reset_chase",
            self.reset_callback,
            10,
        )

        self.rng = random.Random(int(self._read_float_env("SIM_TARGET_RANDOM_SEED", 42)))

        legacy_target_speed = self._read_float_env("SIM_TARGET_SPEED", 220.0)
        self.cruise_speed = self._read_float_env("SIM_TARGET_CRUISE_SPEED", legacy_target_speed)
        self.evade_speed = self._read_float_env("SIM_TARGET_EVADE_SPEED", legacy_target_speed + 45.0)
        self.burst_speed = self._read_float_env("SIM_TARGET_BURST_SPEED", legacy_target_speed + 115.0)
        self.move_sec = self._read_float_env("SIM_TARGET_MOVE_SEC", 2.0)
        self.rest_sec = self._read_float_env("SIM_TARGET_REST_SEC", 1.0)
        self.bounds_x = self._read_float_env("SIM_TARGET_BOUND_X", 1800.0)
        self.bounds_y = self._read_float_env("SIM_TARGET_BOUND_Y", 1800.0)
        self.tick_dt = self._read_float_env("SIM_TARGET_DT", 0.1)
        self.min_z = self._read_float_env("SIMWORLD_DRONE_MIN_Z", self._read_float_env("SIM_DRONE_MIN_Z", 100.0))
        self.max_z = self._read_float_env("SIMWORLD_DRONE_MAX_Z", self._read_float_env("SIM_DRONE_MAX_Z", 700.0))
        if self.min_z > self.max_z:
            self.min_z, self.max_z = self.max_z, self.min_z
        self.cruise_z = self._clamp_z(self._read_float_env("SIM_TARGET_CRUISE_Z", 450.0))
        self.vertical_speed = self._read_float_env("SIM_TARGET_VERTICAL_SPEED", 150.0)
        self.altitude_step = self._read_float_env("SIM_TARGET_ALTITUDE_STEP", 180.0)

        self.visible_range_cm = self._read_float_env("SIM_TARGET_VISIBLE_RANGE_CM", 5000.0)
        self.los_enabled = os.environ.get("SIM_LOS_ENABLED", "1").lower() not in {"0", "false", "no"}
        self.fake_occlusion_prob = self._read_float_env("SIM_TARGET_FAKE_OCCLUSION_PROB", 0.0)
        self.fov_deg = self._read_float_env("SIM_TARGET_FOV_DEG", 220.0)
        self.close_detect_range_cm = self._read_float_env("SIM_TARGET_CLOSE_DETECT_RANGE_CM", 220.0)
        self.proximity_detect_range_cm = self._read_float_env("SIM_TARGET_PROXIMITY_DETECT_RANGE_CM", 750.0)
        self.los_blockers = self._read_los_blockers()
        self.memory_timeout_sec = self._read_float_env("SIM_TARGET_MEMORY_TIMEOUT_SEC", 6.0)

        self.alert_range_cm = self._read_float_env("SIM_TARGET_ALERT_RANGE_CM", 2200.0)
        self.panic_range_cm = self._read_float_env("SIM_TARGET_PANIC_RANGE_CM", 650.0)
        self.proactive_range_cm = self._read_float_env("SIM_TARGET_PROACTIVE_RANGE_CM", 2600.0)
        self.burst_sec = self._read_float_env("SIM_TARGET_BURST_SEC", 2.0)
        self.burst_cooldown_sec = self._read_float_env("SIM_TARGET_BURST_COOLDOWN_SEC", 5.0)
        self.stamina_max = self._read_float_env("SIM_TARGET_STAMINA_MAX", 100.0)
        self.stamina_regen_per_sec = self._read_float_env("SIM_TARGET_STAMINA_REGEN_PER_SEC", 8.0)
        self.burst_stamina_cost = self._read_float_env("SIM_TARGET_BURST_STAMINA_COST", 38.0)
        self.burst_stamina_drain_per_sec = self._read_float_env("SIM_TARGET_BURST_STAMINA_DRAIN_PER_SEC", 12.0)
        self.min_burst_stamina = self._read_float_env("SIM_TARGET_MIN_BURST_STAMINA", 45.0)
        self.exhausted_speed_scale = self._read_float_env("SIM_TARGET_EXHAUSTED_SPEED_SCALE", 0.82)
        self.tactic_ttl_sec = self._read_float_env("SIM_TARGET_TACTIC_TTL_SEC", 4.0)
        self.stuck_speed_threshold_cm_s = self._read_float_env("SIM_TARGET_STUCK_SPEED_THRESHOLD_CM_S", 65.0)
        self.stuck_command_threshold_cm_s = self._read_float_env("SIM_TARGET_STUCK_COMMAND_THRESHOLD_CM_S", 80.0)
        self.stuck_after_sec = self._read_float_env("SIM_TARGET_STUCK_AFTER_SEC", 0.8)
        self.unstuck_sec = self._read_float_env("SIM_TARGET_UNSTUCK_SEC", 3.0)
        self.stuck_start_grace_sec = self._read_float_env("SIM_TARGET_STUCK_START_GRACE_SEC", 2.5)

        self.ollama_enabled = os.environ.get("SIM_TARGET_USE_OLLAMA", os.environ.get("USE_OLLAMA", "1")) != "0"
        self.ollama_model = os.environ.get("SIM_TARGET_OLLAMA_MODEL", os.environ.get("OLLAMA_MODEL", "gpt-oss:latest"))
        self.ollama_urls = self._read_ollama_urls()
        self.ollama_timeout = self._read_float_env("OLLAMA_TIMEOUT_SEC", 20.0)
        self.ollama_decision_cooldown_sec = self._read_float_env("SIM_TARGET_OLLAMA_COOLDOWN_SEC", 2.0)
        self.ollama_failure_backoff_sec = self._read_float_env("SIM_TARGET_OLLAMA_FAILURE_BACKOFF_SEC", 8.0)
        self.ollama_max_backoff_sec = self._read_float_env("SIM_TARGET_OLLAMA_MAX_BACKOFF_SEC", 60.0)
        self.ollama_num_ctx = int(self._read_float_env("SIM_TARGET_OLLAMA_NUM_CTX", 512.0))
        self.ollama_num_predict = int(self._read_float_env("SIM_TARGET_OLLAMA_NUM_PREDICT", 512.0))
        self.ollama_num_gpu = int(self._read_float_env("SIM_TARGET_OLLAMA_NUM_GPU", -1.0))

        self.current_x = 0.0
        self.current_y = 0.0
        self.current_z = self.cruise_z
        self.prev_x = None
        self.prev_y = None
        self.prev_pose_at = None
        self.actual_speed_cm_s = 0.0
        self.chaser_x = None
        self.chaser_y = None
        self.chaser_z = None
        self.heading_x = 0.0
        self.heading_y = 0.0
        self.target_z = self.cruise_z
        self.altitude_tactic = "level"
        self.current_speed = self.cruise_speed
        self.phase = "rest"
        self.phase_time_left = self.rest_sec
        self.announced_ready = False
        self.started = False
        self.last_seen_distance = None
        self.last_seen_x = None
        self.last_seen_y = None
        self.last_seen_at = None
        self.last_visibility_state = None
        self.last_visibility_reason = "unknown"
        self.cached_tactic = None
        self.cached_strategy = "keep_distance"
        self.cached_tactic_at = 0.0
        self.pending_ollama_error = None
        self.ollama_executor = ThreadPoolExecutor(max_workers=1)
        self.ollama_future = None
        self.last_ollama_request_at = 0.0
        self.ollama_failure_count = 0
        self.ollama_disabled_until = 0.0
        self.burst_until = 0.0
        self.burst_cooldown_until = 0.0
        self.stamina = self.stamina_max
        self.last_stamina_update_at = time.time()
        self.last_boost_state = "ready"
        self.threat_state = "patrol"
        self._last_zigzag_sign = 1.0
        self.last_distance_trend = 0.0
        self.stuck_started_at = None
        self.unstuck_until = 0.0
        self.unstuck_heading_x = 0.0
        self.unstuck_heading_y = 1.0
        self.started_at = 0.0
        self.last_unstuck_status_at = 0.0
        self.short_tactic_ttl = min(self.tactic_ttl_sec, 1.4)
        self.allowed_ollama_tactics = (
            "flee_direct",
            "veer_left",
            "veer_right",
            "juke_left",
            "juke_right",
            "zigzag_left",
            "zigzag_right",
            "burst_escape",
            "random_escape",
        )
        self.allowed_ollama_strategies = (
            "keep_distance",
            "break_line_of_sight",
            "reverse_when_overcommitted",
            "wide_arc_escape",
            "tempo_change",
            "force_overshoot",
        )

        self.timer = self.create_timer(self.tick_dt, self.control_loop)

    def _clamp_z(self, z: float) -> float:
        return max(self.min_z, min(self.max_z, float(z)))

    def _reset_runtime_state(self, reset_energy: bool = True) -> None:
        self.prev_x = None
        self.prev_y = None
        self.prev_pose_at = None
        self.actual_speed_cm_s = 0.0
        self.phase = "rest"
        self.phase_time_left = self.rest_sec
        self.last_seen_distance = None
        self.last_seen_x = None
        self.last_seen_y = None
        self.last_seen_at = None
        self.last_visibility_state = None
        self.last_visibility_reason = "unknown"
        self.cached_tactic = None
        self.cached_strategy = "keep_distance"
        self.cached_tactic_at = 0.0
        self.burst_until = 0.0
        self.burst_cooldown_until = 0.0
        if reset_energy:
            self.stamina = self.stamina_max
            self.last_boost_state = "ready"
        self.threat_state = "patrol"
        self.last_distance_trend = 0.0
        self.stuck_started_at = None
        self.unstuck_until = 0.0
        self.last_unstuck_status_at = 0.0
        self.heading_x = 0.0
        self.heading_y = 0.0
        self.target_z = self._clamp_z(self.current_z)
        self.altitude_tactic = "level"
        self.current_speed = self.cruise_speed

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
        return blockers

    def _read_ollama_urls(self) -> list[str]:
        urls_value = os.environ.get("SIM_TARGET_OLLAMA_API_URLS", os.environ.get("OLLAMA_API_URLS"))
        if not urls_value:
            urls_value = os.environ.get("SIM_TARGET_OLLAMA_API_URL", os.environ.get("OLLAMA_API_URL"))
        if not urls_value:
            urls_value = "http://10.8.0.132:11434/api/generate"
        urls = [url.strip() for url in urls_value.split(",") if url.strip()]
        return urls or ["http://10.8.0.132:11434/api/generate"]

    def publish_status(self, text: str) -> None:
        msg = String()
        msg.data = text
        self.status_pub.publish(msg)
        self.get_logger().info(text)

    def pose_callback(self, msg: PoseStamped) -> None:
        now = time.time()
        new_x = msg.pose.position.x
        new_y = msg.pose.position.y
        if self.prev_x is not None and self.prev_pose_at is not None:
            dt = max(1e-3, now - self.prev_pose_at)
            self.actual_speed_cm_s = math.hypot(new_x - self.prev_x, new_y - self.prev_y) / dt
        self.prev_x = new_x
        self.prev_y = new_y
        self.prev_pose_at = now
        self.current_x = msg.pose.position.x
        self.current_y = msg.pose.position.y
        self.current_z = self._clamp_z(msg.pose.position.z)
        if not self.announced_ready:
            self.publish_status(
                "Target brain ready: "
                f"cruise={self.cruise_speed:.1f}, evade={self.evade_speed:.1f}, burst={self.burst_speed:.1f}, "
                f"move={self.move_sec:.1f}s, rest={self.rest_sec:.1f}s, ollama={int(self.ollama_enabled)}, "
                f"ollama_model={self.ollama_model}, ollama_urls={','.join(self.ollama_urls)}, "
                f"alert_range_cm={self.alert_range_cm:.1f}, panic_range_cm={self.panic_range_cm:.1f}, "
                f"z_range={self.min_z:.0f}-{self.max_z:.0f}, waiting_for_start=1"
            )
            self.announced_ready = True

    def chaser_pose_callback(self, msg: PoseStamped) -> None:
        self.chaser_x = msg.pose.position.x
        self.chaser_y = msg.pose.position.y
        self.chaser_z = self._clamp_z(msg.pose.position.z)

    def control_callback(self, msg: String) -> None:
        command = msg.data.strip().lower()
        if command in ("start", "start_a", "start_all"):
            self._reset_runtime_state(reset_energy=True)
            self.started = True
            self.phase = "move"
            self.phase_time_left = self.move_sec
            now = time.time()
            self.started_at = now
            self.last_stamina_update_at = now
            self.choose_heading(force=True)
            self.publish_status(f"Target brain received {command.upper()}")
        elif command in ("stop", "stop_a", "stop_all"):
            self.started = False
            self._reset_runtime_state(reset_energy=False)
            self.cmd_pub.publish(Twist())
            self.publish_status(f"Target brain received {command.upper()}")

    def reset_callback(self, msg: String) -> None:
        command = msg.data.strip().lower()
        if command in ("reset", "reset_chase", "randomize", "randomize_start"):
            self.started = False
            self._reset_runtime_state(reset_energy=True)
            self.cmd_pub.publish(Twist())
            self.publish_status("Target brain reset runtime state")

    def _distance_to_chaser(self) -> float | None:
        if self.chaser_x is None or self.chaser_y is None:
            return None
        chaser_z = self.chaser_z if self.chaser_z is not None else self.current_z
        return math.sqrt(
            (self.current_x - self.chaser_x) ** 2
            + (self.current_y - self.chaser_y) ** 2
            + (self.current_z - chaser_z) ** 2
        )

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
        distance = math.hypot(self.current_x - other_x, self.current_y - other_y)
        if distance > max_distance:
            return False, "range", distance
        if self.los_enabled:
            for bx, by, radius in self.los_blockers:
                if self._line_intersects_circle(self.current_x, self.current_y, other_x, other_y, bx, by, radius):
                    return False, "blocked", distance
            if distance <= self.close_detect_range_cm:
                return True, "close", distance
            if distance <= self.proximity_detect_range_cm:
                return True, "proximity", distance
            heading_len = math.hypot(self.heading_x, self.heading_y)
            if heading_len > 1e-6:
                to_x = (other_x - self.current_x) / max(distance, 1e-6)
                to_y = (other_y - self.current_y) / max(distance, 1e-6)
                hx = self.heading_x / heading_len
                hy = self.heading_y / heading_len
                dot = max(-1.0, min(1.0, hx * to_x + hy * to_y))
                angle_deg = math.degrees(math.acos(dot))
                if angle_deg > self.fov_deg * 0.5:
                    return False, "fov", distance
        if self.fake_occlusion_prob > 0.0 and self.rng.random() < self.fake_occlusion_prob:
            return False, "noise", distance
        return True, "clear", distance

    def _can_see_chaser(self) -> tuple[bool, float | None]:
        distance = self._distance_to_chaser()
        if distance is None:
            return False, None
        visible, reason, distance = self._los_to_point(self.chaser_x, self.chaser_y, self.visible_range_cm)
        self.last_visibility_reason = reason
        if self.last_visibility_state is not None and self.last_visibility_state != visible:
            state = "regained sight of chaser" if visible else f"lost sight of chaser ({reason})"
            self.publish_status(f"Target brain visibility: {state}, distance_cm={distance:.1f}")
        self.last_visibility_state = visible
        if visible:
            self.last_seen_x = self.chaser_x
            self.last_seen_y = self.chaser_y
            self.last_seen_at = time.time()
        return visible, distance

    def _perceived_distance(self, visible: bool, live_distance: float | None) -> tuple[float | None, str]:
        if visible:
            return live_distance, "live"
        if self._recent_memory_available():
            return self.last_seen_distance, "memory"
        return None, "unknown"

    def _recent_memory_available(self) -> bool:
        if self.last_seen_at is None or self.last_seen_x is None or self.last_seen_y is None:
            return False
        return (time.time() - self.last_seen_at) <= self.memory_timeout_sec

    def _current_reference(self, visible: bool) -> tuple[float | None, float | None, bool]:
        ref_x = self.chaser_x
        ref_y = self.chaser_y
        using_memory = False
        if not visible and self._recent_memory_available():
            ref_x = self.last_seen_x
            ref_y = self.last_seen_y
            using_memory = True
        return ref_x, ref_y, using_memory

    def _apply_bounds_bias(self, vx: float, vy: float) -> tuple[float, float]:
        if abs(self.current_x) > self.bounds_x * 0.8:
            vx = -math.copysign(max(abs(vx), 0.2), self.current_x)
        if abs(self.current_y) > self.bounds_y * 0.8:
            vy = -math.copysign(max(abs(vy), 0.2), self.current_y)
        return vx, vy

    def _arena_center_heading(self) -> tuple[float, float]:
        return self._normalize_heading(-self.current_x, -self.current_y)

    def _unstuck_heading(self) -> tuple[float, float]:
        center_x = -self.current_x
        center_y = -self.current_y
        threat_x = self.chaser_x if self.chaser_x is not None else self.last_seen_x
        threat_y = self.chaser_y if self.chaser_y is not None else self.last_seen_y
        away_x = self.current_x - threat_x if threat_x is not None else 0.0
        away_y = self.current_y - threat_y if threat_y is not None else 0.0
        angle = self.rng.uniform(-0.8, 0.8)
        jitter_x = math.cos(angle)
        jitter_y = math.sin(angle)
        vx = center_x * 0.85 + away_x * 0.65 + jitter_x * 140.0
        vy = center_y * 0.85 + away_y * 0.65 + jitter_y * 140.0
        hx, hy = self._normalize_heading(vx, vy)
        self.unstuck_heading_x = hx
        self.unstuck_heading_y = hy
        return hx, hy

    def _update_stuck_state(self) -> bool:
        if not self.started:
            self.stuck_started_at = None
            self.unstuck_until = 0.0
            return False
        now = time.time()
        if now - self.started_at < self.stuck_start_grace_sec:
            self.stuck_started_at = None
            return False
        if self.prev_pose_at is None or now - self.prev_pose_at > 0.75:
            return False
        commanded_speed = abs(self.current_speed)
        if now < self.unstuck_until:
            if self.actual_speed_cm_s > self.stuck_speed_threshold_cm_s * 2.0:
                self.unstuck_until = 0.0
                self.stuck_started_at = None
                self.cached_strategy = "keep_distance"
                self.cached_tactic = None
                return False
            return True
        should_be_moving = commanded_speed >= self.stuck_command_threshold_cm_s
        barely_moving = self.actual_speed_cm_s <= self.stuck_speed_threshold_cm_s
        if should_be_moving and barely_moving:
            if self.stuck_started_at is None:
                self.stuck_started_at = now
            elif now - self.stuck_started_at >= self.stuck_after_sec:
                self.unstuck_until = now + self.unstuck_sec
                self.stuck_started_at = None
                self._unstuck_heading()
                self.cached_strategy = "unstuck_reposition"
                self.cached_tactic = "unstuck_reposition"
                self.cached_tactic_at = now
                self.publish_status(
                    "Target brain unstuck trigger: "
                    f"actual_speed={self.actual_speed_cm_s:.1f}, commanded_speed={commanded_speed:.1f}, "
                    f"vx={self.unstuck_heading_x * self.current_speed:.1f}, vy={self.unstuck_heading_y * self.current_speed:.1f}"
                )
                return True
        else:
            self.stuck_started_at = None
        return False

    def _normalize_heading(self, vx: float, vy: float) -> tuple[float, float]:
        vx, vy = self._apply_bounds_bias(vx, vy)
        length = math.hypot(vx, vy) or 1.0
        return vx / length, vy / length

    def _random_heading(self) -> tuple[float, float]:
        angle = self.rng.uniform(0.0, 2.0 * math.pi)
        return self._normalize_heading(math.cos(angle), math.sin(angle))

    def _choose_altitude_tactic(self, threat_state: str, visible: bool) -> str:
        if self.current_z <= self.min_z + 35.0:
            return "climb_escape"
        if self.current_z >= self.max_z - 35.0:
            return "dive_escape"
        if threat_state == "panic":
            return self.rng.choice(["climb_escape", "dive_escape", "level_escape"])
        if threat_state == "evade" and visible:
            return self.rng.choice(["climb_escape", "dive_escape", "level_escape", "level_escape"])
        return "level_escape"

    def _set_altitude_target_for_tactic(self, tactic: str) -> None:
        self.altitude_tactic = tactic
        if tactic == "climb_escape":
            self.target_z = self._clamp_z(self.current_z + self.altitude_step)
        elif tactic == "dive_escape":
            self.target_z = self._clamp_z(self.current_z - self.altitude_step)
        else:
            self.target_z = self.cruise_z

    def _vertical_velocity(self) -> float:
        error = self._clamp_z(self.target_z) - self.current_z
        if abs(error) < 5.0:
            return 0.0
        return max(-self.vertical_speed, min(self.vertical_speed, error / max(self.tick_dt, 1e-3)))

    def _escape_heading_from_angle(self, base_angle: float, spread_deg: float = 65.0) -> tuple[float, float]:
        offset = self.rng.uniform(-math.radians(spread_deg), math.radians(spread_deg))
        away_x = math.cos(base_angle + offset)
        away_y = math.sin(base_angle + offset)
        center_x = -self.current_x
        center_y = -self.current_y
        edge_pressure = max(
            abs(self.current_x) / max(self.bounds_x, 1.0),
            abs(self.current_y) / max(self.bounds_y, 1.0),
        )
        center_weight = 0.0
        if edge_pressure > 0.65:
            center_weight = min(0.75, (edge_pressure - 0.65) * 2.2)
        vx = away_x * (1.0 - center_weight) + center_x * center_weight
        vy = away_y * (1.0 - center_weight) + center_y * center_weight
        return self._normalize_heading(vx, vy)

    def _separation_safe_heading(
        self,
        hx: float,
        hy: float,
        ref_x: float | None,
        ref_y: float | None,
    ) -> tuple[float, float]:
        if ref_x is None or ref_y is None:
            return hx, hy
        away_x = self.current_x - ref_x
        away_y = self.current_y - ref_y
        distance = math.hypot(away_x, away_y)
        if distance <= 1e-6 or distance > self.alert_range_cm:
            return hx, hy
        away_x /= distance
        away_y /= distance
        dot = hx * away_x + hy * away_y
        min_dot = 0.35 if distance <= self.panic_range_cm else 0.15
        if dot >= min_dot:
            return hx, hy
        center_x = -self.current_x
        center_y = -self.current_y
        center_len = math.hypot(center_x, center_y)
        if center_len > 1e-6:
            center_x /= center_len
            center_y /= center_len
        else:
            center_x = 0.0
            center_y = 0.0
        vx = away_x * 0.85 + center_x * 0.15
        vy = away_y * 0.85 + center_y * 0.15
        return self._normalize_heading(vx, vy)

    def _threat_state_for_distance(self, distance: float | None) -> str:
        if distance is None:
            return "patrol"
        if distance <= self.panic_range_cm:
            return "panic"
        if distance <= self.alert_range_cm:
            return "evade"
        return "patrol"

    def _can_burst(self) -> bool:
        now = time.time()
        return now >= self.burst_cooldown_until and now >= self.burst_until and self.stamina >= self.min_burst_stamina

    def _update_stamina(self) -> None:
        now = time.time()
        dt = max(0.0, now - self.last_stamina_update_at)
        self.last_stamina_update_at = now
        if dt <= 0.0:
            return
        if now < self.burst_until:
            self.stamina -= self.burst_stamina_drain_per_sec * dt
            if self.stamina <= 0.0:
                self.stamina = 0.0
                self.burst_until = now
                self.burst_cooldown_until = max(self.burst_cooldown_until, now + self.burst_cooldown_sec)
        else:
            self.stamina += self.stamina_regen_per_sec * dt
        self.stamina = max(0.0, min(self.stamina_max, self.stamina))

    def _boost_state(self) -> str:
        now = time.time()
        if now < self.burst_until:
            return "burst"
        if now < self.burst_cooldown_until:
            return "cooldown"
        if self.stamina < self.min_burst_stamina:
            return "tired"
        return "ready"

    def _activate_burst(self) -> bool:
        self._update_stamina()
        if not self._can_burst():
            return False
        now = time.time()
        self.stamina = max(0.0, self.stamina - self.burst_stamina_cost)
        self.burst_until = now + self.burst_sec
        self.burst_cooldown_until = self.burst_until + self.burst_cooldown_sec
        return True

    def _update_speed_for_state(self, threat_state: str) -> None:
        self._update_stamina()
        now = time.time()
        if threat_state == "panic":
            if self._can_burst():
                self._activate_burst()
            self.current_speed = self.burst_speed if now < self.burst_until else self.evade_speed
            if self.stamina <= self.min_burst_stamina * 0.45 and now >= self.burst_until:
                self.current_speed *= self.exhausted_speed_scale
            return
        if threat_state == "evade":
            self.current_speed = self.evade_speed
            if self.stamina <= self.min_burst_stamina * 0.35:
                self.current_speed *= self.exhausted_speed_scale
            return
        self.current_speed = self.cruise_speed

    def _fallback_escape_heading(self, visible: bool, threat_state: str) -> tuple[float, float, str]:
        ref_x, ref_y, _ = self._current_reference(visible)
        if ref_x is None or ref_y is None:
            hx, hy = self._random_heading()
            return hx, hy, "random_no_target"

        away_x = self.current_x - ref_x
        away_y = self.current_y - ref_y
        if threat_state == "panic":
            return self._heading_from_tactic("burst_escape", ref_x, ref_y)
        if not visible:
            base_angle = math.atan2(away_y, away_x)
            hx, hy = self._escape_heading_from_angle(base_angle, spread_deg=48.0)
            if self._recent_memory_available():
                return hx, hy, "hidden_from_memory"
            return hx, hy, "random_hidden"

        hx, hy = self._normalize_heading(away_x, away_y)
        return hx, hy, "flee_direct"

    def _build_ollama_request(
        self,
        visible: bool,
        distance: float | None,
        ref_x: float,
        ref_y: float,
        using_memory: bool,
        threat_state: str,
    ) -> dict:
        now = time.time()
        system = (
            "You are a tactical evasion controller for a red drone being chased by a blue drone. "
            "Choose a multi-step escape strategy and one immediate tactic that increases distance or forces the chaser to overshoot. "
            "If visible is false, prefer break_line_of_sight:random_escape or reverse_when_overcommitted:zigzag_left. "
            "If visibility_reason is blocked, stay hidden or widen the arc instead of flying straight back into sight. "
            "If distance_trend_cm is negative, the chaser is closing and you should prefer tempo_change:burst_escape or force_overshoot:juke_left. "
            "Valid strategies: keep_distance, break_line_of_sight, reverse_when_overcommitted, wide_arc_escape, tempo_change, force_overshoot. "
            "Valid tactics: flee_direct, veer_left, veer_right, juke_left, juke_right, zigzag_left, zigzag_right, burst_escape, random_escape. "
            "Answer exactly as strategy:tactic with no explanation."
        )
        payload_obj = {
            "self_x": round(self.current_x, 1),
            "self_y": round(self.current_y, 1),
            "chaser_x": round(ref_x, 1),
            "chaser_y": round(ref_y, 1),
            "distance_cm": round(distance, 1) if distance is not None else None,
            "visible": visible,
            "visibility_reason": self.last_visibility_reason,
            "using_memory": using_memory,
            "threat_state": threat_state,
            "burst_available": self._can_burst(),
            "stamina_pct": round((self.stamina / max(self.stamina_max, 1.0)) * 100.0, 1),
            "boost_state": self._boost_state(),
            "distance_trend_cm": round(self.last_distance_trend, 1),
            "current_strategy": self.cached_strategy,
            "current_tactic": self.cached_tactic,
            "last_seen_enemy_x": round(self.last_seen_x, 1) if self.last_seen_x is not None else None,
            "last_seen_enemy_y": round(self.last_seen_y, 1) if self.last_seen_y is not None else None,
            "seconds_since_last_seen": round(now - self.last_seen_at, 2) if self.last_seen_at is not None else None,
            "bounds_x_cm": self.bounds_x,
            "bounds_y_cm": self.bounds_y,
            "actual_speed_cm_s": round(self.actual_speed_cm_s, 1),
            "stuck": time.time() < self.unstuck_until,
        }
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
            "flee_direct": "keep_distance",
            "veer_left": "wide_arc_escape",
            "veer_right": "wide_arc_escape",
            "juke_left": "force_overshoot",
            "juke_right": "force_overshoot",
            "zigzag_left": "reverse_when_overcommitted",
            "zigzag_right": "reverse_when_overcommitted",
            "burst_escape": "tempo_change",
            "random_escape": "break_line_of_sight",
        }.get(tactic, "keep_distance")

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
                "keep_distance": "flee_direct",
                "break_line_of_sight": "random_escape",
                "reverse_when_overcommitted": "zigzag_left",
                "wide_arc_escape": "veer_left",
                "tempo_change": "burst_escape",
                "force_overshoot": "juke_left",
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
                return self._parse_ollama_plan(raw, "flee_direct")
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
            tactic = result.get("tactic", "flee_direct")
            self.cached_tactic = tactic
            self.cached_strategy = result.get("strategy", self._infer_strategy_for_tactic(tactic))
            self.cached_tactic_at = time.time()
            self.ollama_failure_count = 0
            self.ollama_disabled_until = 0.0
            self.publish_status(f"Target brain cached Ollama strategy={self.cached_strategy} tactic={tactic}")
        except Exception as exc:
            self._record_ollama_failure(exc)
        finally:
            self.ollama_future = None

    def _maybe_schedule_ollama(self, visible: bool, distance: float | None, threat_state: str) -> None:
        ref_x, ref_y, using_memory = self._current_reference(visible)
        if not self.ollama_enabled or ref_x is None or ref_y is None:
            return
        if self.ollama_future is not None:
            return
        now = time.time()
        if now < self.ollama_disabled_until:
            return
        if now - self.last_ollama_request_at < self.ollama_decision_cooldown_sec:
            return
        body = self._build_ollama_request(visible, distance, ref_x, ref_y, using_memory, threat_state)
        self.ollama_future = self.ollama_executor.submit(self._ollama_request_worker, body)
        self.last_ollama_request_at = now

    def _heading_from_tactic(self, tactic: str, ref_x: float | None, ref_y: float | None) -> tuple[float, float, str]:
        if ref_x is None or ref_y is None:
            hx, hy = self._random_heading()
            return hx, hy, "random_no_target"

        away_x = self.current_x - ref_x
        away_y = self.current_y - ref_y
        base_angle = math.atan2(away_y, away_x)

        if tactic in ("zigzag_left", "zigzag_right"):
            sign = -1.0 if tactic.endswith("right") else 1.0
            self._last_zigzag_sign = sign
            angle = base_angle + sign * math.radians(50.0)
            hx, hy = self._normalize_heading(math.cos(angle), math.sin(angle))
            hx, hy = self._separation_safe_heading(hx, hy, ref_x, ref_y)
            return hx, hy, tactic

        if tactic in ("juke_left", "juke_right"):
            sign = -1.0 if tactic.endswith("right") else 1.0
            angle = base_angle + sign * math.radians(70.0)
            hx, hy = self._normalize_heading(math.cos(angle), math.sin(angle))
            hx, hy = self._separation_safe_heading(hx, hy, ref_x, ref_y)
            return hx, hy, tactic

        if tactic == "burst_escape":
            burst_active = self._activate_burst() or time.time() < self.burst_until
            if not burst_active:
                fallback = "juke_right" if self._last_zigzag_sign > 0 else "juke_left"
                return self._heading_from_tactic(fallback, ref_x, ref_y)
            if self.last_distance_trend < -20.0:
                self._last_zigzag_sign *= -1.0
            angle = base_angle + self._last_zigzag_sign * math.radians(28.0)
            hx, hy = self._normalize_heading(math.cos(angle), math.sin(angle))
            hx, hy = self._separation_safe_heading(hx, hy, ref_x, ref_y)
            return hx, hy, tactic

        if tactic == "random_escape":
            hx, hy = self._escape_heading_from_angle(base_angle, spread_deg=80.0)
            hx, hy = self._separation_safe_heading(hx, hy, ref_x, ref_y)
            return hx, hy, tactic

        angle_offset = {
            "flee_direct": 0.0,
            "veer_left": math.radians(25.0),
            "veer_right": -math.radians(25.0),
        }.get(tactic, 0.0)
        angle = base_angle + angle_offset
        hx, hy = self._normalize_heading(math.cos(angle), math.sin(angle))
        hx, hy = self._separation_safe_heading(hx, hy, ref_x, ref_y)
        return hx, hy, tactic or "flee_direct"

    def _choose_tactic(self, visible: bool, distance: float | None, threat_state: str) -> tuple[float, float, str]:
        self._harvest_ollama_result()
        if self.pending_ollama_error:
            self.publish_status(f"Target brain Ollama fallback: {self.pending_ollama_error}")
            self.pending_ollama_error = None

        self._maybe_schedule_ollama(visible, distance, threat_state)
        ref_x, ref_y, _ = self._current_reference(visible)
        tactic_age = time.time() - self.cached_tactic_at
        cached_ttl = self.short_tactic_ttl if self.cached_tactic in ("random_escape", "juke_left", "juke_right", "burst_escape") else self.tactic_ttl_sec
        if self.cached_tactic and tactic_age <= cached_ttl and ref_x is not None and ref_y is not None:
            cached_tactic = self.cached_tactic
            if cached_tactic == "burst_escape" and not self._can_burst() and time.time() >= self.burst_until:
                cached_tactic = "juke_right" if self._last_zigzag_sign > 0 else "juke_left"
            hx, hy, tactic = self._heading_from_tactic(cached_tactic, ref_x, ref_y)
            return hx, hy, f"{tactic}[cached]"

        if threat_state == "panic":
            tactic = "burst_escape"
            hx, hy, tactic = self._heading_from_tactic(tactic, ref_x, ref_y)
            self.cached_strategy = "tempo_change"
            self.cached_tactic = tactic
            self.cached_tactic_at = time.time()
            return hx, hy, tactic

        hx, hy, tactic = self._fallback_escape_heading(visible=visible, threat_state=threat_state)
        if self.cached_strategy == "force_overshoot" and ref_x is not None and ref_y is not None:
            tactic = "juke_left" if self._last_zigzag_sign > 0 else "juke_right"
            hx, hy, tactic = self._heading_from_tactic(tactic, ref_x, ref_y)
        elif self.cached_strategy == "wide_arc_escape" and ref_x is not None and ref_y is not None:
            tactic = "veer_left" if self.current_y <= ref_y else "veer_right"
            hx, hy, tactic = self._heading_from_tactic(tactic, ref_x, ref_y)
        elif self.cached_strategy == "break_line_of_sight" and ref_x is not None and ref_y is not None:
            tactic = "random_escape" if not visible else "zigzag_right"
            hx, hy, tactic = self._heading_from_tactic(tactic, ref_x, ref_y)
        elif self.cached_strategy == "reverse_when_overcommitted" and ref_x is not None and ref_y is not None:
            tactic = "zigzag_left" if self.last_distance_trend >= 0 else "zigzag_right"
            hx, hy, tactic = self._heading_from_tactic(tactic, ref_x, ref_y)
        elif self.cached_strategy == "tempo_change" and ref_x is not None and ref_y is not None:
            tactic = "burst_escape" if self._can_burst() else "juke_right"
            hx, hy, tactic = self._heading_from_tactic(tactic, ref_x, ref_y)
        self.cached_tactic = tactic
        self.cached_strategy = self._infer_strategy_for_tactic(tactic)
        self.cached_tactic_at = time.time()
        return hx, hy, tactic

    def choose_heading(self, force: bool = False) -> None:
        visible, live_distance = self._can_see_chaser()
        distance, distance_source = self._perceived_distance(visible, live_distance)
        if self.last_seen_distance is not None and distance is not None:
            self.last_distance_trend = distance - self.last_seen_distance
        if visible:
            self.last_seen_distance = distance
        self.threat_state = self._threat_state_for_distance(distance)
        self._update_speed_for_state(self.threat_state)

        if self._update_stuck_state():
            hx = self.unstuck_heading_x
            hy = self.unstuck_heading_y
            tactic = "unstuck_reposition"
            self.cached_strategy = "unstuck_reposition"
            self.cached_tactic = tactic
            self._set_altitude_target_for_tactic("climb_escape")
        else:
            hx, hy, tactic = self._choose_tactic(visible, distance, self.threat_state)
            self._set_altitude_target_for_tactic(self._choose_altitude_tactic(self.threat_state, visible))

        self.heading_x = hx
        self.heading_y = hy
        self.publish_status(
            "Target brain move phase: "
            f"strategy={self.cached_strategy}, tactic={tactic}, threat={self.threat_state}, visible={int(visible)}, memory={int(self._recent_memory_available())}, "
            f"distance_cm={distance if distance is not None else 'unknown'}, distance_source={distance_source}, speed={self.current_speed:.1f}, "
            f"stamina={self.stamina:.1f}, boost={self._boost_state()}, actual_speed={self.actual_speed_cm_s:.1f}, stuck={int(time.time() < self.unstuck_until)}, "
            f"altitude={self.current_z:.1f}->{self.target_z:.1f} ({self.altitude_tactic}), "
            f"vx={self.heading_x * self.current_speed:.1f}, vy={self.heading_y * self.current_speed:.1f}, vz={self._vertical_velocity():.1f}"
        )

    def _publish_unstuck_status(self) -> None:
        now = time.time()
        if now - self.last_unstuck_status_at < 0.8:
            return
        self.last_unstuck_status_at = now
        self.publish_status(
            "Target brain move phase: "
            f"strategy=unstuck_reposition, tactic=unstuck_reposition, threat={self.threat_state}, "
            f"visible={int(bool(self.last_visibility_state))}, memory={int(self._recent_memory_available())}, "
            "distance_cm=unknown, distance_source=unknown, "
            f"speed={self.current_speed:.1f}, stamina={self.stamina:.1f}, boost={self._boost_state()}, "
            f"actual_speed={self.actual_speed_cm_s:.1f}, stuck=1, "
            f"altitude={self.current_z:.1f}->{self.target_z:.1f} ({self.altitude_tactic}), "
            f"vx={self.unstuck_heading_x * self.current_speed:.1f}, vy={self.unstuck_heading_y * self.current_speed:.1f}, vz={self._vertical_velocity():.1f}"
        )

    def _effective_rest_sec(self, threat_state: str, distance: float | None = None) -> float:
        if distance is not None:
            return 0.0
        if threat_state == "panic":
            return 0.0
        if threat_state == "evade":
            return 0.0
        return self.rest_sec

    def control_loop(self) -> None:
        if not self.started:
            self.cmd_pub.publish(Twist())
            return

        live_distance = self._distance_to_chaser()
        distance, _ = self._perceived_distance(bool(self.last_visibility_state), live_distance)
        self.threat_state = self._threat_state_for_distance(distance)
        self._update_speed_for_state(self.threat_state)

        self.phase_time_left -= self.tick_dt

        if self.phase == "rest":
            effective_rest = self._effective_rest_sec(self.threat_state, distance)
            if effective_rest <= 0.0 or self.phase_time_left <= 0.0:
                self.choose_heading()
                self.phase = "move"
                self.phase_time_left = self.move_sec
            self.cmd_pub.publish(Twist())
            return

        if self.threat_state in ("evade", "panic") and self.phase_time_left <= self.move_sec * 0.5:
            # Re-plan more often when under pressure.
            self.choose_heading()
            self.phase_time_left = self.move_sec
        elif self._update_stuck_state():
            self.heading_x = self.unstuck_heading_x
            self.heading_y = self.unstuck_heading_y
            self.cached_strategy = "unstuck_reposition"
            self.cached_tactic = "unstuck_reposition"
            self._publish_unstuck_status()
            self.phase_time_left = min(self.phase_time_left, 0.5)

        cmd = Twist()
        cmd.linear.x = self.heading_x * self.current_speed
        cmd.linear.y = self.heading_y * self.current_speed
        cmd.linear.z = self._vertical_velocity()
        self.cmd_pub.publish(cmd)

        if self.phase_time_left <= 0.0:
            rest_sec = self._effective_rest_sec(self.threat_state, distance)
            if rest_sec <= 0.0:
                self.choose_heading()
                self.phase = "move"
                self.phase_time_left = self.move_sec
            else:
                self.phase = "rest"
                self.phase_time_left = rest_sec
                self.publish_status(f"Target brain rest phase: threat={self.threat_state}")
                self.cmd_pub.publish(Twist())


def main(args=None) -> None:
    rclpy.init(args=args)
    node = TargetBrain()
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
