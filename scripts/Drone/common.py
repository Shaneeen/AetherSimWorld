"""Shared startup and world-loading helpers for drone scripts."""
from pathlib import Path
import json
import os
import requests
import socket
import subprocess
import sys
import time


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

STARTUP_LOG_PATH = REPO_ROOT / 'logs' / 'drone_main_startup.log'
DEFAULT_OLLAMA_TIMEOUT_SEC = 60.0
DEFAULT_SIMWORLD_EXE = r"D:\Windows\Windows\SimWorld.exe"
DEFAULT_SIMWORLD_MAP = "/Game/Maps/empty.umap"
DEFAULT_UNREALCV_PORT = 9000


def startup_log(message: str):
    STARTUP_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{timestamp}] {message}'
    print(line)
    with STARTUP_LOG_PATH.open('a', encoding='utf-8') as f:
        f.write(line + '\n')


def debug_enabled() -> bool:
    return os.environ.get('DEBUG_DRONE_AGENT', os.environ.get('DEBUG_PROMPT_AGENT', '0')) == '1'


def debug_log(label: str, value=None):
    if not debug_enabled():
        return
    if value is None:
        print(f'[debug] {label}')
        return
    if isinstance(value, (dict, list, tuple)):
        try:
            rendered = json.dumps(value, indent=2, default=str)
        except Exception:
            rendered = str(value)
    else:
        rendered = str(value)
    print(f'[debug] {label}: {rendered}')


def parse_numeric(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def get_ollama_timeout_sec() -> float:
    timeout = parse_numeric(os.environ.get('OLLAMA_TIMEOUT_SEC'), DEFAULT_OLLAMA_TIMEOUT_SEC)
    if timeout is None:
        return DEFAULT_OLLAMA_TIMEOUT_SEC
    return max(1.0, float(timeout))


def get_simworld_exe_path() -> Path:
    exe_path = os.environ.get('SIMWORLD_EXE', DEFAULT_SIMWORLD_EXE)
    return Path(exe_path)


def is_port_open(host: str, port: int, timeout_sec: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_sec):
            return True
    except OSError:
        return False


def maybe_launch_simworld():
    """Launch the UE server if requested and not already listening."""
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
    cmd = [str(exe_path), map_path]
    print(f'Launching SimWorld: {" ".join(cmd)}')
    creationflags = getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
    subprocess.Popen(cmd, creationflags=creationflags)
    return 'launched'


def wait_for_user_world_ready():
    """Pause until the user confirms the UE window finished loading."""
    print('When the world is fully loaded, press Enter or type 1, then press Enter.')
    while True:
        answer = input('Loaded? [Enter/1]: ').strip()
        if answer in ('', '1'):
            return
        print('Press Enter or type 1 when SimWorld is ready.')


def wait_for_simworld_server():
    """Wait until the UnrealCV port starts accepting connections."""
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


def parse_local_drone_command(text: str):
    lowered = str(text).strip().lower()
    if not lowered:
        return None
    if lowered in ('status', 'mode'):
        return ('status',)
    if lowered in ('help',):
        return ('help',)
    if lowered in ('quit', 'exit'):
        return ('quit',)
    return None


def parse_ollama_drone_action(obj: dict, raw_text: str):
    action = str(obj.get('action', '')).lower()
    if action == 'quit':
        return ('quit',)
    if action == 'help':
        return ('help',)
    if action == 'status':
        return ('status',)
    if action == 'above_nearest_tree':
        return ('above_nearest_tree',)
    if action == 'takeoff':
        altitude = parse_numeric(obj.get('altitude_cm'), None)
        return ('takeoff', altitude)
    if action == 'land':
        return ('land',)
    if action == 'hover':
        duration = parse_numeric(obj.get('duration_sec'), 1.0)
        return ('hover', max(0.0, float(duration)))
    if action == 'up':
        amount = parse_numeric(obj.get('amount_cm'), 100.0)
        return ('up', max(0.0, float(amount)))
    if action == 'down':
        amount = parse_numeric(obj.get('amount_cm'), 100.0)
        return ('down', max(0.0, float(amount)))
    if action == 'orbit':
        radius = parse_numeric(obj.get('radius_cm'), 700.0)
        return ('orbit', max(50.0, float(radius)))
    if action == 'goto':
        x = parse_numeric(obj.get('x'), None)
        y = parse_numeric(obj.get('y'), None)
        z = parse_numeric(obj.get('z'), None)
        if x is not None and y is not None:
            return ('goto', float(x), float(y), float(z) if z is not None else None)
        return ('unknown', raw_text)
    if action == 'move':
        dx = parse_numeric(obj.get('dx'), 0.0)
        dy = parse_numeric(obj.get('dy'), 0.0)
        dz = parse_numeric(obj.get('dz'), 0.0)
        return ('move', float(dx), float(dy), float(dz))
    if action == 'look':
        return ('look',)
    if action == 'view':
        return ('view',)
    return ('unknown', obj.get('raw_text', raw_text))


def ollama_parse_drone_command(text: str, model: str):
    url = os.environ.get('OLLAMA_API_URL', 'http://localhost:11434/api/generate')
    system = (
        "You are a command parser for a drone controller in SimWorld. "
        "Reply with exactly one JSON object and no markdown or explanation. "
        "Allowed actions are: above_nearest_tree, takeoff, land, hover, up, down, orbit, goto, move, look, view, status, help, quit, unknown. "
        "Interpret natural language freely and map the user to the closest valid action. "
        "Examples: "
        "'go above nearest tree', 'fly above the nearest tree', 'hover over the closest tree' -> above_nearest_tree. "
        "'take off', 'launch the drones' -> takeoff. "
        "'land', 'bring them down' -> land. "
        "'hover 2 seconds', 'stay there for 3 seconds' -> hover. "
        "'go up 200', 'ascend 200 cm' -> up. "
        "'go down 150', 'descend 150 cm' -> down. "
        "'orbit 700', 'circle around with radius 700' -> orbit. "
        "'goto 100 200 900', 'fly to x 100 y 200 z 900' -> goto. "
        "'move 100 0 0', 'shift right 100' -> move. "
        "'look around' -> look. "
        "'show view', 'open camera' -> view. "
        "Schema rules: "
        "takeoff => {\"action\":\"takeoff\",\"altitude_cm\":number|null}. "
        "hover => {\"action\":\"hover\",\"duration_sec\":number}. "
        "up/down => {\"action\":\"up\",\"amount_cm\":number}. "
        "orbit => {\"action\":\"orbit\",\"radius_cm\":number}. "
        "goto => {\"action\":\"goto\",\"x\":number,\"y\":number,\"z\":number|null}. "
        "move => {\"action\":\"move\",\"dx\":number,\"dy\":number,\"dz\":number}. "
        "unknown => {\"action\":\"unknown\",\"raw_text\":\"...\"}."
    )
    prompt = f"System:\n{system}\n\nUser:\n{text}\n\nRespond with the JSON only."
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }
    debug_log('drone_ollama_parse_input', {'text': text, 'model': model, 'payload': payload})
    try:
        resp = requests.post(url, json=payload, timeout=get_ollama_timeout_sec())
        resp.raise_for_status()
        body = resp.json()
        debug_log('drone_ollama_parse_response_body', body)
        out = body.get('response', '') if isinstance(body, dict) else ''
        if not out:
            return None
        obj = json.loads(out)
        debug_log('drone_ollama_parse_response_json', obj)
        return parse_ollama_drone_action(obj, text)
    except Exception as e:
        print(f'Ollama drone parse failed: {e}')
        return None
