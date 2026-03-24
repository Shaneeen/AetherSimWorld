from pathlib import Path
import json
import os
import socket
import subprocess
import sys
import time

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_OLLAMA_TIMEOUT_SEC = 60.0
DEFAULT_SIMWORLD_EXE = r"D:\Windows\Windows\SimWorld.exe"
DEFAULT_SIMWORLD_MAP = "/Game/Maps/empty.umap"
DEFAULT_UNREALCV_PORT = 9000


def debug_enabled() -> bool:
    return os.environ.get('DEBUG_ULTRA_HUMANOID', os.environ.get('DEBUG_PROMPT_AGENT', '0')) == '1'


def debug_log(label: str, value=None):
    if not debug_enabled():
        return
    if value is None:
        print(f'[debug] {label}')
        return
    if isinstance(value, (dict, list, tuple)):
        try:
            value = json.dumps(value, indent=2, default=str)
        except Exception:
            value = str(value)
    print(f'[debug] {label}: {value}')


def parse_numeric(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def get_ollama_timeout_sec() -> float:
    timeout = parse_numeric(os.environ.get('OLLAMA_TIMEOUT_SEC'), DEFAULT_OLLAMA_TIMEOUT_SEC)
    return max(1.0, float(timeout if timeout is not None else DEFAULT_OLLAMA_TIMEOUT_SEC))


def get_simworld_exe_path() -> Path:
    return Path(os.environ.get('SIMWORLD_EXE', DEFAULT_SIMWORLD_EXE))


def is_port_open(host: str, port: int, timeout_sec: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_sec):
            return True
    except OSError:
        return False


def maybe_launch_simworld():
    if os.environ.get('SIMWORLD_AUTO_LAUNCH', '0') != '1':
        return 'disabled'
    host = os.environ.get('SIMWORLD_HOST', '127.0.0.1')
    port = int(os.environ.get('SIMWORLD_PORT', str(DEFAULT_UNREALCV_PORT)))
    if is_port_open(host, port, timeout_sec=0.5):
        print(f'SimWorld already listening on {host}:{port}, reusing existing server.')
        return 'reused'
    exe_path = get_simworld_exe_path()
    if not exe_path.exists():
        raise FileNotFoundError(f'SimWorld executable not found: {exe_path}')
    map_path = os.environ.get('SIMWORLD_MAP_PATH', DEFAULT_SIMWORLD_MAP)
    subprocess.Popen([str(exe_path), map_path], creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
    return 'launched'


def wait_for_user_world_ready():
    print('When the world is fully loaded, press Enter or type 1, then press Enter.')
    while True:
        answer = input('Loaded? [Enter/1]: ').strip()
        if answer in ('', '1'):
            return
        print('Press Enter or type 1 when SimWorld is ready.')


def wait_for_simworld_server():
    host = os.environ.get('SIMWORLD_HOST', '127.0.0.1')
    port = int(os.environ.get('SIMWORLD_PORT', str(DEFAULT_UNREALCV_PORT)))
    timeout_sec = float(os.environ.get('SIMWORLD_START_TIMEOUT_SEC', '120'))
    deadline = time.time() + timeout_sec
    print(f'Waiting for SimWorld on {host}:{port}...')
    while time.time() < deadline:
        if is_port_open(host, port, timeout_sec=0.5):
            print('SimWorld is ready.')
            return
        time.sleep(1.0)
    raise TimeoutError(f'SimWorld did not start listening on {host}:{port} within {timeout_sec:.0f} seconds')


def parse_local_command(text: str):
    lowered = str(text).strip().lower()
    if not lowered:
        return None
    if lowered in ('quit', 'exit'):
        return {'action': 'quit'}
    if lowered in ('help',):
        return {'action': 'help'}
    if lowered in ('status', 'where'):
        return {'action': 'status'}
    if lowered in ('look', 'scan'):
        return {'action': 'look'}
    if lowered.startswith('go to ') or lowered.startswith('walk to ') or lowered.startswith('find '):
        query = lowered.replace('walk to ', '').replace('go to ', '').replace('find ', '', 1).strip()
        visible_only = 'visible' in query
        if any(token in query for token in ('building', 'store', 'shop', 'tree', 'trash', 'bin', 'marker')):
            return {'action': 'semantic_goto', 'query': query, 'visible_only': visible_only}
    return None


def parse_ollama_command(text: str, model: str):
    url = os.environ.get('OLLAMA_API_URL', 'http://localhost:11434/api/generate')
    system = (
        "You are a command parser for an ultra humanoid in SimWorld. "
        "Reply with exactly one JSON object and no markdown. "
        "Allowed actions are: semantic_goto, goto, look, status, help, quit, unknown. "
        "Use semantic_goto for nearest/visible object queries like building, store, tree, trash. "
        "Use goto for numeric coordinates. "
        "Schemas: "
        "{\"action\":\"semantic_goto\",\"query\":\"nearest building\",\"visible_only\":false}. "
        "{\"action\":\"goto\",\"x\":100,\"y\":200}. "
        "{\"action\":\"look\"}. {\"action\":\"status\"}. {\"action\":\"help\"}. {\"action\":\"quit\"}. "
        "{\"action\":\"unknown\",\"raw_text\":\"...\"}."
    )
    payload = {"model": model, "prompt": f"System:\n{system}\n\nUser:\n{text}\n\nRespond with JSON only.", "stream": False, "format": "json", "options": {"temperature": 0}}
    try:
        resp = requests.post(url, json=payload, timeout=get_ollama_timeout_sec())
        resp.raise_for_status()
        body = resp.json()
        out = body.get('response', '') if isinstance(body, dict) else ''
        return json.loads(out) if out else None
    except Exception as e:
        print(f'Ollama parse failed: {e}')
        return None
