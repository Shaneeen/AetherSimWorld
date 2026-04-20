from pathlib import Path
import json
import os
import re
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
DEFAULT_STEP_DURATION_SEC = 0.5


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
    match = re.fullmatch(r'(?:go to|walk to)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)', lowered)
    if match:
        return {'action': 'goto', 'x': float(match.group(1)), 'y': float(match.group(2))}

    semantic = parse_local_semantic_command(lowered)
    if semantic is not None:
        return semantic

    manual = parse_local_manual_move(lowered)
    if manual is not None:
        return manual

    return None


def parse_local_semantic_command(lowered: str):
    match = re.fullmatch(r'(?:go to|walk to)\s+(.+?)(?:\s+please)?', lowered)
    if not match:
        return None
    remainder = match.group(1)
    tokens = remainder.split()
    if not tokens:
        return None

    count = 1
    if tokens and re.fullmatch(r'\d+', tokens[0]):
        count = max(1, int(tokens.pop(0)))
    tokens = [token for token in tokens if token not in ('the', 'a', 'an')]
    if not tokens:
        return None

    selector = 'nearest'
    for candidate in ('visible', 'nearest', 'closest', 'furthest', 'farthest', 'another', 'different'):
        if candidate in tokens:
            selector = candidate
            tokens.remove(candidate)
            break

    if not tokens:
        return None

    raw_target = tokens[-1]
    target = normalize_semantic_target(raw_target)
    if target not in {'building', 'store', 'tree', 'trash'}:
        return None
    selector = normalize_selector(selector)
    visible_only = selector == 'visible'
    if visible_only:
        selector = 'nearest'
    return {
        'action': 'semantic_goto',
        'query': target,
        'visible_only': visible_only,
        'selector': selector,
        'count': count,
    }


def parse_local_manual_move(lowered: str):
    match = re.fullmatch(
        r'(?:take|go|move|walk)\s+'
        r'(?P<count>\d+(?:\.\d+)?)\s+'
        r'(?:(?:step|steps)\s+)?'
        r'(?P<direction>forward|backward|back|left|right)',
        lowered,
    )
    if not match:
        return None
    return {
        'action': 'manual_move',
        'steps': float(match.group('count')),
        'direction': normalize_step_direction(match.group('direction')),
    }


def normalize_semantic_target(raw_target: str) -> str:
    target = str(raw_target).strip().lower()
    mapping = {
        'buildings': 'building',
        'stores': 'store',
        'shop': 'store',
        'shops': 'store',
        'market': 'store',
        'markets': 'store',
        'trees': 'tree',
        'bin': 'trash',
        'bins': 'trash',
        'garbage': 'trash',
    }
    return mapping.get(target, target)


def normalize_selector(raw_selector: str) -> str:
    selector = str(raw_selector).strip().lower()
    mapping = {
        'closest': 'nearest',
        'furthest': 'farthest',
        'another': 'different',
    }
    return mapping.get(selector, selector)


def normalize_step_direction(raw_direction: str) -> str:
    direction = str(raw_direction).strip().lower()
    mapping = {
        'back': 'backward',
    }
    return mapping.get(direction, direction)


def parse_ollama_command(text: str, model: str):
    url = os.environ.get('OLLAMA_API_URL', 'http://localhost:11434/api/generate')
    system = (
        "You are a command parser for an ultra humanoid in SimWorld. "
        "Reply with exactly one JSON object and no markdown. "
        "Allowed actions are: semantic_goto, goto, manual_move, look, status, help, quit, sequence, unknown. "
        "Use semantic_goto for nearest/visible/farthest/another/different object queries like building, store, tree, trash. "
        "Use goto for numeric coordinates. "
        "Use manual_move for local body-relative moves like 5 steps forward, 2 steps left, or 1 step backward. "
        "Use sequence for multi-step requests such as visiting several different objects. "
        "Schemas: "
        "{\"action\":\"semantic_goto\",\"query\":\"nearest building\",\"visible_only\":false,\"selector\":\"nearest\",\"count\":1}. "
        "Valid selector values are nearest, farthest, another, different. "
        "\"count\" must be a positive integer and means how many distinct visits to attempt. "
        "{\"action\":\"goto\",\"x\":100,\"y\":200}. "
        "{\"action\":\"manual_move\",\"steps\":5,\"direction\":\"left\"}. "
        "{\"action\":\"sequence\",\"steps\":[{\"action\":\"semantic_goto\",\"query\":\"tree\",\"selector\":\"different\",\"count\":3}]}. "
        "{\"action\":\"look\"}. {\"action\":\"status\"}. {\"action\":\"help\"}. {\"action\":\"quit\"}. "
        "{\"action\":\"unknown\",\"raw_text\":\"...\"}. "
        "Examples: "
        "\"go to the nearest tree\" -> {\"action\":\"semantic_goto\",\"query\":\"tree\",\"visible_only\":false,\"selector\":\"nearest\",\"count\":1}. "
        "\"go to the furthest tree\" -> {\"action\":\"semantic_goto\",\"query\":\"tree\",\"visible_only\":false,\"selector\":\"farthest\",\"count\":1}. "
        "\"go to another tree\" -> {\"action\":\"semantic_goto\",\"query\":\"tree\",\"visible_only\":false,\"selector\":\"different\",\"count\":1}. "
        "\"go to a different tree\" -> {\"action\":\"semantic_goto\",\"query\":\"tree\",\"visible_only\":false,\"selector\":\"different\",\"count\":1}. "
        "\"walk to 3 different trees\" -> {\"action\":\"semantic_goto\",\"query\":\"tree\",\"visible_only\":false,\"selector\":\"different\",\"count\":3}. "
        "\"go to the visible store\" -> {\"action\":\"semantic_goto\",\"query\":\"store\",\"visible_only\":true,\"selector\":\"nearest\",\"count\":1}. "
        "\"take 5 steps left\" -> {\"action\":\"manual_move\",\"steps\":5,\"direction\":\"left\"}. "
        "\"go 5 steps forward\" -> {\"action\":\"manual_move\",\"steps\":5,\"direction\":\"forward\"}."
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
