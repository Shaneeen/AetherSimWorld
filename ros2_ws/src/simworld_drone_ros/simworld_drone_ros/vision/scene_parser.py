from __future__ import annotations

import json
import time
from typing import Any


def extract_json_object(text: str) -> dict[str, Any]:
    """Extract the first JSON object from a model response."""
    stripped = text.strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(stripped[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("scene response is not a JSON object")
    return parsed


def normalize_scene(raw: dict[str, Any], observer: str, source: str) -> dict[str, Any]:
    scene = dict(raw)
    scene["timestamp"] = float(scene.get("timestamp") or time.time())
    scene["observer"] = str(scene.get("observer") or observer)
    scene["source"] = source
    scene["confidence"] = _confidence(scene.get("confidence"), 0.0)
    scene["runner_visible"] = _bool_or_none(scene.get("runner_visible"))
    scene["visible_targets"] = _list_of_dicts(scene.get("visible_targets"))
    scene["visible_chasers"] = _string_list(scene.get("visible_chasers"))
    scene["visible_drones"] = _string_list(scene.get("visible_drones"))
    scene["occluders"] = _list_of_dicts(scene.get("occluders"))
    scene["nearest_cover"] = _optional_text(scene.get("nearest_cover"))
    scene["blocked_by"] = _optional_text(scene.get("blocked_by"))
    scene["recommended_search_area"] = _optional_text(scene.get("recommended_search_area"))
    scene["suggested_tactic"] = _optional_text(scene.get("suggested_tactic"))
    return scene


def fallback_scene(
    observer: str,
    poses: dict[str, tuple[float, float, float]],
    blockers: list[dict[str, float | str]],
) -> dict[str, Any]:
    """Pose-based fallback so downstream code can be tested without a VLM."""
    observer_pose = poses.get(observer)
    runner_pose = poses.get("red_1")
    blocked_by = None
    runner_visible = None
    if observer_pose is not None and runner_pose is not None:
        runner_visible = True
        for blocker in blockers:
            if _segment_distance_xy(observer_pose, runner_pose, blocker) <= float(blocker["radius"]):
                blocked_by = str(blocker["name"])
                runner_visible = False
                break
    visible_targets = []
    if runner_visible and runner_pose is not None:
        visible_targets.append(
            {
                "id": "red_1",
                "estimated_state": "pose_fallback",
            "confidence": 0.5,
            }
        )
    return normalize_scene(
        {
            "runner_visible": runner_visible,
            "visible_targets": visible_targets,
            "blocked_by": blocked_by,
            "recommended_search_area": "split_lanes" if runner_visible is False else None,
            "suggested_tactic": "use pose fallback; split search when sight is blocked",
            "confidence": 0.5 if runner_visible is not None else 0.0,
        },
        observer=observer,
        source="pose_fallback",
    )


def compact_scene_for_prompt(scene: dict[str, Any] | None) -> dict[str, Any] | None:
    if not scene:
        return None
    keys = (
        "timestamp",
        "observer",
        "source",
        "runner_visible",
        "visible_targets",
        "visible_drones",
        "occluders",
        "nearest_cover",
        "blocked_by",
        "recommended_search_area",
        "suggested_tactic",
        "confidence",
        "mission_goal",
    )
    return {key: scene.get(key) for key in keys if scene.get(key) is not None}


def _confidence(value: Any, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "visible"}:
            return True
        if lowered in {"0", "false", "no", "blocked", "not_visible"}:
            return False
    return None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _segment_distance_xy(
    first: tuple[float, float, float],
    second: tuple[float, float, float],
    blocker: dict[str, float | str],
) -> float:
    ax, ay = first[0], first[1]
    bx, by = second[0], second[1]
    cx, cy = float(blocker["x"]), float(blocker["y"])
    dx = bx - ax
    dy = by - ay
    length_sq = dx * dx + dy * dy
    if length_sq <= 0.0001:
        return ((ax - cx) ** 2 + (ay - cy) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((cx - ax) * dx + (cy - ay) * dy) / length_sq))
    px = ax + t * dx
    py = ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5
