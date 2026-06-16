from __future__ import annotations

from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

import requests


ROOT = Path(os.environ.get("SIMWORLD_ROOT", Path.cwd())).resolve()
LOGS_DIR = ROOT / "logs"
ROS_LOG_DIR = LOGS_DIR / "ros"
CHASE_LOG_DIR = LOGS_DIR / "chase_watch"
REPORT_DIR = LOGS_DIR / "run_reports"


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    inputs = _collect_inputs()
    summary = _build_summary(inputs)
    vlm_report = _ask_vlm(summary)
    report = _format_report(summary, vlm_report)
    report_path = REPORT_DIR / f"run_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    report_path.write_text(report, encoding="utf-8")
    _trim_old_reports(keep=2)
    print(f"[run-report] wrote {report_path}")
    return 0


def _collect_inputs() -> dict[str, Path | None]:
    latest_chase = _latest_file(CHASE_LOG_DIR, "chase_detail_*.log")
    ros_files = sorted(ROS_LOG_DIR.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True) if ROS_LOG_DIR.exists() else []
    all_ros_files = ros_files
    if latest_chase is not None:
        stat = latest_chase.stat()
        floor = min(stat.st_ctime, stat.st_mtime) - 120
        ros_files = [path for path in ros_files if path.stat().st_mtime >= floor]

    inputs: dict[str, Path | None] = {
        "chase": latest_chase,
        "bridge": _find_log(ros_files, "ue_bridge"),
        "target": _find_log(ros_files, "target_brain"),
        "chaser": _find_log(ros_files, "chaser_brain"),
        "red_coordinator": _prefer_named_or_content(ros_files, "team_red_coordinator.log", "red_team_coordinator"),
        "blue_coordinator": _prefer_named_or_content(ros_files, "team_blue_coordinator.log", "blue_team_coordinator"),
        "red_support": _prefer_named_or_content(ros_files, "team_red_support.log", "red_team_drone_controller"),
        "blue_support": _prefer_named_or_content(ros_files, "team_blue_support.log", "blue_team_drone_controller"),
        "vision": _find_log(ros_files, "visual_observer"),
    }
    if inputs["bridge"] is None:
        inputs["bridge"] = _find_log(all_ros_files[:80], "ue_bridge")
    return inputs


def _latest_file(folder: Path, pattern: str) -> Path | None:
    if not folder.exists():
        return None
    files = list(folder.glob(pattern))
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def _find_log(files: list[Path], needle: str) -> Path | None:
    for path in files:
        if needle in _read(path, limit=50000):
            return path
    return None


def _prefer_named_or_content(files: list[Path], name: str, needle: str) -> Path | None:
    for path in files:
        if path.name == name and path.stat().st_size > 0:
            return path
    return _find_log(files, needle)


def _read(path: Path | None, limit: int | None = None) -> str:
    if path is None or not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if limit is not None and len(text) > limit:
        return text[-limit:]
    return text


