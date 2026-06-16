from __future__ import annotations

import os
import sys
import time
from typing import Any

import requests


def main() -> int:
    base_url = os.environ.get("SIM_VLM_BASE_URL", "http://10.8.0.132:11434").rstrip("/")
    model = os.environ.get(
        "SIM_OLLAMA_PREP_MODEL",
        os.environ.get("SIM_VLM_MODEL", os.environ.get("SIM_TEAM_OLLAMA_MODEL", "qwen3-vl:latest")),
    )
    unload_models = _csv_env("SIM_VISION_UNLOAD_MODELS", "magicoder:latest")
    timeout = _read_float_env("SIM_VISION_PREP_TIMEOUT_SEC", 45.0)
    warm = _read_bool_env("SIM_VISION_PREP_WARM", True)

    print(f"[vision-prep] Ollama base: {base_url}", flush=True)
    print(f"[vision-prep] Prep model: {model}", flush=True)

    loaded = _get_json(f"{base_url}/api/ps", timeout=8.0)
    loaded_names = []
    if loaded is not None:
        loaded_names = [item.get("name") for item in loaded.get("models", []) if isinstance(item, dict)]
    print(f"[vision-prep] Loaded models: {', '.join(loaded_names) if loaded_names else 'none'}", flush=True)

    for name in unload_models:
        if name and name in loaded_names and name != model:
            print(f"[vision-prep] Unloading stale model: {name}", flush=True)
            _post_json(
                f"{base_url}/api/generate",
                {"model": name, "prompt": "", "stream": False, "keep_alive": 0},
                timeout=12.0,
            )

    if warm:
        body = {
            "model": model,
            "prompt": 'Return JSON only: {"ok":true}',
            "stream": False,
            "think": False,
            "keep_alive": os.environ.get("SIM_VLM_KEEP_ALIVE", "10m"),
            "options": {
                "temperature": 0,
                "num_ctx": int(_read_float_env("SIM_VISION_PREP_NUM_CTX", 512.0)),
                "num_predict": int(_read_float_env("SIM_VISION_PREP_NUM_PREDICT", 256.0)),
            },
        }
        started = time.time()
        response = _post_json(f"{base_url}/api/generate", body, timeout=timeout)
        duration = time.time() - started
        text = _response_text(response).replace("\n", " ") if response else ""
        if text:
            print(f"[vision-prep] Warmed {model} in {duration:.1f}s: {text[:80]}", flush=True)
        else:
            print(f"[vision-prep] WARN: warmup did not return final text after {duration:.1f}s", flush=True)

    return 0


def _get_json(url: str, timeout: float) -> dict[str, Any] | None:
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        print(f"[vision-prep] WARN: request failed: {url}: {exc}", flush=True)
        return None


def _post_json(url: str, body: dict[str, Any], timeout: float) -> dict[str, Any] | None:
    try:
        response = requests.post(url, json=body, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        print(f"[vision-prep] WARN: request failed: {url}: {exc}", flush=True)
        return None


def _response_text(data: dict[str, Any] | None) -> str:
    if not isinstance(data, dict):
        return ""
    text = data.get("response", "")
    if not text:
        message = data.get("message", {})
        if isinstance(message, dict):
            text = message.get("content", "")
    return str(text).strip()


def _csv_env(name: str, default: str) -> list[str]:
    value = os.environ.get(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


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
