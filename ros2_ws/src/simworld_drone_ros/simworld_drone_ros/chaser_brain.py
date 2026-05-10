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
            10,
        )

        self.base_speed = self._read_float_env("SIM_CHASER_SPEED", 240.0)
        self.intercept_speed = self._read_float_env("SIM_CHASER_INTERCEPT_SPEED", 270.0)
        self.search_speed = self._read_float_env("SIM_CHASER_SEARCH_SPEED", 170.0)
        self.catch_distance = self._read_float_env("SIM_CATCH_DISTANCE", 120.0)
        self.tick_dt = self._read_float_env("SIM_CHASER_DT", 0.1)

        self.reaction_delay_sec = self._read_float_env("SIM_CHASER_REACTION_DELAY_SEC", 0.75)
        self.commit_sec = self._read_float_env("SIM_CHASER_COMMIT_SEC", 1.2)
        self.turn_rate_deg = self._read_float_env("SIM_CHASER_TURN_RATE_DEG", 95.0)
        self.aim_noise_cm = self._read_float_env("SIM_CHASER_AIM_NOISE_CM", 120.0)
        self.search_radius_cm = self._read_float_env("SIM_CHASER_SEARCH_RADIUS_CM", 500.0)
        self.memory_timeout_sec = self._read_float_env("SIM_CHASER_MEMORY_TIMEOUT_SEC", 6.0)
        self.tactic_ttl_sec = self._read_float_env("SIM_CHASER_TACTIC_TTL_SEC", 4.0)
        self.finish_range_cm = self._read_float_env("SIM_CHASER_FINISH_RANGE_CM", 260.0)
        self.finish_speed = self._read_float_env("SIM_CHASER_FINISH_SPEED", 235.0)
        self.finish_commit_sec = self._read_float_env("SIM_CHASER_FINISH_COMMIT_SEC", 0.8)
        self.mistake_chance = self._read_float_env("SIM_CHASER_MISTAKE_CHANCE", 0.18)
        self.pressure_hold_chance = self._read_float_env("SIM_CHASER_PRESSURE_HOLD_CHANCE", 0.35)
        self.cutoff_bias_cm = self._read_float_env("SIM_CHASER_CUTOFF_BIAS_CM", 320.0)
        self.intercept_lead_sec = self._read_float_env("SIM_CHASER_INTERCEPT_LEAD_SEC", 0.8)

        self.ollama_enabled = os.environ.get("SIM_CHASER_USE_OLLAMA", os.environ.get("USE_OLLAMA", "1")) != "0"
        self.ollama_model = os.environ.get("SIM_CHASER_OLLAMA_MODEL", os.environ.get("OLLAMA_MODEL", "phi3"))
        self.ollama_url = os.environ.get("OLLAMA_API_URL", "http://localhost:11434/api/generate")
        self.ollama_timeout = self._read_float_env("OLLAMA_TIMEOUT_SEC", 3.0)
        self.ollama_decision_cooldown_sec = self._read_float_env("SIM_CHASER_OLLAMA_COOLDOWN_SEC", 2.0)

        self.rng = random.Random(int(self._read_float_env("SIM_CHASER_RANDOM_SEED", 24)))

        self.target_x = None
        self.target_y = None
        self.self_x = None
        self.self_y = None
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
        self.lock_x = None
        self.lock_y = None
        self.lock_updated_at = 0.0
        self.commit_until = 0.0
        self.current_heading_x = 1.0
        self.current_heading_y = 0.0
        self.cached_tactic = "chase_direct"
        self.cached_tactic_at = 0.0
        self.pending_ollama_error = None
        self.ollama_executor = ThreadPoolExecutor(max_workers=1)
        self.ollama_future = None
        self.last_ollama_request_at = 0.0
        self.finish_until = 0.0

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

    def target_pose_callback(self, msg: PoseStamped) -> None:
        now = time.time()
        new_x = msg.pose.position.x
        new_y = msg.pose.position.y

        if self.prev_target_x is not None and self.prev_target_t is not None:
            dt = max(1e-3, now - self.prev_target_t)
            self.target_vx = (new_x - self.prev_target_x) / dt
            self.target_vy = (new_y - self.prev_target_y) / dt

        self.target_x = new_x
        self.target_y = new_y
        self.prev_target_x = new_x
        self.prev_target_y = new_y
        self.prev_target_t = now
        self.last_seen_x = new_x
        self.last_seen_y = new_y
        self.last_seen_at = now
        self._maybe_report_ready()

    def self_pose_callback(self, msg: PoseStamped) -> None:
        self.self_x = msg.pose.position.x
        self.self_y = msg.pose.position.y
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
            f"catch_distance={self.catch_distance:.1f}, reaction_delay={self.reaction_delay_sec:.2f}s, waiting_for_start=1"
        )

    def control_callback(self, msg: String) -> None:
        command = msg.data.strip().lower()
        if command in ("start", "start_b", "start_all"):
            if not self.started:
                self.started = True
                self.publish_status(f"Chaser brain received {command.upper()}")
        elif command in ("stop", "stop_b", "stop_all"):
            self.started = False
            self.cmd_pub.publish(Twist())
            self.publish_status(f"Chaser brain received {command.upper()}")

    def _distance_to_target(self, x: float | None, y: float | None) -> float | None:
        if x is None or y is None or self.self_x is None or self.self_y is None:
            return None
        return math.hypot(x - self.self_x, y - self.self_y)

    def _recent_memory_available(self) -> bool:
        if self.last_seen_at is None or self.last_seen_x is None or self.last_seen_y is None:
            return False
        return (time.time() - self.last_seen_at) <= self.memory_timeout_sec

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
            "target_mode": target_mode,
            "memory_available": self._recent_memory_available(),
        }
        system = (
            "You are a tactical controller for a blue chaser drone pursuing a red target drone. "
            "Return exactly one JSON object and no markdown. "
            "Allowed tactics: chase_direct, intercept, cutoff_left, cutoff_right, pressure, search_last_seen. "
            "Schema: {\"tactic\":\"...\",\"reason\":\"short text\"}."
        )
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
        tactic = str(obj.get("tactic", "")).strip().lower() or "chase_direct"
        return {"tactic": tactic}

    def _harvest_ollama_result(self) -> None:
        if self.ollama_future is None or not self.ollama_future.done():
            return
        try:
            result = self.ollama_future.result()
            self.cached_tactic = result.get("tactic", "chase_direct")
            self.cached_tactic_at = time.time()
            self.publish_status(f"Chaser brain cached Ollama tactic={self.cached_tactic}")
        except Exception as exc:
            self.pending_ollama_error = str(exc)
        finally:
            self.ollama_future = None

    def _maybe_schedule_ollama(self, distance: float | None, target_visible: bool, target_mode: str) -> None:
        if not self.ollama_enabled:
            return
        if self.ollama_future is not None:
            return
        now = time.time()
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
        return self.target_x is not None and self.target_y is not None

    def _choose_tactic(self, distance: float | None) -> str:
        self._harvest_ollama_result()
        if self.pending_ollama_error:
            self.publish_status(f"Chaser brain Ollama fallback: {self.pending_ollama_error}")
            self.pending_ollama_error = None

        visible = self._target_visible()
        target_mode = self._estimate_target_mode(distance)
        self._maybe_schedule_ollama(distance, visible, target_mode)

        if not visible and self._recent_memory_available():
            return "search_last_seen"

        if distance is not None and distance <= self.finish_range_cm:
            self.finish_until = time.time() + self.finish_commit_sec
            if self.rng.random() < self.pressure_hold_chance:
                return "pressure"
            return "finish_commit"

        tactic_age = time.time() - self.cached_tactic_at
        if self.cached_tactic and tactic_age <= self.tactic_ttl_sec:
            tactic = self.cached_tactic
        elif distance is not None and distance > 1200.0:
            tactic = "intercept"
        else:
            tactic = "chase_direct"

        if distance is not None and distance > self.finish_range_cm:
            if self.rng.random() < self.mistake_chance:
                tactic = self.rng.choice(["cutoff_left", "cutoff_right", "search_last_seen"])
            elif distance > 1400.0 and self.rng.random() < 0.45:
                tactic = self.rng.choice(["intercept", "cutoff_left", "cutoff_right"])
            elif distance < 800.0 and self.rng.random() < 0.25:
                tactic = self.rng.choice(["pressure", "cutoff_left", "cutoff_right"])

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

        elif tactic == "pressure":
            speed = self.base_speed * 0.68

        elif tactic == "finish_commit":
            speed = self.finish_speed

        if target_x is None or target_y is None or self.self_x is None or self.self_y is None:
            return self.current_heading_x, self.current_heading_y, speed

        desired_x = target_x - self.self_x
        desired_y = target_y - self.self_y

        noise_scale = 1.0
        if tactic == "finish_commit":
            noise_scale = 0.35
        elif tactic == "pressure":
            noise_scale = 1.25
        elif tactic == "search_last_seen":
            noise_scale = 1.4

        noise_x = self.rng.uniform(-self.aim_noise_cm, self.aim_noise_cm) * noise_scale
        noise_y = self.rng.uniform(-self.aim_noise_cm, self.aim_noise_cm) * noise_scale
        desired_x += noise_x
        desired_y += noise_y

        heading_x, heading_y = self._apply_turn_limit(desired_x, desired_y)
        return heading_x, heading_y, speed

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
            self.cached_tactic_at = now
            self.commit_until = now + (self.finish_commit_sec if tactic == "finish_commit" else self.commit_sec)
            self.publish_status(f"Chaser brain commit tactic={tactic}")

        if now < self.finish_until and (self.cached_tactic in ("pressure", "chase_direct")):
            self.cached_tactic = "finish_commit"

        tactic = self.cached_tactic or "chase_direct"
        heading_x, heading_y, speed = self._desired_heading_from_tactic(tactic)

        cmd = Twist()
        cmd.linear.x = heading_x * speed
        cmd.linear.y = heading_y * speed
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