def _build_summary(inputs: dict[str, Path | None]) -> dict[str, Any]:
    chase = _read(inputs["chase"])
    bridge = _read(inputs["bridge"], limit=80000)
    red_coordinator = _read(inputs.get("red_coordinator"), limit=30000)
    blue_coordinator = _read(inputs.get("blue_coordinator"), limit=30000)
    red = _read(inputs["red_support"], limit=80000)
    blue = _read(inputs["blue_support"], limit=80000)
    vision = _read(inputs["vision"], limit=40000)
    target = _read(inputs["target"], limit=20000)
    chaser = _read(inputs["chaser"], limit=20000)
    all_text = "\n".join([chase, bridge, red_coordinator, blue_coordinator, red, blue, vision, target, chaser])

    eliminations = _unique_preserve_order(re.findall(r"Team elimination: ([^\n]+)", all_text))
    elimination_events = _parse_eliminations(eliminations)
    final_lines = re.findall(r"Team elimination (?:game over|final): [^\n]+", all_text)
    missing_pose_samples = re.findall(r"missing_poses=([^\n]+)", chase or red + "\n" + blue)
    live_old_status_count = len(re.findall(r"TARGET no target move yet \|\| CHASER no chaser commit yet", chase))
    errors = re.findall(r"(?im).*(ERROR|FAIL|Traceback|Exception|warning:|warning).*", all_text)

    blue_intents = _intent_counter(blue + "\n" + chase, team="blue")
    red_intents = _intent_counter(red + "\n" + chase, team="red")

    vision_ready = "Vision observer ready" in vision
    image_vlm_enabled = bool(re.search(r"Vision observer ready: .*image_vlm=1", vision))
    vision_request = "Vision observer request" in vision
    vision_scene = "Vision scene" in vision or "vision_scene" in all_text
    vision_warm_fallback = "Vision observer warm start" in vision
    image_frame_sizes = [int(value) for value in re.findall(r"frame_bytes=(\d+)", vision)]
    image_frame_seen = any(size > 0 for size in image_frame_sizes)
    vlm_response = bool(
        re.search(r"Vision observer response|source=vlm|source['\"]?\s*:\s*['\"]?vlm", all_text, re.I)
    )
    vlm_sources = re.findall(r"source=(vlm:[^\s,]+)", all_text, re.I)
    vlm_context_scene = any(source.endswith(":context") for source in vlm_sources)
    vlm_image_scene = any(not source.endswith(":context") for source in vlm_sources)
    coordinator_plan = "Team coordinator plan:" in all_text
    coordinator_accepted_vision = "Team coordinator accepted vision scene" in all_text
    vision_influenced_plan = bool(
        re.search(r"Team coordinator plan: .*vision hint|Team coordinator cached Ollama plan: .*vision", all_text, re.I)
    )
    red_vla_accepted_vision = bool(re.search(r"VLA accepted vision scene: team=red\b", all_text))
    blue_vla_accepted_vision = bool(re.search(r"VLA accepted vision scene: team=blue\b", all_text))
    red_vla_used_vision = bool(re.search(r"VLA used vision team=red source=vlm:", all_text))
    blue_vla_used_vision = bool(re.search(r"VLA used vision team=blue source=vlm:", all_text))
    vla_accepted_vision = red_vla_accepted_vision or blue_vla_accepted_vision or "VLA accepted vision scene" in all_text
    vla_used_vision = red_vla_used_vision or blue_vla_used_vision or "VLA used vision source=vlm:" in all_text
    vla_action = "vla_action=1" in all_text or "VLA " in all_text

    bridge_connected = "UE bridge connected to UnrealCV" in bridge
    swept_fallback = "swept movement unavailable" in bridge
    game_over = "Team elimination game over" in all_text or "all target drones are down" in all_text

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "input_files": {key: str(path) if path else None for key, path in inputs.items()},
        "run_health": {
            "bridge_connected_to_unrealcv": bridge_connected,
            "swept_movement_fallback": swept_fallback,
            "game_over_seen": game_over,
            "old_1v1_watcher_status_count": live_old_status_count,
            "error_or_warning_count": len(errors),
        },
        "eliminations": eliminations[-12:],
        "elimination_events": elimination_events,
        "elimination_counts_by_catcher": dict(Counter(event["caught_by"] for event in elimination_events)),
        "unique_targets_eliminated": sorted({event["target"] for event in elimination_events}),
        "final_lines": final_lines[-5:],
        "missing_pose_samples": missing_pose_samples[:8],
        "intent_repetition": {
            "blue_top_intents": blue_intents.most_common(8),
            "red_top_intents": red_intents.most_common(8),
        },
        "vlm_status": {
            "vision_log_found": inputs["vision"] is not None,
            "vision_ready": vision_ready,
            "vision_request_seen": vision_request,
            "vision_scene_seen": vision_scene,
            "vision_warm_fallback_seen": vision_warm_fallback,
            "vlm_image_enabled": image_vlm_enabled,
            "vlm_image_frame_seen": image_frame_seen,
            "vlm_image_frame_bytes_max": max(image_frame_sizes) if image_frame_sizes else 0,
            "vlm_response_or_publish_evidence": vlm_response,
            "vlm_context_scene_seen": vlm_context_scene,
            "vlm_image_scene_seen": vlm_image_scene,
            "coordinator_plan_seen": coordinator_plan,
            "coordinator_accepted_vision_seen": coordinator_accepted_vision,
            "vision_influenced_plan_seen": vision_influenced_plan,
        },
        "vla_status": {
            "vla_action_controller_seen": vla_action,
            "vla_accepted_vision_seen": vla_accepted_vision,
            "vla_used_vlm_vision_seen": vla_used_vision,
            "red_vla_accepted_vision_seen": red_vla_accepted_vision,
            "red_vla_used_vlm_vision_seen": red_vla_used_vision,
            "blue_vla_accepted_vision_seen": blue_vla_accepted_vision,
            "blue_vla_used_vlm_vision_seen": blue_vla_used_vision,
            "blue_finish_commit_seen": "VLA finish commit" in all_text,
            "blue_endgame_collapse_seen": "VLA endgame collapse" in all_text,
            "blue_assigned_pressure_seen": "VLA assigned pressure" in all_text,
        },
        "local_findings": _local_findings(
            game_over=game_over,
            swept_fallback=swept_fallback,
            vision_ready=vision_ready,
            image_vlm_enabled=image_vlm_enabled,
            image_frame_seen=image_frame_seen,
            vision_request=vision_request,
            vlm_response=vlm_response,
            vlm_image_scene=vlm_image_scene,
            bridge_log_found=inputs["bridge"] is not None,
            coordinator_plan=coordinator_plan,
            coordinator_accepted_vision=coordinator_accepted_vision,
            vision_influenced_plan=vision_influenced_plan,
            vla_accepted_vision=vla_accepted_vision,
            vla_used_vision=vla_used_vision,
            vla_action=vla_action,
            elimination_events=elimination_events,
            blue_intents=blue_intents,
            live_old_status_count=live_old_status_count,
            missing_pose_samples=missing_pose_samples,
        ),
    }


