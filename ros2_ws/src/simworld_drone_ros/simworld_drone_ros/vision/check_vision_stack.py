from __future__ import annotations

import json
import os
import sys
import time
import base64
from typing import Any

import requests

try:
    import unrealcv
except ImportError:
    unrealcv = None


def main() -> int:
    base_url = os.environ.get("SIM_VLM_BASE_URL", "http://10.8.0.132:11434").rstrip("/")
    model = os.environ.get("SIM_VLM_MODEL", "qwen3-vl:latest")
    timeout = _read_float_env("SIM_VISION_CHECK_TIMEOUT_SEC", 60.0)
    print(f"[vision-check] Ollama base: {base_url}", flush=True)
    print(f"[vision-check] VLM model: {model}", flush=True)

    ok = True
    tags = _get_json(f"{base_url}/api/tags", timeout=8.0)
    if tags is None:
        print("[vision-check] FAIL: /api/tags did not respond", flush=True)
        return 1
    names = [item.get("name") for item in tags.get("models", []) if isinstance(item, dict)]
    if model not in names:
        ok = False
        print(f"[vision-check] FAIL: model tag not found. Available: {', '.join(names)}", flush=True)
    else:
        print("[vision-check] OK: model tag exists", flush=True)

    show = _post_json(f"{base_url}/api/show", {"model": model}, timeout=20.0)
    if show is None:
        ok = False
        print("[vision-check] FAIL: /api/show did not respond for model", flush=True)
    else:
        capabilities = show.get("capabilities", [])
        print(f"[vision-check] model capabilities: {capabilities}", flush=True)
        if "vision" not in capabilities:
            ok = False
            print("[vision-check] FAIL: model does not report vision capability", flush=True)

    loaded = _get_json(f"{base_url}/api/ps", timeout=8.0)
    if loaded is not None:
        loaded_names = [item.get("name") for item in loaded.get("models", []) if isinstance(item, dict)]
        print(f"[vision-check] loaded models: {', '.join(loaded_names) if loaded_names else 'none'}", flush=True)
        if loaded_names and model not in loaded_names:
            print(
                f"[vision-check] WARN: requested model is not currently loaded; "
                f"Ollama may need to evict/load before responding",
                flush=True,
            )

    started = time.time()
    body = {
        "model": model,
        "prompt": 'Return JSON only: {"ok":true}',
        "stream": False,
        "think": False,
        "keep_alive": os.environ.get("SIM_VLM_KEEP_ALIVE", "10m"),
        "options": {
            "num_predict": int(_read_float_env("SIM_VISION_CHECK_NUM_PREDICT", 256.0)),
            "temperature": 0,
            "num_ctx": int(_read_float_env("SIM_VISION_CHECK_NUM_CTX", 512.0)),
        },
    }
    response = _post_json(f"{base_url}/api/generate", body, timeout=timeout)
    duration = time.time() - started
    if response is None:
        ok = False
        print(f"[vision-check] FAIL: tiny generate timed out or failed after {duration:.1f}s", flush=True)
    else:
        text = _response_text(response).replace("\n", " ")
        if not _final_response_text(response) and str(response.get("done_reason", "")) == "length":
            ok = False
            print(
                "[vision-check] FAIL: tiny generate stopped during thinking before final JSON; "
                "increase SIM_VISION_CHECK_NUM_PREDICT or use a faster VLM",
                flush=True,
            )
        else:
            print(f"[vision-check] OK: tiny generate returned in {duration:.1f}s: {text[:120]}", flush=True)

    frame = None
    if _read_bool_env("SIM_VISION_CHECK_UNREALCV", False) or _read_bool_env("SIM_VISION_CHECK_IMAGE_VLM", False):
        frame = _check_unrealcv_camera()
        ok = frame is not None and ok

    if frame is not None and _read_bool_env("SIM_VISION_CHECK_IMAGE_VLM", False):
        ok = _check_image_vlm(base_url, model, frame, timeout=max(timeout, 120.0)) and ok

    return 0 if ok else 2


def _get_json(url: str, timeout: float) -> dict[str, Any] | None:
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        print(f"[vision-check] request error: {url}: {exc}", flush=True)
        return None


