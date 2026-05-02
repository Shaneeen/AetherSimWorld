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

        self.rng = random.Random(int(self._read_float_env("SIM_TARGET_RANDOM_SEED", 42)))

        self.cruise_speed = self._read_float_env("SIM_TARGET_CRUISE_SPEED", 180.0)
        self.evade_speed = self._read_float_env("SIM_TARGET_EVADE_SPEED", 240.0)
        self.burst_speed = self._read_float_env("SIM_TARGET_BURST_SPEED", 320.0)
        self.move_sec = self._read_float_env("SIM_TARGET_MOVE_SEC", 2.0)
        self.rest_sec = self._read_float_env("SIM_TARGET_REST_SEC", 1.0)
        self.bounds_x = self._read_float_env("SIM_TARGET_BOUND_X", 1800.0)
        self.bounds_y = self._read_float_env("SIM_TARGET_BOUND_Y", 1800.0)
        self.tick_dt = self._read_float_env("SIM_TARGET_DT", 0.1)

        self.visible_range_cm = self._read_float_env("SIM_TARGET_VISIBLE_RANGE_CM", 5000.0)
        self.fake_occlusion_prob = self._read_float_env("SIM_TARGET_FAKE_OCCLUSION_PROB", 0.35)
        self.memory_timeout_sec = self._read_float_env("SIM_TARGET_MEMORY_TIMEOUT_SEC", 6.0)

        self.alert_range_cm = self._read_float_env("SIM_TARGET_ALERT_RANGE_CM", 1500.0)
        self.panic_range_cm = self._read_float_env("SIM_TARGET_PANIC_RANGE_CM", 500.0)
        self.burst_sec = self._read_float_env("SIM_TARGET_BURST_SEC", 2.0)
        self.burst_cooldown_sec = self._read_float_env("SIM_TARGET_BURST_COOLDOWN_SEC", 5.0)
        self.tactic_ttl_sec = self._read_float_env("SIM_TARGET_TACTIC_TTL_SEC", 4.0)

        self.ollama_enabled = os.environ.get("SIM_TARGET_USE_OLLAMA", os.environ.get("USE_OLLAMA", "1")) != "0"
        self.ollama_model = os.environ.get("SIM_TARGET_OLLAMA_MODEL", os.environ.get("OLLAMA_MODEL", "phi3"))
        self.ollama_url = os.environ.get("OLLAMA_API_URL", "http://localhost:11434/api/generate")
        self.ollama_timeout = self._read_float_env("OLLAMA_TIMEOUT_SEC", 3.0)
        self.ollama_decision_cooldown_sec = self._read_float_env("SIM_TARGET_OLLAMA_COOLDOWN_SEC", 2.0)

        self.current_x = 0.0
        self.current_y = 0.0
        self.chaser_x = None
        self.chaser_y = None
        self.heading_x = 0.0
        self.heading_y = 0.0
        self.current_speed = self.cruise_speed
        self.phase = "rest"
        self.phase_time_left = self.rest_sec
        self.announced_ready = False
        self.started = False
        self.last_seen_distance = None
        self.last_seen_x = None
        self.last_seen_y = None
        self.last_seen_at = None
        self.cached_tactic = None
        self.cached_tactic_at = 0.0
        self.pending_ollama_error = None
        self.ollama_executor = ThreadPoolExecutor(max_workers=1)
        self.ollama_future = None
        self.last_ollama_request_at = 0.0
        self.burst_until = 0.0
        self.burst_cooldown_until = 0.0
        self.threat_state = "patrol"
        self._last_zigzag_sign = 1.0

        self.timer = self.create_timer(self.tick_dt, self.control_loop)

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

    def publish_status(self, text: str) -> None:
        msg = String()
        msg.data = text
        self.status_pub.publish(msg)
        self.get_logger().info(text)

    def pose_callback(self, msg: PoseStamped) -> None:
        self.current_x = msg.pose.position.x
        self.current_y = msg.pose.position.y
        if not self.announced_ready:
            self.publish_status(
                "Target brain ready: "
                f"cruise={self.cruise_speed:.1f}, evade={self.evade_speed:.1f}, burst={self.burst_speed:.1f}, "
                f"move={self.move_sec:.1f}s, rest={self.rest_sec:.1f}s, ollama={int(self.ollama_enabled)}, "
                f"alert_range_cm={self.alert_range_cm:.1f}, panic_range_cm={self.panic_range_cm:.1f}, waiting_for_start=1"
            )
            self.announced_ready = True

    def chaser_pose_callback(self, msg: PoseStamped) -> None:
        self.chaser_x = msg.pose.position.x
        self.chaser_y = msg.pose.position.y

    def control_callback(self, msg: String) -> None:
        command = msg.data.strip().lower()
        if command in ("start", "start_a", "start_all"):
            self.started = True
            self.phase = "move"
            self.phase_time_left = self.move_sec
            self.choose_heading(force=True)
            self.publish_status(f"Target brain received {command.upper()}")
        elif command in ("stop", "stop_a", "stop_all"):
            self.started = False
            self.phase = "rest"
            self.phase_time_left = self.rest_sec
            self.cmd_pub.publish(Twist())
            self.publish_status(f"Target brain received {command.upper()}")

    def _distance_to_chaser(self) -> float | None:
        if self.chaser_x is None or self.chaser_y is None:
            return None
        return math.hypot(self.current_x - self.chaser_x, self.current_y - self.chaser_y)

    def _can_see_chaser(self) -> tuple[bool, float | None]:
        distance = self._distance_to_chaser()
        if distance is None:
            return False, None
        if distance > self.visible_range_cm:
            return False, distance
        visible = self.rng.random() >= self.fake_occlusion_prob
        if visible:
            self.last_seen_x = self.chaser_x
            self.last_seen_y = self.chaser_y
            self.last_seen_at = time.time()
        return visible, distance

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

    def _normalize_heading(self, vx: float, vy: float) -> tuple[float, float]:
        vx, vy = self._apply_bounds_bias(vx, vy)
        length = math.hypot(vx, vy) or 1.0
        return vx / length, vy / length

    def _random_heading(self) -> tuple[float, float]:
        angle = self.rng.uniform(0.0, 2.0 * math.pi)
        return self._normalize_heading(math.cos(angle), math.sin(angle))

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
        return now >= self.burst_cooldown_until and now >= self.burst_until

    def _activate_burst(self) -> None:
        now = time.time()
        self.burst_until = now + self.burst_sec
        self.burst_cooldown_until = self.burst_until + self.burst_cooldown_sec

    def _update_speed_for_state(self, threat_state: str) -> None:
        now = time.time()
        if threat_state == "panic":
            if self._can_burst():
                self._activate_burst()
            self.current_speed = self.burst_speed if now < self.burst_until else self.evade_speed
            return
        if threat_state == "evade":
            self.current_speed = self.evade_speed
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
            jitter_angle = self.rng.uniform(-1.2, 1.2)
            base_angle = math.atan2(away_y, away_x) + jitter_angle
            hx, hy = self._normalize_heading(math.cos(base_angle), math.sin(base_angle))
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
            "Return exactly one JSON object and no markdown. "
            "Choose an escape tactic that increases distance from the chaser or the last seen chaser position. "
            "Allowed tactics: flee_direct, veer_left, veer_right, juke_left, juke_right, zigzag_left, zigzag_right, burst_escape, random_escape. "
            "Schema: {\"tactic\":\"...\",\"reason\":\"short text\"}."
        )
        payload_obj = {
            "self_x": round(self.current_x, 1),
            "self_y": round(self.current_y, 1),
            "chaser_x": round(ref_x, 1),
            "chaser_y": round(ref_y, 1),
            "distance_cm": round(distance, 1) if distance is not None else None,
            "visible": visible,
            "using_memory": using_memory,
            "threat_state": threat_state,
            "burst_available": self._can_burst(),
            "last_seen_enemy_x": round(self.last_seen_x, 1) if self.last_seen_x is not None else None,
            "last_seen_enemy_y": round(self.last_seen_y, 1) if self.last_seen_y is not None else None,
            "seconds_since_last_seen": round(now - self.last_seen_at, 2) if self.last_seen_at is not None else None,
            "bounds_x_cm": self.bounds_x,
            "bounds_y_cm": self.bounds_y,
        }
        prompt = f"System:\n{system}\n\nUser:\n{json.dumps(payload_obj)}\n\nRespond with JSON only."
        return {
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2},
        }

    def _ollama_request_worker(self, body: dict) -> dict:
        response = requests.post(self.ollama_url, json=body, timeout=max(1.0, self.ollama_timeout))
        response.raise_for_status()
        outer = response.json()
        raw = outer.get("response", "") if isinstance(outer, dict) else ""
        if not raw:
            raise RuntimeError("Empty Ollama response")
        obj = json.loads(raw)
        tactic = str(obj.get("tactic", "")).strip().lower() or "flee_direct"
        return {"tactic": tactic}

    def _harvest_ollama_result(self) -> None:
        if self.ollama_future is None or not self.ollama_future.done():
            return
        try:
            result = self.ollama_future.result()
            tactic = result.get("tactic", "flee_direct")
            self.cached_tactic = tactic
            self.cached_tactic_at = time.time()
            self.publish_status(f"Target brain cached Ollama tactic={tactic}")
        except Exception as exc:
            self.pending_ollama_error = str(exc)
        finally:
            self.ollama_future = None

    def _maybe_schedule_ollama(self, visible: bool, distance: float | None, threat_state: str) -> None:
        ref_x, ref_y, using_memory = self._current_reference(visible)
        if not self.ollama_enabled or ref_x is None or ref_y is None:
            return
        if self.ollama_future is not None:
            return
        now = time.time()
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
            return hx, hy, tactic

        if tactic in ("juke_left", "juke_right"):
            sign = -1.0 if tactic.endswith("right") else 1.0
            angle = base_angle + sign * math.radians(70.0)
            hx, hy = self._normalize_heading(math.cos(angle), math.sin(angle))
            return hx, hy, tactic

        if tactic == "burst_escape":
            if self._can_burst():
                self._activate_burst()
            self._last_zigzag_sign *= -1.0
            angle = base_angle + self._last_zigzag_sign * math.radians(40.0)
            hx, hy = self._normalize_heading(math.cos(angle), math.sin(angle))
            return hx, hy, tactic

        if tactic == "random_escape":
            angle = self.rng.uniform(-math.pi, math.pi)
            hx, hy = self._normalize_heading(math.cos(angle), math.sin(angle))
            return hx, hy, tactic

        angle_offset = {
            "flee_direct": 0.0,
            "veer_left": math.radians(25.0),
            "veer_right": -math.radians(25.0),
        }.get(tactic, 0.0)
        angle = base_angle + angle_offset
        hx, hy = self._normalize_heading(math.cos(angle), math.sin(angle))
        return hx, hy, tactic or "flee_direct"

    def _choose_tactic(self, visible: bool, distance: float | None, threat_state: str) -> tuple[float, float, str]:
        self._harvest_ollama_result()
        if self.pending_ollama_error:
            self.publish_status(f"Target brain Ollama fallback: {self.pending_ollama_error}")
            self.pending_ollama_error = None

        self._maybe_schedule_ollama(visible, distance, threat_state)
        ref_x, ref_y, _ = self._current_reference(visible)
        tactic_age = time.time() - self.cached_tactic_at
        if self.cached_tactic and tactic_age <= self.tactic_ttl_sec and ref_x is not None and ref_y is not None:
            hx, hy, tactic = self._heading_from_tactic(self.cached_tactic, ref_x, ref_y)
            return hx, hy, f"{tactic}[cached]"

        if threat_state == "panic":
            tactic = "burst_escape"
            hx, hy, tactic = self._heading_from_tactic(tactic, ref_x, ref_y)
            self.cached_tactic = tactic
            self.cached_tactic_at = time.time()
            return hx, hy, tactic

        hx, hy, tactic = self._fallback_escape_heading(visible=visible, threat_state=threat_state)
        self.cached_tactic = tactic
        self.cached_tactic_at = time.time()
        return hx, hy, tactic

    def choose_heading(self, force: bool = False) -> None:
        visible, distance = self._can_see_chaser()
        self.last_seen_distance = distance
        self.threat_state = self._threat_state_for_distance(distance)
        self._update_speed_for_state(self.threat_state)

        hx, hy, tactic = self._choose_tactic(visible, distance, self.threat_state)

        self.heading_x = hx
        self.heading_y = hy
        self.publish_status(
            "Target brain move phase: "
            f"tactic={tactic}, threat={self.threat_state}, visible={int(visible)}, memory={int(self._recent_memory_available())}, "
            f"distance_cm={distance if distance is not None else 'unknown'}, speed={self.current_speed:.1f}, "
            f"vx={self.heading_x * self.current_speed:.1f}, vy={self.heading_y * self.current_speed:.1f}"
        )

    def _effective_rest_sec(self, threat_state: str) -> float:
        if threat_state == "panic":
            return 0.0
        if threat_state == "evade":
            return min(0.5, self.rest_sec)
        return self.rest_sec

    def control_loop(self) -> None:
        if not self.started:
            self.cmd_pub.publish(Twist())
            return

        distance = self._distance_to_chaser()
        self.threat_state = self._threat_state_for_distance(distance)
        self._update_speed_for_state(self.threat_state)

        self.phase_time_left -= self.tick_dt

        if self.phase == "rest":
            effective_rest = self._effective_rest_sec(self.threat_state)
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

        cmd = Twist()
        cmd.linear.x = self.heading_x * self.current_speed
        cmd.linear.y = self.heading_y * self.current_speed
        self.cmd_pub.publish(cmd)

        if self.phase_time_left <= 0.0:
            self.phase = "rest"
            self.phase_time_left = self._effective_rest_sec(self.threat_state)
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