def _intent_counter(text: str, team: str) -> Counter[str]:
    counter: Counter[str] = Counter()
    role_marker = f"scope={team}"
    for line in text.splitlines():
        if role_marker not in line or "intent=" not in line:
            continue
        match = re.search(r"intent=(\{.*?\})(?:, missing_poses=|$)", line)
        if not match:
            continue
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        for value in data.values():
            counter[str(value)] += 1
    return counter


def _parse_eliminations(lines: list[str]) -> list[dict[str, Any]]:
    events = []
    pattern = re.compile(
        r"(?P<target>red_\d+) caught by (?P<catcher>blue_\d+) at (?P<distance>[0-9.]+) cm"
        r".*?catch=(?P<catch>[0-9.]+)"
    )
    for line in lines:
        match = pattern.search(line)
        if not match:
            continue
        events.append(
            {
                "target": match.group("target"),
                "caught_by": match.group("catcher"),
                "distance_cm": float(match.group("distance")),
                "catch_radius_cm": float(match.group("catch")),
            }
        )
    return events


def _local_findings(
    *,
    game_over: bool,
    swept_fallback: bool,
    vision_ready: bool,
    image_vlm_enabled: bool,
    image_frame_seen: bool,
    vision_request: bool,
    vlm_response: bool,
    vlm_image_scene: bool,
    bridge_log_found: bool,
    coordinator_plan: bool,
    coordinator_accepted_vision: bool,
    vision_influenced_plan: bool,
    vla_accepted_vision: bool,
    vla_used_vision: bool,
    vla_action: bool,
    elimination_events: list[dict[str, Any]],
    blue_intents: Counter[str],
    live_old_status_count: int,
    missing_pose_samples: list[str],
) -> list[str]:
    findings = []
    if game_over:
        findings.append("The run reached a team-elimination game-over condition.")
    else:
        findings.append("No clear game-over line was found in the reviewed logs.")
    if not bridge_log_found:
        findings.append("No bridge log was found for the reviewed run; bridge health and movement fidelity cannot be trusted.")
    if swept_fallback:
        findings.append("The bridge fell back from swept Unreal movement to direct UnrealCV movement.")
    if missing_pose_samples:
        findings.append("Team support initially had missing poses; this is common during startup but should clear quickly.")
    if live_old_status_count:
        findings.append("The watcher printed old 1v1 target/chaser status lines during team mode, which can be misleading.")
    if vision_ready and vision_request and not vlm_response:
        findings.append("The VLM observer started and requested a scene, but no VLM response/published scene was found.")
    elif vision_ready and vlm_response:
        findings.append("The VLM observer produced response/publish evidence.")
    else:
        findings.append("No useful VLM observer evidence was found.")
    if vision_ready and not image_vlm_enabled:
        findings.append("Image VLM was disabled for this run; only context VLM could produce scenes.")
    elif image_vlm_enabled and not image_frame_seen:
        findings.append("Image VLM was enabled, but no camera frame bytes were captured in the vision log.")
    elif image_vlm_enabled and image_frame_seen and not vlm_image_scene:
        findings.append("Image VLM captured camera frames, but no final image VLM scene was published.")
    if coordinator_accepted_vision:
        findings.append("A team coordinator accepted a fresh vision scene.")
    elif coordinator_plan:
        findings.append("A team coordinator published plans, but no coordinator vision acceptance was seen.")
    elif vision_ready:
        findings.append("No team coordinator plan evidence was found; coordinator runtime should be checked.")
    if not vision_influenced_plan:
        findings.append("No clear evidence was found that a coordinator plan changed because of a vision hint.")
    if not vla_action:
        findings.append("No explicit VLA action-controller evidence was found in the team logs.")
    elif vla_accepted_vision and vla_used_vision:
        findings.append("The VLA action layer accepted and used a fresh VLM vision scene.")
    elif vla_accepted_vision:
        findings.append("The VLA action layer accepted a vision scene, but no action intent showed VLM use.")
    if len(elimination_events) >= 3:
        catchers = Counter(str(event["caught_by"]) for event in elimination_events)
        top_catcher, top_count = catchers.most_common(1)[0]
        if top_count == len(elimination_events):
            findings.append(f"All confirmed catches came from {top_catcher}; support drones did not produce scoring evidence.")
    if blue_intents:
        top_intent, count = blue_intents.most_common(1)[0]
        if count >= 8:
            findings.append(f"Blue repeated the same intent many times ({count}x): {top_intent}")
    return findings


