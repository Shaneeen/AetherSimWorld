from __future__ import annotations

import base64
from concurrent.futures import Future, ThreadPoolExecutor
import json
import math
import os
import time
from typing import Any

from geometry_msgs.msg import PoseStamped
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from simworld_drone_ros.team.models import build_team
from simworld_drone_ros.team.tactical_geometry import read_tactical_blockers
from simworld_drone_ros.vision.scene_parser import fallback_scene, normalize_scene
from simworld_drone_ros.vision.vlm_client import OllamaVlmClient

try:
    import unrealcv
except ImportError:
    unrealcv = None


class VisualObserver(Node):
    """Publishes VLM scene summaries for team coordination."""

    def __init__(self) -> None:
        observer_name = os.environ.get("SIM_VISION_OBSERVER", "blue_1").strip() or "blue_1"
        super().__init__(f"visual_observer_{_safe_node_suffix(observer_name)}")
        self.status_pub = self.create_publisher(String, "/sim/status", 20)
        self.scene_pub = self.create_publisher(String, "/sim/vision_scene", 10)
        self.camera_frame_sub = self.create_subscription(String, "/sim/camera_frame", self.camera_frame_callback, 5)
        self.enabled = _read_bool_env("SIM_VISION_ENABLED", False)
        self.vlm_enabled = _read_bool_env("SIM_VLM_ENABLED", self.enabled)
        self.image_vlm_enabled = _read_bool_env("SIM_VISION_IMAGE_VLM_ENABLED", False)
        self.direct_unrealcv_enabled = _read_bool_env("SIM_VISION_DIRECT_UNREALCV", False)
        self.bridge_frame_max_age_sec = _read_float_env("SIM_VISION_BRIDGE_FRAME_MAX_AGE_SEC", 8.0)
        self.publish_fallback = _read_bool_env("SIM_VISION_PUBLISH_FALLBACK", True)
        self.observer = observer_name
        self.camera_id = int(_read_float_env("SIM_VISION_CAMERA_ID", 0.0))
        self.camera_width = int(_read_float_env("SIM_VISION_CAMERA_WIDTH", 320.0))
        self.camera_height = int(_read_float_env("SIM_VISION_CAMERA_HEIGHT", 240.0))
        self.camera_steer_enabled = _read_bool_env("SIM_BRIDGE_CAMERA_STEER_ENABLED", False)
        self.plan_sec = max(0.5, _read_float_env("SIM_VISION_DT", 2.5))
        self.vlm_request_interval_sec = max(
            self.plan_sec,
            _read_float_env("SIM_VISION_VLM_INTERVAL_SEC", 20.0),
        )
        self.min_poses_for_vlm = int(_read_float_env("SIM_VISION_MIN_POSES_FOR_VLM", 8.0))
        self.host = os.environ.get("SIMWORLD_HOST", "127.0.0.1")
        self.port = int(_read_float_env("SIMWORLD_PORT", 9000.0))
        self.back_offset = _read_float_env("SIM_VISION_CAMERA_BACK_CM", 320.0)
        self.up_offset = _read_float_env("SIM_VISION_CAMERA_UP_CM", 180.0)
        self.pitch_deg = _read_float_env("SIM_VISION_CAMERA_PITCH_DEG", -18.0)
        self.fov_deg = _read_float_env("SIM_VISION_CAMERA_FOV_DEG", 90.0)
        self.min_z = _read_float_env("SIMWORLD_DRONE_MIN_Z", _read_float_env("SIM_DRONE_MIN_Z", 100.0))
        self.max_z = _read_float_env("SIMWORLD_DRONE_MAX_Z", _read_float_env("SIM_DRONE_MAX_Z", 700.0))
        self.blockers = [_blocker_to_dict(blocker) for blocker in read_tactical_blockers(self.min_z, self.max_z)]
        self.poses: dict[str, tuple[float, float, float]] = {}
        self.last_failure_at = 0.0
        self.failure_backoff_sec = _read_float_env("SIM_VISION_FAILURE_BACKOFF_SEC", 8.0)
        self.request_timeout_sec = max(
            self.plan_sec + 1.0,
            _read_float_env("SIM_VISION_REQUEST_TIMEOUT_SEC", 180.0),
        )
        self.last_request_status_at = 0.0
        self.client = None
        self.vlm = OllamaVlmClient()
        self.worker_executor = ThreadPoolExecutor(max_workers=1)
        self.future: Future[dict[str, Any]] | None = None
        self.future_started_at = 0.0
        self.future_mode = ""
        self.camera_ready = False
        self.camera_list = ""
        self.latest_camera_frame: bytes | None = None
        self.latest_camera_frame_at = 0.0
        self.latest_camera_frame_meta: dict[str, Any] = {}
        self.last_scene_publish_at = 0.0
        self.first_fallback_published = False
        self.last_vlm_request_at = 0.0
        self.request_counter = 0

        self.pose_subs = []
        for drone in build_team("red") + build_team("blue"):
            self.pose_subs.append(
                self.create_subscription(
                    PoseStamped,
                    drone.pose_topic,
                    lambda msg, selected=drone.name: self.pose_callback(selected, msg),
                    10,
                )
            )

        self.timer = self.create_timer(self.plan_sec, self.control_loop)
        self.publish_status(
            "Vision observer ready: "
            f"enabled={int(self.enabled)} vlm={int(self.vlm_enabled)} image_vlm={int(self.image_vlm_enabled)} "
            f"observer={self.observer} "
            f"camera={self.camera_id} size={self.camera_width}x{self.camera_height} "
            f"dt={self.plan_sec:.1f}s timeout={self.request_timeout_sec:.1f}s blockers={len(self.blockers)} "
            f"model={self.vlm.model} goal_memory={int(bool(self.vlm.mission_goal))} "
            f"steer={int(self.camera_steer_enabled)}"
        )

    def pose_callback(self, name: str, msg: PoseStamped) -> None:
        self.poses[name] = (
            msg.pose.position.x,
            msg.pose.position.y,
            msg.pose.position.z,
        )

    def camera_frame_callback(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
            frame = base64.b64decode(str(payload.get("image_b64", "")), validate=True)
            if not frame:
                return
        except Exception as exc:
            self.publish_status(f"Vision observer ignored bad bridge camera frame: {exc}")
            return
        self.latest_camera_frame = frame
        self.latest_camera_frame_at = time.time()
        self.latest_camera_frame_meta = payload

    def publish_status(self, text: str) -> None:
        msg = String()
        msg.data = text
        self.status_pub.publish(msg)
        self.get_logger().info(text)

    def publish_scene(self, scene: dict[str, Any]) -> None:
        if self.vlm.mission_goal and not scene.get("mission_goal"):
            scene["mission_goal"] = self.vlm.mission_goal
        msg = String()
        msg.data = json.dumps(scene, separators=(",", ":"))
        self.scene_pub.publish(msg)
        self.last_scene_publish_at = time.time()
        self.publish_status(
            "Vision scene: "
            f"observer={scene.get('observer')} source={scene.get('source')} "
            f"runner_visible={scene.get('runner_visible')} blocked_by={scene.get('blocked_by') or 'none'} "
            f"search={scene.get('recommended_search_area') or 'none'} confidence={scene.get('confidence', 0.0):.2f}"
        )

    def connect(self) -> bool:
        if self.client is not None and self.client.isconnected():
            self.publish_status("Vision observer UnrealCV already connected")
            self._prepare_camera()
            return True
        if unrealcv is None:
            return False
        self.publish_status(f"Vision observer UnrealCV connect begin: {self.host}:{self.port}")
        self.client = unrealcv.Client((self.host, self.port))
        self.client.connect()
        if not self.client.isconnected():
            return False
        self.publish_status(f"Vision observer UnrealCV connected: {self.host}:{self.port}")
        self._prepare_camera()
        return True

    def _prepare_camera(self) -> None:
        if self.camera_ready or self.client is None:
            return
        try:
            self.publish_status("Vision observer camera list request begin")
            self.camera_list = str(self.client.request("vget /cameras")).strip()
            self.publish_status(f"Vision observer camera list ok: cameras={self.camera_list or 'unknown'}")
        except Exception as exc:
            self.camera_list = f"unavailable: {exc}"
        try:
            self.publish_status(
                f"Vision observer camera size request begin: camera={self.camera_id} "
                f"size={self.camera_width}x{self.camera_height}"
            )
            if self.camera_steer_enabled:
                self.client.request(f"vset /camera/{self.camera_id}/size {self.camera_width} {self.camera_height}")
                self.publish_status(f"Vision observer camera size ok: camera={self.camera_id}")
            else:
                self.publish_status(f"Vision observer camera size skipped: camera={self.camera_id} steer=0")
        except Exception as exc:
            self.publish_status(f"Vision observer camera size warning: camera={self.camera_id} error={exc}")
        self.camera_ready = True
        self.publish_status(
            "Vision observer camera ready: "
            f"camera={self.camera_id} size={self.camera_width}x{self.camera_height} "
            f"cameras={self.camera_list or 'unknown'} steer={int(self.camera_steer_enabled)}"
        )

    def capture_frame(self) -> bytes:
        if self.latest_camera_frame is not None:
            age = time.time() - self.latest_camera_frame_at
            if age <= self.bridge_frame_max_age_sec:
                self.publish_status(
                    "Vision observer bridge camera frame accepted: "
                    f"frame_bytes={len(self.latest_camera_frame)} age={age:.1f}s "
                    f"observer={self.latest_camera_frame_meta.get('observer', 'unknown')}"
                )
                return self.latest_camera_frame
        if not self.direct_unrealcv_enabled:
            raise RuntimeError(
                "No fresh /sim/camera_frame from bridge yet; waiting for bridge-owned image VLM frame"
            )
        self.publish_status("Vision observer camera capture begin")
        if not self.connect():
            raise RuntimeError("UnrealCV is unavailable or not connected")
        observer_pose = self.poses.get(self.observer)
        runner_pose = self.poses.get("red_1")
        if observer_pose is not None and self.camera_steer_enabled:
            yaw = self._camera_yaw(observer_pose, runner_pose)
            yaw_rad = math.radians(yaw)
            camera_x = observer_pose[0] - math.cos(yaw_rad) * self.back_offset
            camera_y = observer_pose[1] - math.sin(yaw_rad) * self.back_offset
            camera_z = observer_pose[2] + self.up_offset
            self.publish_status(
                "Vision observer camera pose request begin: "
                f"x={camera_x:.1f} y={camera_y:.1f} z={camera_z:.1f} yaw={yaw:.1f}"
            )
            self.client.request(f"vset /camera/{self.camera_id}/location {camera_x} {camera_y} {camera_z}")
            self.client.request(f"vset /camera/{self.camera_id}/rotation {self.pitch_deg} {yaw} 0")
            self.client.request(f"vset /camera/{self.camera_id}/fov {self.fov_deg}")
            self.publish_status("Vision observer camera pose ok")
        elif observer_pose is not None:
            self.publish_status("Vision observer camera pose skipped: steer=0")
        self.publish_status(f"Vision observer camera lit request begin: camera={self.camera_id}")
        frame = self.client.request(f"vget /camera/{self.camera_id}/lit png")
        if not isinstance(frame, (bytes, bytearray)) or not frame:
            raise RuntimeError("UnrealCV camera returned no PNG bytes")
        self.publish_status(f"Vision observer camera capture ok: frame_bytes={len(frame)}")
        return bytes(frame)

    def _camera_yaw(
        self,
        observer_pose: tuple[float, float, float],
        runner_pose: tuple[float, float, float] | None,
    ) -> float:
        if runner_pose is None:
            return 0.0
        return math.degrees(math.atan2(runner_pose[1] - observer_pose[1], runner_pose[0] - observer_pose[0]))

    def _scene_worker(self) -> dict[str, Any]:
        started = time.time()
        if self.enabled and self.vlm_enabled:
            if len(self.poses) < self.min_poses_for_vlm:
                scene = fallback_scene(self.observer, self.poses, self.blockers)
                scene["_duration_sec"] = round(time.time() - started, 2)
                scene["_skip_reason"] = f"waiting_for_poses:{len(self.poses)}/{self.min_poses_for_vlm}"
                return scene
            if not self.image_vlm_enabled:
                self.publish_status("Vision observer VLM context request begin")
                scene = self.vlm.describe_context_scene(self.observer, self.poses, self.blockers)
                scene["_duration_sec"] = round(time.time() - started, 2)
                scene["_frame_bytes"] = 0
                return scene
            frame = self.capture_frame()
            self.publish_status(f"Vision observer image VLM request begin: frame_bytes={len(frame)}")
            scene = self.vlm.describe_scene(frame, self.observer, self.poses, self.blockers)
            scene["_duration_sec"] = round(time.time() - started, 2)
            scene["_frame_bytes"] = len(frame)
            return scene
        scene = fallback_scene(self.observer, self.poses, self.blockers)
        scene["_duration_sec"] = round(time.time() - started, 2)
        return scene

    def _harvest_result(self) -> None:
        if self.future is None:
            return
        if not self.future.done():
            if time.time() - self.future_started_at <= self.request_timeout_sec:
                return
            self.last_failure_at = time.time()
            self.publish_status(
                "Vision observer timeout: "
                f"request exceeded {self.request_timeout_sec:.1f}s; publishing fallback scene"
            )
            self.future.cancel()
            timed_out_mode = self.future_mode
            self.future = None
            self.future_started_at = 0.0
            self.future_mode = ""
            if timed_out_mode == "vlm_image":
                self.publish_status(
                    "Vision observer image VLM request timed out; keeping image mode enabled and retrying"
                )
                self._replace_worker_executor()
            if self.publish_fallback:
                self.publish_scene(fallback_scene(self.observer, self.poses, self.blockers))
            return
        try:
            result = self.future.result()
            duration = result.pop("_duration_sec", None) if isinstance(result, dict) else None
            frame_bytes = result.pop("_frame_bytes", None) if isinstance(result, dict) else None
            skip_reason = result.pop("_skip_reason", None) if isinstance(result, dict) else None
            if duration is not None:
                self.publish_status(
                    "Vision observer response: "
                    f"duration={duration:.1f}s frame_bytes={frame_bytes or 'n/a'}"
                    f"{' skip=' + str(skip_reason) if skip_reason else ''}"
                )
            self.publish_scene(normalize_scene(result, self.observer, str(result.get("source", "vision"))))
        except Exception as exc:
            self.last_failure_at = time.time()
            self.publish_status(f"Vision observer fallback: {exc}")
            if self.publish_fallback:
                self.publish_scene(fallback_scene(self.observer, self.poses, self.blockers))
        finally:
            self.future = None
            self.future_started_at = 0.0
            self.future_mode = ""

    def control_loop(self) -> None:
        self._harvest_result()
        if self.future is not None:
            return
        if not self.enabled and not self.publish_fallback:
            return
        if time.time() - self.last_failure_at < self.failure_backoff_sec:
            return
        if self.publish_fallback and not self.first_fallback_published and self.poses:
            self.first_fallback_published = True
            self.publish_status("Vision observer warm start: publishing fallback scene while VLM starts")
            self.publish_scene(fallback_scene(self.observer, self.poses, self.blockers))
        if self.enabled and self.vlm_enabled and len(self.poses) < self.min_poses_for_vlm:
            now = time.time()
            if now - self.last_request_status_at >= 8.0:
                self.last_request_status_at = now
                self.publish_status(
                    "Vision observer waiting: "
                    f"poses={len(self.poses)}/{self.min_poses_for_vlm} before VLM image request"
                )
            return
        now = time.time()
        if self.enabled and self.vlm_enabled and now - self.last_vlm_request_at < self.vlm_request_interval_sec:
            return
        self.request_counter += 1
        mode = "vlm_image" if self.enabled and self.vlm_enabled and self.image_vlm_enabled else (
            "vlm_context" if self.enabled and self.vlm_enabled else "pose_fallback"
        )
        self.last_request_status_at = now
        self.publish_status(
            "Vision observer request: "
            f"id={self.request_counter} mode={mode} observer={self.observer} "
            f"poses={len(self.poses)} blockers={len(self.blockers)}"
        )
        self.future_started_at = time.time()
        if self.enabled and self.vlm_enabled:
            self.last_vlm_request_at = self.future_started_at
        self.future_mode = mode
        self.future = self.worker_executor.submit(self._scene_worker)

    def _replace_worker_executor(self) -> None:
        old_executor = self.worker_executor
        self.worker_executor = ThreadPoolExecutor(max_workers=1)
        old_executor.shutdown(wait=False, cancel_futures=True)


def _blocker_to_dict(blocker: Any) -> dict[str, float | str]:
    return {
        "name": blocker.name,
        "x": blocker.x,
        "y": blocker.y,
        "radius": blocker.radius,
        "min_z": blocker.min_z,
        "max_z": blocker.max_z,
    }


def _safe_node_suffix(value: str) -> str:
    return "".join(char if char.isalnum() else "_" for char in value.lower())


def _read_bool_env(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() not in {"0", "false", "no"}


def _read_float_env(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def main(args=None) -> None:
    rclpy.init(args=args)
    node = VisualObserver()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.worker_executor.shutdown(wait=False, cancel_futures=True)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
