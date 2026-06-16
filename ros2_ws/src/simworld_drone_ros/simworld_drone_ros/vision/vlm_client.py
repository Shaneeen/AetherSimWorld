from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import time
from typing import Any

import requests

from simworld_drone_ros.vision.scene_parser import extract_json_object, normalize_scene


class OllamaVlmClient:
    """Small Ollama generate API client for image-to-scene JSON."""

    def __init__(self) -> None:
        urls = os.environ.get("SIM_VLM_API_URLS", os.environ.get("SIM_VLM_API_URL", ""))
        if not urls:
            urls = os.environ.get("OLLAMA_API_URLS", os.environ.get("OLLAMA_API_URL", ""))
        if not urls:
            urls = "http://10.8.0.132:11434/api/generate"
        self.urls = [url.strip() for url in urls.split(",") if url.strip()]
        self.model = os.environ.get("SIM_VLM_MODEL", os.environ.get("OLLAMA_VLM_MODEL", "qwen3-vl:latest"))
        self.timeout = _read_float_env("SIM_VLM_TIMEOUT_SEC", _read_float_env("OLLAMA_TIMEOUT_SEC", 90.0))
        self.num_ctx = int(_read_float_env("SIM_VLM_NUM_CTX", 512.0))
        self.num_predict = int(_read_float_env("SIM_VLM_NUM_PREDICT", 256.0))
        self.keep_alive = os.environ.get("SIM_VLM_KEEP_ALIVE", "10m")
        self.mission_goal = _load_mission_goal()

    def describe_scene(
        self,
        image_bytes: bytes,
        observer: str,
        poses: dict[str, tuple[float, float, float]],
        known_blockers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        body = {
            "model": self.model,
            "prompt": self._prompt(observer, poses, known_blockers),
            "images": [base64.b64encode(image_bytes).decode("ascii")],
            "stream": False,
            "think": False,
            "format": "json",
            "keep_alive": self.keep_alive,
            "options": {
                "temperature": 0,
                "num_ctx": max(256, self.num_ctx),
                "num_predict": max(64, self.num_predict),
            },
        }
        errors = []
        for url in self.urls:
            try:
                started = time.time()
                response = requests.post(url, json=body, timeout=max(1.0, self.timeout))
                response.raise_for_status()
                outer = response.json()
                raw = _response_text(outer)
                if not _final_response_text(outer) and _done_reason(outer) == "length":
                    raise RuntimeError(
                        f"{url} VLM stopped during thinking before final JSON; "
                        "increase SIM_VLM_NUM_PREDICT or use a faster/less verbose VLM"
                    )
                if not raw:
                    done_reason = outer.get("done_reason", "unknown") if isinstance(outer, dict) else "unknown"
                    thinking = str(outer.get("thinking", ""))[:160] if isinstance(outer, dict) else ""
                    raise RuntimeError(
                        f"{url} empty VLM response; done_reason={done_reason}; thinking={thinking!r}"
                    )
                scene = normalize_scene(extract_json_object(raw), observer=observer, source=f"vlm:{self.model}")
                _repair_image_scene(scene)
                scene["mission_goal"] = self.mission_goal
                scene["vlm_duration_sec"] = round(time.time() - started, 2)
                return scene
            except Exception as exc:
                errors.append(str(exc))
        raise RuntimeError("VLM endpoints failed: " + " | ".join(errors))

    def describe_context_scene(
        self,
        observer: str,
        poses: dict[str, tuple[float, float, float]],
        known_blockers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        body = {
            "model": self.model,
            "prompt": self._context_prompt(observer, poses, known_blockers),
            "stream": False,
            "think": False,
            "format": "json",
            "keep_alive": self.keep_alive,
            "options": {
                "temperature": 0,
                "num_ctx": max(256, self.num_ctx),
                "num_predict": max(64, self.num_predict),
            },
        }
        errors = []
        for url in self.urls:
            try:
                started = time.time()
                response = requests.post(url, json=body, timeout=max(1.0, min(self.timeout, 30.0)))
                response.raise_for_status()
                outer = response.json()
                raw = _response_text(outer)
                if not _final_response_text(outer) and _done_reason(outer) == "length":
                    raise RuntimeError(
                        f"{url} VLM context stopped during thinking before final JSON; "
                        "increase SIM_VLM_NUM_PREDICT or use a faster/less verbose VLM"
                    )
                if not raw:
                    done_reason = outer.get("done_reason", "unknown") if isinstance(outer, dict) else "unknown"
                    thinking = str(outer.get("thinking", ""))[:160] if isinstance(outer, dict) else ""
                    raise RuntimeError(
                        f"{url} empty VLM context response; done_reason={done_reason}; thinking={thinking!r}"
                    )
                scene = normalize_scene(extract_json_object(raw), observer=observer, source=f"vlm:{self.model}:context")
                scene["mission_goal"] = self.mission_goal
                scene["vlm_duration_sec"] = round(time.time() - started, 2)
                return scene
            except Exception as exc:
                errors.append(str(exc))
        raise RuntimeError("VLM context endpoints failed: " + " | ".join(errors))

    def _prompt(
        self,
        observer: str,
        poses: dict[str, tuple[float, float, float]],
        known_blockers: list[dict[str, Any]],
    ) -> str:
        known_ids = ",".join(sorted(poses))
        blocker_names = ",".join(str(blocker.get("name", "")) for blocker in known_blockers[:5] if blocker.get("name"))
        return (
            "Describe the image in one short JSON object. Return only valid JSON. "
            "Do not explain. Do not think step by step. "
            "Analyze this SimWorld drone camera frame. "
            f"Mission goal={self.mission_goal}. "
            f"Observer={observer}. Known drone ids={known_ids}. Known blockers={blocker_names or 'none'}. "
            "Use the image for visibility. Do not explain. "
            "Schema: {\"runner_visible\":true,\"visible_targets\":[{\"id\":\"red_1\",\"confidence\":0.0}],"
            "\"visible_chasers\":[\"blue_1\"],\"visible_drones\":[\"red_1\",\"blue_1\"],"
            "\"blocked_by\":null,\"recommended_search_area\":null,\"suggested_tactic\":\"short hint\","
            "\"confidence\":0.0}"
        )

    def _context_prompt(
        self,
        observer: str,
        poses: dict[str, tuple[float, float, float]],
        known_blockers: list[dict[str, Any]],
    ) -> str:
        pose_obj = {
            name: {"x": round(pose[0], 1), "y": round(pose[1], 1), "z": round(pose[2], 1)}
            for name, pose in poses.items()
        }
        context = {
            "observer": observer,
            "poses_cm": pose_obj,
            "known_blockers": known_blockers[:5],
        }
        return (
            "Return only valid JSON. Do not explain. Do not think step by step. "
            "You are a VLM supervisor for a SimWorld drone camera scene. "
            "Use this live observation context as a low-confidence scene estimate while image VLM is unavailable. "
            f"Mission goal={self.mission_goal}. "
            f"Context={json.dumps(context, separators=(',', ':'))}. "
            "Schema: {\"runner_visible\":true,\"visible_targets\":[{\"id\":\"red_1\",\"confidence\":0.45}],"
            "\"visible_chasers\":[\"blue_1\"],\"visible_drones\":[\"red_1\",\"blue_1\"],"
            "\"blocked_by\":null,\"recommended_search_area\":\"center_lane\","
            "\"suggested_tactic\":\"short tactical hint for team planner\",\"confidence\":0.45}"
        )


def _read_float_env(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _response_text(data: Any) -> str:
    text = _final_response_text(data)
    if text:
        return text
    if isinstance(data, dict):
        return str(data.get("thinking", "")).strip()
    return ""


def _final_response_text(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    text = data.get("response", "")
    if not text:
        message = data.get("message", {})
        if isinstance(message, dict):
            text = message.get("content", "")
    return str(text).strip()


def _done_reason(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    return str(data.get("done_reason", "")).strip()


def _repair_image_scene(scene: dict[str, Any]) -> None:
    has_visual_evidence = (
        scene.get("runner_visible") is not None
        or bool(scene.get("visible_targets"))
        or bool(scene.get("visible_chasers"))
        or bool(scene.get("visible_drones"))
    )
    confidence = float(scene.get("confidence", 0.0) or 0.0)
    if has_visual_evidence and confidence <= 0.0:
        scene["confidence"] = 0.55
    if not scene.get("suggested_tactic"):
        if scene.get("runner_visible") is True:
            scene["suggested_tactic"] = "camera sees runner; maintain visual contact and avoid stacking"
        elif scene.get("runner_visible") is False:
            scene["suggested_tactic"] = "camera does not see runner; split search from last known lane"


def _load_mission_goal() -> str:
    explicit = os.environ.get("SIM_VISION_MISSION_GOAL", "").strip()
    if explicit:
        return explicit[:700]

    env_path = os.environ.get("SIM_VISION_MISSION_GOAL_FILE", "").strip()
    candidates: list[Path] = []
    if env_path:
        candidates.append(Path(env_path))
    sim_root = os.environ.get("SIMWORLD_ROOT", "").strip()
    if sim_root:
        candidates.append(Path(sim_root) / "overview" / "future_plan.md")
    candidates.append(Path.cwd() / "overview" / "future_plan.md")
    for parent in Path(__file__).resolve().parents:
        candidates.append(parent / "overview" / "future_plan.md")

    for candidate in candidates:
        try:
            if not candidate.is_file():
                continue
            text = candidate.read_text(encoding="utf-8", errors="replace")
            goal = _extract_main_research_target(text)
            if goal:
                return goal[:700]
        except OSError:
            continue
    return (
        "Build VLM-supervised VLA drone swarm intelligence: camera/context to scene interpretation, "
        "team VLA role planning, safe validated controller actions, run review, and next-run tactical tuning."
    )


def _extract_main_research_target(text: str) -> str:
    lines = text.splitlines()
    collecting = False
    picked: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## ") and "Main Research Target" in stripped:
            collecting = True
            continue
        if collecting and stripped.startswith("## "):
            break
        if collecting and stripped and not stripped.startswith("```"):
            picked.append(stripped.lstrip("- ").strip())
    return " ".join(picked)