def _ask_vlm(summary: dict[str, Any]) -> str | None:
    if os.environ.get("SIM_RUN_REPORT_USE_VLM", "1").lower() in {"0", "false", "no"}:
        return _deterministic_supervisor_review(summary, "VLM reviewer disabled.")
    url = os.environ.get("SIM_RUN_REPORT_API_URL", os.environ.get("SIM_VLM_API_URL", ""))
    if not url:
        url = os.environ.get("OLLAMA_API_URL", "http://10.8.0.132:11434/api/generate")
    model = os.environ.get("SIM_RUN_REPORT_MODEL", "gpt-oss:latest")
    timeout = _read_float_env("SIM_RUN_REPORT_TIMEOUT_SEC", 0.0)
    request_timeout = None if timeout <= 0 else timeout
    prompt = _report_prompt(summary)
    body = {
        "model": model,
        "prompt": "/no_think\n" + prompt,
        "stream": False,
        "think": False,
        "keep_alive": os.environ.get("SIM_RUN_REPORT_KEEP_ALIVE", "10m"),
        "options": {
            "temperature": 0.2,
            "num_ctx": int(_read_float_env("SIM_RUN_REPORT_NUM_CTX", 4096.0)),
            "num_predict": int(_read_float_env("SIM_RUN_REPORT_NUM_PREDICT", 4096.0)),
        },
    }
    try:
        response = requests.post(url, json=body, timeout=request_timeout)
        response.raise_for_status()
        data = response.json()
        text = str(data.get("response", "")).strip()
        if text:
            return text
        done_reason = data.get("done_reason", "unknown")
        return _deterministic_supervisor_review(summary, f"VLM reviewer returned no final response; done_reason={done_reason}.")
    except Exception as exc:
        return _deterministic_supervisor_review(summary, f"VLM reviewer unavailable: {exc}")


def _report_prompt(summary: dict[str, Any]) -> str:
    compact = json.dumps(summary, indent=2)[:12000]
    return (
        "You are a supervising VLM reviewer for a SimWorld drone swarm-vs-swarm experiment. "
        "Review the run summary and write concise markdown. Return the final report immediately. "
        "Do not invent evidence. Do not show hidden reasoning, chain-of-thought, planning notes, or step-by-step analysis. "
        "If the bridge log is missing or bridge_connected_to_unrealcv is false, treat bridge health as unverified and do not claim it had no impact. "
        "The goal is to improve separate VLA-style planners for red defender and blue attacker. "
        "Include sections: Overall verdict, System health, VLM/VLA status, Blue attacker review, "
        "Red defender review, Next-run tuning, Open questions. "
        "If VLM evidence is missing, say so clearly. "
        f"Run summary JSON:\n{compact}"
    )


