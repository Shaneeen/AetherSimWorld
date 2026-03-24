from pathlib import Path
import json
import os
import requests
import socket
import subprocess
import sys
import time

from simworld.utils.vector import Vector

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

STARTUP_LOG_PATH = REPO_ROOT / 'logs' / 'prompt_agent_startup.log'

DEFAULT_OLLAMA_TIMEOUT_SEC = 60.0
DEFAULT_SIMWORLD_EXE = r"D:\Windows\Windows\SimWorld.exe"
DEFAULT_SIMWORLD_MAP = "/Game/Maps/empty.umap"
DEFAULT_UNREALCV_PORT = 9000

STEP_DURATION = 0.5
DEFAULT_TURN_ANGLE = 90.0
MAX_STEP_DURATION = 5.0
DEFAULT_WALK_SPEED_CM_PER_SEC = 200.0
CALIBRATION_STEP_DURATION = 0.5
NAVIGATION_SCAN_RADIUS = 4000.0
NAVIGATION_STOP_DISTANCE = 350.0
NAVIGATION_STEP_LIMIT = 2.5
GOTO_STOP_DISTANCE = 20.0
GOTO_MAX_ITERS = 16
STUCK_DISTANCE_EPS = 15.0
STUCK_MAX_COUNT = 2
GOTO_TURN_DEADBAND_DEG = 8.0
GOTO_MAX_TURN_DEG = 45.0
GOTO_DISTANCE_DIVISOR = 5.0
GOTO_ITER_DISTANCE_CM = 200.0
GOTO_MAX_TIME_SEC = 60.0
GOTO_FINAL_WALK_DISTANCE_CM = 200.0
GOTO_FINAL_APPROACH_TRIGGER_CM = 150.0
GOTO_FINAL_APPROACH_WALK_CM = 75.0
GOTO_FINAL_APPROACH_STOP_DISTANCE_CM = 200.0
SURVEY_SWEEP_ANGLES = (0.0, 180.0)
VISIBLE_FOV_DEG = 100.0
MASK_MIN_PIXELS = 40
MAX_SURVEY_OPTIONS = 6
IGNORED_OBJECT_PATTERNS = (
    'gen_bp_humanoid_',
    'chaosdebugdrawactor',
    'hud_',
    'particleeventmanager_',
    'gameplaydebugger',
    'smartobjectsubsystemrenderingactor',
    'massvisualizer',
    'unrealcvworldcontroller',
    'buoyancymanager',
    'gen_bp_uemanager',
    'gamenetworkmanager',
    'worldsettings',
    'gamemodebase',
    'gamesession',
    'gamestatebase',
    'playerstate_',
    'playercontroller_',
    'aicontroller_',
    'defaultmap',
    'abstractnavdata',
    'defaultphysicsvolume',
    'playercameramanager',
    'defaultpawn_',
    'skylight_',
    'skyatmosphere_',
    'volumetriccloud_',
    'directionallight_',
    'floor_',
    'staticmeshactor_',
)

_walk_speed_cm_per_sec = DEFAULT_WALK_SPEED_CM_PER_SEC


def startup_log(message: str):
    STARTUP_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{timestamp}] {message}'
    print(line)
    with STARTUP_LOG_PATH.open('a', encoding='utf-8') as f:
        f.write(line + '\n')


def debug_enabled() -> bool:
    return os.environ.get('DEBUG_PROMPT_AGENT', '0') == '1'


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


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


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


def get_walk_speed_cm_per_sec() -> float:
    return _walk_speed_cm_per_sec


def set_walk_speed_cm_per_sec(value: float):
    global _walk_speed_cm_per_sec
    _walk_speed_cm_per_sec = max(1.0, float(value))


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


def extract_coordinate_pair(text: str):
    matches = []
    current = ''
    for ch in str(text):
        if ch.isdigit() or ch in '.-+':
            current += ch
        else:
            if current not in ('', '+', '-', '.', '+.', '-.'):
                matches.append(current)
            current = ''
    if current not in ('', '+', '-', '.', '+.', '-.'):
        matches.append(current)
    if len(matches) < 2:
        return None
    x = parse_numeric(matches[0])
    y = parse_numeric(matches[1])
    if x is None or y is None:
        return None
    return Vector(float(x), float(y))


def looks_like_semantic_navigation(text: str) -> bool:
    lowered = str(text).strip().lower()
    semantic_markers = (
        'nearest', 'closest', 'building', 'tree', 'store', 'shop', 'trash', 'bin',
        'crossing', 'zebra', 'lamp', 'sign', 'car', 'house', 'office', 'kiosk',
        'bench', 'pole', 'road', 'door', 'tower', 'left', 'right', 'taller', 'shorter',
    )
    return any(marker in lowered for marker in semantic_markers)


def parse_local_command(text: str):
    lowered = str(text).strip().lower()
    if not lowered:
        return None

    directional_selection_phrases = (
        ('left', ('left tree', 'left one', 'the left tree', 'the left one', 'tree on the left', 'left option')),
        ('right', ('right tree', 'right one', 'the right tree', 'the right one', 'tree on the right', 'right option')),
    )
    selection_prefixes = ('go to ', 'walk to ', 'pick ', 'choose ', '')
    for direction, phrases in directional_selection_phrases:
        for prefix in selection_prefixes:
            for phrase in phrases:
                if lowered == f'{prefix}{phrase}'.strip():
                    return ('goto_directional_option', direction)

    semantic_prefixes = (
        'go to the ', 'go to ', 'walk to the ', 'walk to ', 'head to the ',
        'head to ', 'find the ', 'find a ', 'find an ',
    )
    if looks_like_semantic_navigation(lowered):
        for prefix in semantic_prefixes:
            if lowered.startswith(prefix):
                query = text.strip()[len(prefix):].strip()
                if query:
                    return ('navigate_to_query', query)

    if lowered.startswith('go to option ') or lowered.startswith('goto option '):
        suffix = lowered.split('option ', 1)[1]
        index = parse_numeric(suffix, None)
        if index is not None:
            return ('goto_option', int(index))

    if lowered in ('show options', 'list options', 'options', 'show candidates', 'list candidates'):
        return ('show_options',)

    if lowered.startswith('survey '):
        return ('survey', text.strip()[7:].strip())
    if lowered.startswith('scan for '):
        return ('survey', text.strip()[9:].strip())
    if lowered.startswith('find options for '):
        return ('survey', text.strip()[17:].strip())

    return None