def _post_json(url: str, body: dict[str, Any], timeout: float) -> dict[str, Any] | None:
    try:
        response = requests.post(url, json=body, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        print(f"[vision-check] request error: {url}: {exc}", flush=True)
        return None


def _check_unrealcv_camera() -> bytes | None:
    if unrealcv is None:
        print("[vision-check] FAIL: unrealcv Python package is not importable", flush=True)
        return None
    host = os.environ.get("SIMWORLD_HOST", "127.0.0.1")
    port = int(_read_float_env("SIMWORLD_PORT", 9000.0))
    camera_id = int(_read_float_env("SIM_VISION_CAMERA_ID", 0.0))
    camera_width = int(_read_float_env("SIM_VISION_CAMERA_WIDTH", 320.0))
    camera_height = int(_read_float_env("SIM_VISION_CAMERA_HEIGHT", 240.0))
    try:
        client = unrealcv.Client((host, port))
        client.connect()
        if not client.isconnected():
            print("[vision-check] FAIL: UnrealCV did not connect", flush=True)
            return None
        cameras = str(client.request("vget /cameras")).strip()
        client.request(f"vset /camera/{camera_id}/size {camera_width} {camera_height}")
        frame = client.request(f"vget /camera/{camera_id}/lit png")
        if not isinstance(frame, (bytes, bytearray)) or not frame:
            print("[vision-check] FAIL: UnrealCV camera returned no PNG bytes", flush=True)
            return None
        print(
            f"[vision-check] OK: UnrealCV cameras={cameras}, camera {camera_id} "
            f"size={camera_width}x{camera_height} frame bytes={len(frame)}",
            flush=True,
        )
        return bytes(frame)
    except Exception as exc:
        print(f"[vision-check] FAIL: UnrealCV camera check failed: {exc}", flush=True)
        return None


def _check_image_vlm(base_url: str, model: str, frame: bytes, timeout: float) -> bool:
    body = {
        "model": model,
        "prompt": (
            "Describe the image in one short JSON object. Return only valid JSON. "
            "Do not explain. Do not think step by step. Use this format: "
            "{\"visible_scene\":\"...\",\"objects\":[\"...\"],\"navigation_hint\":\"...\"}"
        ),
        "images": [base64.b64encode(frame).decode("ascii")],
        "stream": False,
        "think": False,
        "format": "json",
        "keep_alive": os.environ.get("SIM_VLM_KEEP_ALIVE", "10m"),
        "options": {
            "num_predict": int(_read_float_env("SIM_VISION_CHECK_IMAGE_NUM_PREDICT", 256.0)),
            "temperature": 0,
            "num_ctx": int(_read_float_env("SIM_VLM_NUM_CTX", 512.0)),
        },
    }
    started = time.time()
    response = _post_json(f"{base_url}/api/generate", body, timeout=timeout)
    duration = time.time() - started
    if response is None:
        print(f"[vision-check] FAIL: image VLM request failed after {duration:.1f}s", flush=True)
        return False
    if not _final_response_text(response) and str(response.get("done_reason", "")) == "length":
        print(
            f"[vision-check] FAIL: image VLM stopped during thinking before final JSON after {duration:.1f}s; "
            "increase SIM_VISION_CHECK_IMAGE_NUM_PREDICT or use a faster VLM",
            flush=True,
        )
        return False
    raw = _response_text(response).replace("\n", " ")
    if not raw:
        thinking = str(response.get("thinking", ""))[:160].replace("\n", " ")
        print(
            f"[vision-check] FAIL: image VLM returned empty response after {duration:.1f}s; "
            f"done_reason={response.get('done_reason')}; thinking={thinking!r}",
            flush=True,
        )
        return False
    print(f"[vision-check] OK: image VLM returned in {duration:.1f}s: {raw[:180]}", flush=True)
    return True


def _response_text(data: Any) -> str:
    text = _final_response_text(data)
    if text:
        return text
    if isinstance(data, dict):
        text = data.get("thinking", "")
    return str(text).strip()


def _final_response_text(data: Any) -> str:
    text = data.get("response", "") if isinstance(data, dict) else ""
    if not text and isinstance(data, dict):
        message = data.get("message", {})
        if isinstance(message, dict):
            text = message.get("content", "")
    return str(text).strip()


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


if __name__ == "__main__":
    sys.exit(main())