def _deterministic_supervisor_review(summary: dict[str, Any], note: str) -> str:
    run_health = summary.get("run_health", {})
    vlm_status = summary.get("vlm_status", {})
    vla_status = summary.get("vla_status", {})
    eliminated = summary.get("unique_targets_eliminated", [])
    eliminations = summary.get("eliminations", [])
    blue_counts = summary.get("elimination_counts_by_catcher", {})
    local_findings = summary.get("local_findings", [])
    blue_top = summary.get("intent_repetition", {}).get("blue_top_intents", [])
    red_top = summary.get("intent_repetition", {}).get("red_top_intents", [])
    top_blue = blue_top[0] if blue_top else ["none", 0]
    top_red = red_top[0] if red_top else ["none", 0]

    if run_health.get("game_over_seen"):
        verdict = f"Blue completed the red-elimination round: {len(eliminated)} target drones were caught."
    elif eliminated:
        verdict = f"Blue made partial progress: {len(eliminated)} target drones were caught, but no game-over was seen."
    else:
        verdict = "No red eliminations were confirmed in the reviewed logs."

    bridge = "verified connected" if run_health.get("bridge_connected_to_unrealcv") else "missing or unverified"
    movement = "direct UnrealCV fallback was used" if run_health.get("swept_movement_fallback") else "swept fallback was not reported"
    image_vlm = "yes" if vlm_status.get("vlm_image_scene_seen") else "no"
    context_vlm = "yes" if vlm_status.get("vlm_context_scene_seen") else "no"
    coordinator_plan = "yes" if vlm_status.get("coordinator_plan_seen") else "no"
    coordinator_accept = "yes" if vlm_status.get("coordinator_accepted_vision_seen") else "no"
    red_used = "yes" if vla_status.get("red_vla_used_vlm_vision_seen") else "no"
    blue_used = "yes" if vla_status.get("blue_vla_used_vlm_vision_seen") else "no"

    lines = [
        f"> Reviewer fallback note: {note}",
        "",
        "### Overall verdict",
        "",
        verdict,
        "",
        "### System health",
        "",
        f"- Bridge: {bridge}.",
        f"- Movement: {movement}.",
        f"- Game over seen: {bool(run_health.get('game_over_seen'))}.",
        f"- Errors/warnings counted: {run_health.get('error_or_warning_count', 0)}.",
        "",
        "### VLM/VLA status",
        "",
        f"- VLM context scene seen: {context_vlm}.",
        f"- VLM image scene seen: {image_vlm}.",
        f"- Coordinator plan seen: {coordinator_plan}.",
        f"- Coordinator accepted vision: {coordinator_accept}.",
        f"- Coordinator vision influence seen: {'yes' if vlm_status.get('vision_influenced_plan_seen') else 'no'}.",
        f"- Red VLA used VLM vision: {red_used}.",
        f"- Blue VLA used VLM vision: {blue_used}.",
        "",
        "### Blue attacker review",
        "",
        f"- Confirmed eliminations: {len(eliminations)}.",
        f"- Eliminations by catcher: {json.dumps(blue_counts, sort_keys=True)}.",
        f"- Most repeated blue intent: {top_blue[1]}x `{top_blue[0]}`.",
        "",
        "### Red defender review",
        "",
        f"- Red targets eliminated: {', '.join(eliminated) if eliminated else 'none'}.",
        f"- Most repeated red intent: {top_red[1]}x `{top_red[0]}`.",
        "",
        "### Next-run tuning",
        "",
        "- Keep checking the bridge `scoring_distance_cm` at reset so the round starts fair.",
        "- Keep image VLM disabled until image-scene latency is acceptable; context VLM is the current working evidence path.",
        "- If blue wins too quickly, tune red escape spacing or speed before changing the VLA evidence plumbing.",
        "",
        "### Open questions",
        "",
        "- Why did coordinator-level vision influence remain false while action-level VLA vision use was true?",
        "- Are direct UnrealCV fallback moves accurate enough for the VLA behavior you want to evaluate?",
    ]
    if local_findings:
        lines.extend(["", "### Local findings", ""])
        lines.extend(f"- {finding}" for finding in local_findings[:8])
    return "\n".join(lines)


def _format_report(summary: dict[str, Any], vlm_report: str | None) -> str:
    lines = [
        "# SimWorld Run Report",
        "",
        f"Generated: {summary['generated_at']}",
        "",
        "## Input Files",
        "",
    ]
    for key, path in summary["input_files"].items():
        lines.append(f"- {key}: `{path or 'not found'}`")
    lines.extend(
        [
            "",
            "## Deterministic Summary",
            "",
            "```json",
            json.dumps(summary, indent=2),
            "```",
            "",
            "## VLM Supervisor Review",
            "",
            vlm_report or "VLM reviewer was disabled or returned no text.",
            "",
        ]
    )
    return "\n".join(lines)


def _unique_preserve_order(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _trim_old_reports(keep: int) -> None:
    reports = sorted(REPORT_DIR.glob("run_report_*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in reports[keep:]:
        try:
            old.unlink()
        except OSError:
            pass


def _read_float_env(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


if __name__ == "__main__":
    sys.exit(main())