def parse_ollama_action(obj: dict, raw_text: str):
    action = str(obj.get('action', '')).lower()
    if action == 'walk_steps':
        return ('walk_steps', parse_numeric(obj.get('steps'), 1.0))
    if action == 'turn':
        direction = str(obj.get('direction', 'left')).lower()
        if direction not in ('left', 'right'):
            direction = 'left'
        return ('turn', direction, parse_numeric(obj.get('angle'), DEFAULT_TURN_ANGLE))
    if action == 'stop':
        return ('stop',)
    if action == 'where':
        return ('where',)
    if action == 'view':
        return ('view',)
    if action == 'look':
        return ('look',)
    if action == 'caption':
        return ('caption',)
    if action == 'explore':
        return ('explore',)
    if action == 'goto':
        x = parse_numeric(obj.get('x'), None)
        y = parse_numeric(obj.get('y'), None)
        if x is not None and y is not None:
            return ('goto', Vector(float(x), float(y)))
        extracted = extract_coordinate_pair(raw_text)
        if extracted is not None:
            return ('goto', extracted)
        if looks_like_semantic_navigation(raw_text):
            return ('navigate_to_query', raw_text.strip())
        return ('unknown', raw_text)
    if action == 'navigate_to_query':
        return ('navigate_to_query', str(obj.get('query', raw_text)).strip())
    if action == 'goto_option':
        option_index = parse_numeric(obj.get('option'), None)
        if option_index is not None:
            return ('goto_option', int(option_index))
        return ('unknown', raw_text)
    if action == 'survey':
        return ('survey', str(obj.get('query', raw_text)).strip())
    if action == 'help':
        return ('help',)
    if action == 'quit':
        return ('quit',)
    return ('unknown', obj.get('raw_text', raw_text))


def ollama_parse_command(text: str, model: str):
    url = os.environ.get('OLLAMA_API_URL', 'http://localhost:11434/api/generate')
    system = (
        "You are a command parser for a humanoid in SimWorld. "
        "Reply with exactly one JSON object and no markdown or explanation. "
        "Allowed actions are: walk_steps, turn, stop, where, view, look, caption, explore, goto, navigate_to_query, help, quit, unknown. "
        "Interpret natural language freely. "
        "If the user asks for multiple actions in one sentence, return them in an action_sequence array in execution order. "
        "Examples: "
        "'walk forward', 'go ahead', 'move a bit', 'walk 5 steps', 'move forward 3 steps' -> walk_steps. "
        "'turn left', 'rotate right 45 degrees', 'turn around' -> turn. "
        "'turn right and walk 5 steps' -> action_sequence containing turn then walk_steps. "
        "'where am i', 'what is my position' -> where. "
        "'show me the camera', 'look through the camera' -> view. "
        "'look around', 'scan nearby objects' -> look. "
        "'describe what you see', 'caption this scene' -> caption. "
        "'explore the area', 'scan all directions' -> explore. "
        "'go to 100 200', 'walk to x 100 y 200' -> goto. "
        "'go to the nearest store', 'walk to the closest building', 'head to the zebra crossing', 'find a trash bin' -> navigate_to_query. "
        "Return numeric values when needed. "
        "Schema rules: "
        "walk_steps => {\"action\":\"walk_steps\",\"steps\":number}. "
        "turn => {\"action\":\"turn\",\"direction\":\"left|right\",\"angle\":number}. "
        "goto => {\"action\":\"goto\",\"x\":number,\"y\":number}. "
        "navigate_to_query => {\"action\":\"navigate_to_query\",\"query\":\"target description\"}. "
        "Multi-step => {\"action_sequence\":[{\"action\":\"turn\",\"direction\":\"right\",\"angle\":90},{\"action\":\"walk_steps\",\"steps\":5}]}. "
        "help => {\"action\":\"help\"}. stop => {\"action\":\"stop\"}. unknown => {\"action\":\"unknown\",\"raw_text\":\"...\"}."
    )
    prompt = f"System:\n{system}\n\nUser:\n{text}\n\nRespond with the JSON only."
    payload = {"model": model, "prompt": prompt, "stream": False, "format": "json", "options": {"temperature": 0}}
    debug_log('ollama_parse_input', {'text': text, 'model': model, 'payload': payload})
    try:
        resp = requests.post(url, json=payload, timeout=get_ollama_timeout_sec())
        resp.raise_for_status()
        body = resp.json()
        out = body.get('response', '') if isinstance(body, dict) else ''
        if not out:
            return None
        obj = json.loads(out)
        if isinstance(obj.get('action_sequence'), list):
            sequence = []
            for item in obj['action_sequence']:
                parsed = parse_ollama_action(item, text)
                if parsed is not None:
                    sequence.append(parsed)
            if sequence:
                return ('sequence', sequence)
            return ('unknown', text)
        return parse_ollama_action(obj, text)
    except Exception as e:
        print(f'Ollama parse failed: {e}')
        return None
