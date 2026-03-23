"""Ollama-driven prompt agent runner for SimWorld.

Run a local UnrealCV server and a local Ollama server before using this script.

Usage:
  python scripts/prompt_agent.py
"""
from pathlib import Path
import time
import os
import json
import random
import requests
import math
import sys
import socket
import subprocess
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

STARTUP_LOG_PATH = REPO_ROOT / 'logs' / 'prompt_agent_startup.log'


def startup_log(message: str):
    STARTUP_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{timestamp}] {message}'
    print(line)
    with STARTUP_LOG_PATH.open('a', encoding='utf-8') as f:
        f.write(line + '\n')


import numpy as np

startup_log(f'Python executable: {sys.executable}')
startup_log(f'Working directory: {os.getcwd()}')
startup_log(f'Repo root: {REPO_ROOT}')

try:
    startup_log('Importing SimWorld modules...')
    from simworld.communicator.unrealcv import UnrealCV
    from simworld.communicator.communicator import Communicator
    from simworld.agent.humanoid import Humanoid
    from simworld.utils.vector import Vector
    from simworld.config import Config
    startup_log('SimWorld imports succeeded.')
except Exception as e:
    startup_log(f'SimWorld import failed: {type(e).__name__}: {e}')
    raise

# Vision model cache
_vision_pipeline = None
_vision_model = None
_vision_processor = None
_vision_device = None
_walk_speed_cm_per_sec = 200.0
_last_survey_options = []
_last_survey_query = ''
DEFAULT_OLLAMA_TIMEOUT_SEC = 60.0
DEFAULT_SIMWORLD_EXE = r"D:\Windows\Windows\SimWorld.exe"
DEFAULT_SIMWORLD_MAP = "/Game/Maps/empty.umap"
DEFAULT_UNREALCV_PORT = 9000


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


def get_ollama_timeout_sec() -> float:
    timeout = parse_numeric(os.environ.get('OLLAMA_TIMEOUT_SEC'), DEFAULT_OLLAMA_TIMEOUT_SEC)
    if timeout is None:
        return DEFAULT_OLLAMA_TIMEOUT_SEC
    return max(1.0, float(timeout))


def load_vision_pipeline(model_name: str = None):
    """Lazy-load a BLIP captioning callable.

    Returns a callable pipeline(image, top_k=...) -> list[dict].
    """
    global _vision_pipeline, _vision_model, _vision_processor, _vision_device
    if _vision_pipeline is not None:
        return _vision_pipeline

    model_name = model_name or os.environ.get('VISION_MODEL', 'Salesforce/blip-image-captioning-base')

    try:
        import torch
        from transformers import AutoProcessor, BlipForConditionalGeneration
    except Exception as e:
        raise RuntimeError(
            "Vision import failed while loading BLIP captioning dependencies. "
            f"Python executable: {sys.executable}. "
            f"Original error: {type(e).__name__}: {e}"
        ) from e

    print(f'Loading vision model {model_name} (this may take a while)...')
    try:
        processor = AutoProcessor.from_pretrained(model_name)
        model = BlipForConditionalGeneration.from_pretrained(model_name)
        requested_device = os.environ.get('VISION_DEVICE', 'cpu').strip().lower()
        if requested_device == 'auto':
            device = 'cuda' if torch.cuda.is_available() else 'cpu'
        elif requested_device == 'cuda' and torch.cuda.is_available():
            device = 'cuda'
        else:
            device = 'cpu'
        model.to(device)
        _vision_model = model
        _vision_processor = processor
        _vision_device = device

        def _generate_captions(image, top_k=3):
            inputs = processor(images=image, return_tensors='pt')
            inputs = {key: value.to(device) for key, value in inputs.items()}
            outputs = model.generate(
                **inputs,
                num_beams=max(1, int(top_k)),
                num_return_sequences=1,
                max_new_tokens=40,
            )
            captions = processor.batch_decode(outputs, skip_special_tokens=True)
            return [{'generated_text': caption.strip()} for caption in captions if caption.strip()]

        _vision_pipeline = _generate_captions
    except Exception as e:
        raise RuntimeError(
            f'Failed to load vision model {model_name}. '
            f'Python executable: {sys.executable}. '
            f'Original error: {type(e).__name__}: {e}'
        ) from e

    return _vision_pipeline


def unload_vision_pipeline():
    global _vision_pipeline, _vision_model, _vision_processor, _vision_device
    if _vision_model is not None:
        try:
            if _vision_device == 'cuda':
                import torch
                del _vision_model
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
        except Exception:
            pass
    _vision_pipeline = None
    _vision_model = None
    _vision_processor = None
    _vision_device = None


def caption_current_view(comm: Communicator, hum: Humanoid, model_name: str = None, top_k: int = 3):
    """Capture current humanoid camera view and return captions list."""
    try:
        img = comm.get_camera_observation(hum.camera_id, 'lit', mode='direct')
        debug_log(
            'camera_observation',
            {
                'camera_id': hum.camera_id,
                'type': type(img).__name__,
                'shape': getattr(img, 'shape', None),
                'top_k': top_k,
            },
        )
    except Exception as e:
        raise RuntimeError(f'Failed to get camera image: {e}')

    try:
        from PIL import Image
        import numpy as np
    except Exception as e:
        raise RuntimeError(
            "Vision image-processing imports failed. "
            f"Python executable: {sys.executable}. "
            f"Original error: {type(e).__name__}: {e}"
        ) from e

    # convert numpy array (H,W,3) to PIL
    if isinstance(img, np.ndarray):
        pil = Image.fromarray(img.astype('uint8'))
    else:
        # try to handle raw bytes via PIL
        pil = Image.fromarray(np.array(img))

    pipeline = load_vision_pipeline(model_name)
    outputs = pipeline(pil, top_k=top_k)
    debug_log('vision_model_outputs', outputs)

    captions = []
    for o in outputs:
        # pipeline output varies by version
        text = o.get('generated_text') or o.get('caption') or o.get('text') or str(o)
        captions.append(text)
    debug_log('vision_captions', captions)
    if os.environ.get('KEEP_VISION_MODEL_LOADED', '0') != '1':
        unload_vision_pipeline()
    return captions


STEP_DURATION = 0.5  # seconds per "step" (tunable)
DEFAULT_TURN_ANGLE = 90.0
MAX_STEP_DURATION = 5.0
DEFAULT_WALK_SPEED_CM_PER_SEC = 200.0
CALIBRATION_STEP_DURATION = 0.5
NAVIGATION_SCAN_RADIUS = 4000.0
NAVIGATION_STOP_DISTANCE = 350.0
NAVIGATION_MAX_ITERS = 12
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


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def parse_numeric(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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
    poll_sec = 1.0
    deadline = time.time() + timeout_sec

    print(f'Waiting for SimWorld on {host}:{port}...')
    while time.time() < deadline:
        if is_port_open(host, port, timeout_sec=0.5):
            print('SimWorld is ready.')
            return
        time.sleep(poll_sec)

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
    selection_prefixes = (
        'go to ',
        'walk to ',
        'pick ',
        'choose ',
        '',
    )
    for direction, phrases in directional_selection_phrases:
        for prefix in selection_prefixes:
            for phrase in phrases:
                if lowered == f'{prefix}{phrase}'.strip():
                    return ('goto_directional_option', direction)

    semantic_prefixes = (
        'go to the ',
        'go to ',
        'walk to the ',
        'walk to ',
        'head to the ',
        'head to ',
        'find the ',
        'find a ',
        'find an ',
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


def ollama_parse_command(text: str, model: str):
    """Call local Ollama HTTP API to parse user text into a JSON command.

    Expects Ollama server running via `ollama serve` on port 11434.
    The model should be pulled with `ollama pull <model>` and passed via
    the `OLLAMA_MODEL` env var or parameter.
    """
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
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0
        }
    }
    debug_log('ollama_parse_input', {'text': text, 'model': model, 'prompt': prompt, 'payload': payload})
    try:
        resp = requests.post(url, json=payload, timeout=get_ollama_timeout_sec())
        resp.raise_for_status()
        body = resp.json()
        debug_log('ollama_parse_response_body', body)
        out = body.get('response', '') if isinstance(body, dict) else ''
        if not out:
            return None
        obj = json.loads(out)
        debug_log('ollama_parse_response_json', obj)
        if isinstance(obj.get('action_sequence'), list):
            sequence = []
            for item in obj['action_sequence']:
                parsed = parse_ollama_action(item, text)
                if parsed is not None:
                    sequence.append(parsed)
            debug_log('ollama_parse_sequence', sequence)
            if sequence:
                return ('sequence', sequence)
            return ('unknown', text)

        # convert to our tuple format
        parsed = parse_ollama_action(obj, text)
        debug_log('ollama_parse_result', parsed)
        return parsed
    except Exception as e:
        print(f'Ollama parse failed: {e}')
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
        query = str(obj.get('query', raw_text)).strip()
        return ('navigate_to_query', query)
    if action == 'goto_option':
        option_index = parse_numeric(obj.get('option'), None)
        if option_index is not None:
            return ('goto_option', int(option_index))
        return ('unknown', raw_text)
    if action == 'survey':
        query = str(obj.get('query', raw_text)).strip()
        return ('survey', query)
    if action == 'help':
        return ('help',)
    if action == 'quit':
        return ('quit',)
    return ('unknown', obj.get('raw_text', raw_text))


def check_vision_dependencies():
    missing = []
    modules = (
        ('transformers', 'transformers'),
        ('PIL', 'pillow'),
        ('torch', 'torch'),
        ('numpy', 'numpy'),
    )
    for module_name, package_name in modules:
        try:
            __import__(module_name)
        except Exception:
            missing.append(package_name)
    return missing


def print_runtime_status(use_ollama: bool, ollama_model: str):
    print(f'Python executable: {sys.executable}')
    print(f'Ollama enabled: {use_ollama}')
    print(f'Ollama model: {ollama_model}')
    print(f'Estimated walk speed: {get_walk_speed_cm_per_sec():.1f} cm/s')
    print(f'Vision device: {os.environ.get("VISION_DEVICE", "cpu")}')
    print(f'Keep vision model loaded: {os.environ.get("KEEP_VISION_MODEL_LOADED", "0") == "1"}')
    missing = check_vision_dependencies()
    if missing:
        print('Vision captioning unavailable. Missing packages:', ', '.join(missing))
        print(f'Install into this Python with: "{sys.executable}" -m pip install {" ".join(missing)}')
    else:
        print('Vision captioning dependencies are installed.')


def load_asset_maps():
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))
    desc_path = os.path.join(base, 'description_map.json')
    assets_path = os.path.join(base, 'ue_assets.json')
    desc = {}
    assets = {}
    try:
        with open(desc_path, 'r', encoding='utf-8') as f:
            desc = json.load(f)
    except Exception:
        pass
    try:
        with open(assets_path, 'r', encoding='utf-8') as f:
            assets = json.load(f)
    except Exception:
        pass
    return desc, assets


def parse_rgb_color(color_str: str):
    try:
        stripped = color_str.strip().strip('()')
        parts = {}
        for chunk in stripped.split(','):
            key, value = chunk.split('=', 1)
            parts[key.strip().upper()] = int(value.strip())
        return (parts['R'], parts['G'], parts['B'])
    except Exception:
        return None


def get_asset_category_maps():
    desc_map, assets_map = load_asset_maps()
    category_colors = {}
    class_to_category = {}
    for color_name, color_value in assets_map.get('colors', {}).items():
        rgb = parse_rgb_color(color_value)
        if rgb is not None:
            category_colors[rgb] = color_name.lower()
    for key, value in assets_map.items():
        if key == 'colors':
            continue
        category = str(value.get('color', '')).strip().lower()
        if category:
            class_to_category[key.lower()] = category
    return desc_map, assets_map, category_colors, class_to_category


def infer_category_for_object(obj_name: str, assets_map: dict, class_to_category: dict) -> str:
    lowered = str(obj_name).lower()
    for asset_key, category in class_to_category.items():
        if asset_key in lowered:
            return category
    if 'lamp' in lowered or 'lightpole' in lowered or 'streetlight' in lowered or 'street_light' in lowered:
        return 'lamp_post'
    if 'building' in lowered or 'bp_building' in lowered:
        return 'building'
    if 'tree' in lowered or 'vegetation' in lowered:
        return 'vegetation'
    if 'trash' in lowered or 'rabbish' in lowered or 'bin' in lowered:
        return 'trash'
    if 'store' in lowered or 'shop' in lowered:
        return 'building'
    return ''


def look_around(comm: Communicator, ucv: UnrealCV, hum: Humanoid, radius: float = 2000.0, save_path: str = None):
    """Query UE for nearby objects and map to descriptions using repo maps.

    Returns a list of (name, short_label, description, distance) tuples and optionally saves JSON.
    """
    desc_map, assets_map, _, class_to_category = get_asset_category_maps()

    # current humanoid position
    try:
        name = comm.get_humanoid_name(hum.id)
        hum_loc = ucv.get_location(name)
        hum_pos = Vector(hum_loc[0], hum_loc[1])
    except Exception:
        hum_pos = None

    objects = comm.unrealcv.get_objects()
    debug_log('look_around_world_state', {'object_count': len(objects), 'radius': radius, 'humanoid_id': hum.id})
    results = []

    # prepare keys for matching
    desc_keys = list(desc_map.keys())
    asset_keys = [k for k in assets_map.keys() if k != 'colors']

    for obj in objects:
        try:
            obj_name = str(obj)
        except Exception:
            continue

        # distance check
        pos = None
        try:
            loc = ucv.get_location(obj_name)
            pos = Vector(loc[0], loc[1])
            distance = hum_pos.distance(pos) if hum_pos else None
            if distance is not None and distance > radius:
                continue
        except Exception:
            distance = None

        # match by substring to asset or description keys
        short_label = None
        description = None
        for key in desc_keys:
            if key.lower() in obj_name.lower():
                short_label = key
                description = desc_map.get(key)
                break
        if short_label is None:
            for key in asset_keys:
                if key.lower() in obj_name.lower():
                    short_label = key
                    # try to get a short human label from asset key
                    description = assets_map.get(key, {}).get('asset_path', key)
                    break

        # fallback: simple heuristics
        if short_label is None:
            if 'tree' in obj_name.lower() or 'bp_tree' in obj_name.lower():
                short_label = 'tree'
                description = 'Tree/vegetation'
            elif 'building' in obj_name.lower() or 'bp_building' in obj_name.lower():
                short_label = 'building'
                description = 'Building'

        category = infer_category_for_object(obj_name, assets_map, class_to_category)
        world_x = float(pos.x) if 'pos' in locals() else None
        world_y = float(pos.y) if 'pos' in locals() else None
        results.append({
            'name': obj_name,
            'label': short_label or 'unknown',
            'description': description or '',
            'distance': distance,
            'category': category,
            'world_x': world_x,
            'world_y': world_y,
        })

    # sort by distance if available
    results.sort(key=lambda x: x['distance'] if x['distance'] is not None else 1e9)
    debug_log('look_around_results', results[:50])

    # print summary
    display_results = get_displayable_look_results(results)
    hidden_count = max(0, len(results) - len(display_results))
    print('Look results:')
    for r in display_results[:50]:
        dstr = f" ({r['distance']:.1f})" if r['distance'] is not None else ''
        print(f" - {r['name']}: {r['label']}{dstr} -> {r['description']}")
    if hidden_count > 0:
        print(f' - [{hidden_count} simulator/internal objects hidden]')

    if save_path:
        try:
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump({'timestamp': time.time(), 'humanoid': hum.id, 'results': results}, f, indent=2)
            print('Saved look results to', save_path)
        except Exception as e:
            print('Failed saving look results:', e)

    return results


def is_navigable_candidate(item: dict) -> bool:
    name = str(item.get('name', '')).lower()
    label = str(item.get('label', '')).lower()
    description = str(item.get('description', '')).strip().lower()

    if any(pattern in name for pattern in IGNORED_OBJECT_PATTERNS):
        return False
    if label == 'unknown' and not description:
        return False
    return True


def get_navigation_candidates(results):
    return [item for item in results if is_navigable_candidate(item)]


def normalize_query_token(token: str) -> str:
    cleaned = ''.join(ch for ch in str(token).lower() if ch.isalnum())
    if cleaned.endswith('ies') and len(cleaned) > 3:
        return cleaned[:-3] + 'y'
    if cleaned.endswith('es') and len(cleaned) > 3:
        return cleaned[:-2]
    if cleaned.endswith('s') and len(cleaned) > 3:
        return cleaned[:-1]
    return cleaned


def extract_query_terms(query: str):
    stop_words = {
        'go', 'to', 'the', 'a', 'an', 'nearest', 'closest', 'find', 'walk', 'head',
        'toward', 'towards', 'near', 'me', 'please', 'option', 'show', 'on', 'of',
        'my', 'that', 'this',
    }
    tokens = str(query).strip().lower().replace('_', ' ').replace('-', ' ').split()
    terms = []
    for token in tokens:
        normalized = normalize_query_token(token)
        if normalized and normalized not in stop_words:
            terms.append(normalized)
    return terms


def expand_query_terms(terms):
    synonym_groups = {
        'building': {'building', 'office', 'store', 'shop', 'house', 'tower', 'kiosk', 'commercial', 'residential'},
        'office': {'office', 'building', 'commercial', 'tower'},
        'store': {'store', 'shop', 'market', 'mart', 'kiosk', 'building'},
        'shop': {'shop', 'store', 'market', 'mart', 'kiosk', 'building'},
        'tree': {'tree', 'vegetation'},
        'lamp': {'lamp', 'lamppost', 'streetlight', 'light', 'pole', 'lightpost'},
        'pole': {'pole', 'lamp', 'lamppost', 'lightpost', 'streetlight'},
        'crossing': {'crossing', 'crosswalk', 'zebra'},
        'zebra': {'zebra', 'crossing', 'crosswalk'},
        'bin': {'bin', 'trash', 'garbage', 'rubbish', 'can'},
        'trash': {'trash', 'bin', 'garbage', 'rubbish', 'can'},
        'bench': {'bench', 'seat'},
        'sign': {'sign', 'signpost'},
    }
    expanded = set()
    for term in terms:
        expanded.update(synonym_groups.get(term, {term}))
    return expanded or set(terms)


def candidate_text_blob(item: dict) -> str:
    return ' '.join(
        [
            str(item.get('name', '')),
            str(item.get('label', '')),
            str(item.get('description', '')),
            str(item.get('category', '')),
        ]
    ).lower().replace('_', ' ').replace('-', ' ')


def filter_candidates_for_query(candidates, query: str):
    terms = extract_query_terms(query)
    if not terms:
        return list(candidates)

    expanded_terms = expand_query_terms(terms)
    matched = []
    for item in candidates:
        blob = candidate_text_blob(item)
        score = 0
        for term in expanded_terms:
            if term and term in blob:
                score += 1
        if score > 0:
            enriched = dict(item)
            enriched['query_relevance_score'] = score
            matched.append(enriched)

    matched.sort(key=lambda item: (-item.get('query_relevance_score', 0), item.get('distance', 1e9)))
    debug_log(
        'filter_candidates_for_query',
        {'query': query, 'terms': terms, 'expanded_terms': sorted(expanded_terms), 'input_count': len(candidates), 'output_count': len(matched)},
    )
    return matched


def get_displayable_look_results(results):
    displayable = [item for item in results if is_navigable_candidate(item)]
    if displayable:
        return displayable
    return results


def summarize_look_results(results, limit: int = 8) -> str:
    if not results:
        return 'No nearby objects found.'
    lines = []
    for item in results[:limit]:
        desc = item['description'] or item['label']
        distance = item.get('distance')
        distance_text = f'{distance:.0f} cm' if isinstance(distance, (int, float)) else 'unknown distance'
        lines.append(f"{item['name']} | label={item['label']} | description={desc} | distance={distance_text}")
    return '\n'.join(lines)


def get_visible_mask_categories(comm: Communicator, hum: Humanoid):
    try:
        mask = comm.get_camera_observation(hum.camera_id, 'object_mask', mode='direct')
    except Exception as e:
        print(f'Object-mask capture failed: {e}')
        return {}

    if mask is None or not hasattr(mask, 'shape'):
        return {}

    if len(mask.shape) == 2:
        mask_rgb = np.stack([mask, mask, mask], axis=-1)
    else:
        mask_rgb = np.asarray(mask)[..., :3]

    _, _, category_colors, _ = get_asset_category_maps()
    flat = mask_rgb.reshape(-1, 3)
    unique_colors, counts = np.unique(flat, axis=0, return_counts=True)
    visible = {}
    for color, count in zip(unique_colors, counts):
        if int(count) < MASK_MIN_PIXELS:
            continue
        key = tuple(int(channel) for channel in color.tolist())
        category = category_colors.get(key)
        if category:
            visible[category] = visible.get(category, 0) + int(count)
    return visible


def relative_angle_to_target(current_pos: Vector, yaw: float, target_pos: Vector) -> float:
    dx = target_pos.x - current_pos.x
    dy = target_pos.y - current_pos.y
    target_heading = math.degrees(math.atan2(dy, dx))
    return normalize_angle_deg(target_heading - yaw)


def bucket_screen_position(relative_angle: float) -> str:
    if relative_angle < -18.0:
        return 'left'
    if relative_angle > 18.0:
        return 'right'
    return 'center'


def bucket_distance(distance: float) -> str:
    if distance < 250:
        return 'near'
    if distance < 700:
        return 'mid'
    return 'far'


def bucket_apparent_size(item: dict) -> str:
    description = str(item.get('description', '')).lower()
    if 'high ' in description or 'tower' in description or 'tall' in description:
        return 'tall'
    if 'low ' in description or 'small' in description or 'short' in description:
        return 'short'
    distance = item.get('distance')
    if isinstance(distance, (int, float)) and distance < 250:
        return 'large'
    return 'medium'


def describe_candidate_phrase(item: dict) -> str:
    size_bucket = item.get('size_bucket', 'medium')
    screen_bucket = item.get('screen_bucket', 'center')
    category = item.get('category') or item.get('label') or 'object'
    category = category.replace('_', ' ')
    if category == 'vegetation':
        category = 'tree'
    if category == 'building' and 'store' in str(item.get('description', '')).lower():
        category = 'store building'
    return f'{size_bucket} {category} on the {screen_bucket}'


def build_visible_candidates(results, current_pos: Vector, yaw: float, visible_categories: dict):
    candidates = []
    visible_category_names = set(visible_categories.keys())
    for item in results:
        category = item.get('category', '') or ''
        distance = item.get('distance')
        if not isinstance(distance, (int, float)):
            continue
        try:
            target_pos = Vector(item['world_x'], item['world_y'])
        except Exception:
            continue
        rel_angle = relative_angle_to_target(current_pos, yaw, target_pos)
        if abs(rel_angle) > VISIBLE_FOV_DEG / 2.0:
            continue
        if visible_category_names and category and category not in visible_category_names:
            continue
        enriched = dict(item)
        enriched['relative_angle'] = rel_angle
        enriched['screen_bucket'] = bucket_screen_position(rel_angle)
        enriched['distance_bucket'] = bucket_distance(distance)
        enriched['size_bucket'] = bucket_apparent_size(item)
        enriched['visible_score'] = max(0.0, 1.0 - abs(rel_angle) / (VISIBLE_FOV_DEG / 2.0))
        enriched['screen_description'] = describe_candidate_phrase(enriched)
        if category:
            enriched['mask_pixels'] = visible_categories.get(category, 0)
        candidates.append(enriched)
    candidates.sort(key=lambda x: (x.get('distance', 1e9), abs(x.get('relative_angle', 999.0))))
    return candidates


def dedupe_ranked_candidates(candidates, limit: int = MAX_SURVEY_OPTIONS):
    deduped = []
    seen_names = set()
    seen_phrases = set()
    for item in candidates:
        name = item.get('name')
        phrase = item.get('screen_description')
        if not name or name in seen_names:
            continue
        if phrase and phrase in seen_phrases and len(deduped) >= 2:
            continue
        deduped.append(item)
        seen_names.add(name)
        if phrase:
            seen_phrases.add(phrase)
        if len(deduped) >= limit:
            break
    return deduped


def summarize_candidate_for_user(item: dict, index: int) -> str:
    description = item.get('screen_description') or item.get('description') or item.get('label') or 'unknown'
    distance = item.get('distance')
    distance_text = f'{distance:.0f} cm' if isinstance(distance, (int, float)) else 'unknown distance'
    reason = item.get('reason', '')
    summary = f'{index}. {item["name"]} | {description} | {distance_text}'
    if reason:
        summary += f' | {reason}'
    return summary


def rank_navigation_candidates(model: str, query: str, candidates, limit: int = 5):
    if not candidates:
        return []
    url = os.environ.get('OLLAMA_API_URL', 'http://localhost:11434/api/generate')
    system = (
        "You rank nearby world objects for a humanoid in SimWorld. "
        "Reply with exactly one JSON object and no markdown. "
        "Return {\"selected_names\":[\"exact name 1\",\"exact name 2\"],\"reason\":\"short reason\"}. "
        "Prefer objects that best match the user's wording and spatial cues like left, right, taller, shorter, nearest. "
        "Use only exact names from the provided list."
    )
    prompt = (
        f"System:\n{system}\n\n"
        f"User query:\n{query}\n\n"
        f"Nearby objects:\n{summarize_look_results(candidates, limit=18)}\n\n"
        f"Return up to {limit} exact object names in ranked order."
    )
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0
        }
    }
    debug_log(
        'rank_navigation_candidates_input',
        {'query': query, 'model': model, 'limit': limit, 'candidate_count': len(candidates), 'prompt': prompt},
    )
    try:
        resp = requests.post(url, json=payload, timeout=get_ollama_timeout_sec())
        resp.raise_for_status()
        body = resp.json()
        debug_log('rank_navigation_candidates_response_body', body)
        out = body.get('response', '') if isinstance(body, dict) else ''
        if not out:
            return []
        obj = json.loads(out)
        debug_log('rank_navigation_candidates_response_json', obj)
        selected_names = obj.get('selected_names') or []
        reason = str(obj.get('reason', '')).strip()
        ranked = []
        seen = set()
        for selected_name in selected_names:
            exact_name = str(selected_name).strip()
            if not exact_name or exact_name in seen:
                continue
            for candidate in candidates:
                if candidate['name'] == exact_name:
                    enriched = dict(candidate)
                    if reason:
                        enriched['reason'] = reason
                    ranked.append(enriched)
                    seen.add(exact_name)
                    break
            if len(ranked) >= limit:
                break
        return ranked
    except Exception as e:
        print(f'Candidate ranking failed: {e}')
        return []


def rank_hybrid_candidates(model: str, query: str, candidates, limit: int = MAX_SURVEY_OPTIONS):
    if not candidates:
        return []
    url = os.environ.get('OLLAMA_API_URL', 'http://localhost:11434/api/generate')
    lines = []
    for item in candidates[:18]:
        distance = item.get('distance')
        distance_text = f'{distance:.0f} cm' if isinstance(distance, (int, float)) else 'unknown'
        rel_angle = item.get('relative_angle')
        angle_text = f'{rel_angle:.1f} deg' if isinstance(rel_angle, (int, float)) else 'unknown'
        lines.append(
            f'{item["name"]} | phrase={item.get("screen_description", "")} | '
            f'description={item.get("description", "")} | category={item.get("category", "")} | '
            f'distance={distance_text} | rel_angle={angle_text}'
        )
    system = (
        "You rank visible hybrid navigation candidates for a humanoid in SimWorld. "
        "Reply with exactly one JSON object and no markdown. "
        "Return {\"selected_names\":[\"exact object name\"],\"reason\":\"short reason\"}. "
        "Prefer candidates that best match spatial language like left, right, taller, shorter, near, far."
    )
    prompt = (
        f"System:\n{system}\n\n"
        f"User query:\n{query}\n\n"
        "Visible candidates:\n"
        f"{chr(10).join(lines)}\n\n"
        f"Return up to {limit} exact object names in ranked order."
    )
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0
        }
    }
    debug_log(
        'rank_hybrid_candidates_input',
        {'query': query, 'model': model, 'limit': limit, 'candidate_count': len(candidates), 'prompt': prompt},
    )
    try:
        resp = requests.post(url, json=payload, timeout=get_ollama_timeout_sec())
        resp.raise_for_status()
        body = resp.json()
        debug_log('rank_hybrid_candidates_response_body', body)
        out = body.get('response', '') if isinstance(body, dict) else ''
        if not out:
            return []
        obj = json.loads(out)
        debug_log('rank_hybrid_candidates_response_json', obj)
        selected_names = obj.get('selected_names') or []
        reason = str(obj.get('reason', '')).strip()
        ranked = []
        seen = set()
        for selected_name in selected_names:
            exact_name = str(selected_name).strip()
            if not exact_name or exact_name in seen:
                continue
            for candidate in candidates:
                if candidate['name'] == exact_name:
                    enriched = dict(candidate)
                    if reason:
                        enriched['reason'] = reason
                    ranked.append(enriched)
                    seen.add(exact_name)
                    break
            if len(ranked) >= limit:
                break
        return ranked
    except Exception as e:
        print(f'Hybrid candidate ranking failed: {e}')
        return []


def store_survey_options(query: str, options):
    global _last_survey_options, _last_survey_query
    _last_survey_query = query
    _last_survey_options = list(options)


def print_survey_options():
    if not _last_survey_options:
        print('No saved options yet. Try "survey building" or "show options" after a semantic request.')
        return
    query_text = f' for "{_last_survey_query}"' if _last_survey_query else ''
    print(f'Option summary{query_text}:')
    for index, item in enumerate(_last_survey_options, start=1):
        print(summarize_candidate_for_user(item, index))


def find_directional_option(direction: str):
    direction = str(direction).strip().lower()
    if direction not in ('left', 'right'):
        return None
    matches = []
    for index, item in enumerate(_last_survey_options, start=1):
        screen_bucket = str(item.get('screen_bucket', '')).strip().lower()
        description = str(item.get('screen_description', '')).strip().lower()
        if screen_bucket == direction or f'on the {direction}' in description:
            matches.append((index, item))
    if len(matches) == 1:
        return matches[0]
    return None


def navigate_to_directional_option(comm: Communicator, ucv: UnrealCV, hum: Humanoid, direction: str):
    match = find_directional_option(direction)
    if match is None:
        print(
            f'Could not uniquely identify the {direction} option from the current candidates. '
            'Use "show options" and then "go to option N".'
        )
        return
    option_index, item = match
    print(f'Selected the {direction} option: {item["name"]}')
    navigate_to_option(comm, ucv, hum, option_index)


def collect_hybrid_candidates_for_pose(comm: Communicator, ucv: UnrealCV, hum: Humanoid):
    try:
        current_pos, yaw = get_humanoid_pose(comm, ucv, hum)
    except Exception as e:
        print(f'Failed to read humanoid pose for hybrid survey: {e}')
        return []
    visible_categories = get_visible_mask_categories(comm, hum)
    debug_log('visible_mask_categories', visible_categories)
    if visible_categories:
        visible_text = ', '.join(f'{key}:{value}' for key, value in sorted(visible_categories.items()))
        print(f'Visible mask categories: {visible_text}')
    results = look_around(comm, ucv, hum, radius=NAVIGATION_SCAN_RADIUS)
    candidates = get_navigation_candidates(results)
    visible_candidates = build_visible_candidates(candidates, current_pos, yaw, visible_categories)
    debug_log(
        'hybrid_pose_candidates',
        {
            'current_pos': current_pos,
            'yaw': yaw,
            'candidate_count': len(visible_candidates),
            'candidates': visible_candidates,
        },
    )
    return visible_candidates


def survey_semantic_candidates_hybrid(comm: Communicator, ucv: UnrealCV, hum: Humanoid, model: str, query: str, limit: int = MAX_SURVEY_OPTIONS):
    print(f'Hybrid survey for "{query}"')
    collected = []
    sweep_turn_deg = 360.0 / max(1, len(SURVEY_SWEEP_ANGLES))
    for sweep_index, sweep_yaw in enumerate(SURVEY_SWEEP_ANGLES):
        if sweep_index > 0:
            print(
                f'Hybrid survey: rotating right by {sweep_turn_deg:.0f} degrees '
                f'for sweep {sweep_index + 1}/{len(SURVEY_SWEEP_ANGLES)}'
            )
            comm.humanoid_rotate(hum.id, sweep_turn_deg, 'right')
            time.sleep(0.6)
        pose_candidates = collect_hybrid_candidates_for_pose(comm, ucv, hum)
        if not pose_candidates:
            continue
        ranked_pose = rank_hybrid_candidates(model, query, pose_candidates, limit=limit)
        if not ranked_pose:
            ranked_pose = pose_candidates[:limit]
        for item in ranked_pose:
            enriched = dict(item)
            enriched['sweep_yaw'] = sweep_yaw
            collected.append(enriched)
    if len(SURVEY_SWEEP_ANGLES) > 1:
        comm.humanoid_rotate(hum.id, sweep_turn_deg, 'right')
        time.sleep(0.2)
    if not collected:
        print('Hybrid survey could not find any visible semantic candidates.')
        store_survey_options(query, [])
        return []
    collected = filter_candidates_for_query(collected, query)
    if not collected:
        print(f'Hybrid survey found no candidates relevant to "{query}".')
        store_survey_options(query, [])
        return []
    ranked = rank_hybrid_candidates(model, query, collected, limit=limit)
    if not ranked:
        ranked = collected
    ranked = dedupe_ranked_candidates(ranked, limit=limit)
    store_survey_options(query, ranked)
    print_survey_options()
    return list(_last_survey_options)


def survey_semantic_candidates(comm: Communicator, ucv: UnrealCV, hum: Humanoid, model: str, query: str, limit: int = 5):
    hybrid_ranked = survey_semantic_candidates_hybrid(comm, ucv, hum, model, query, limit=min(limit, MAX_SURVEY_OPTIONS))
    if hybrid_ranked:
        return hybrid_ranked

    print(f'Falling back to world-object survey for "{query}"')
    results = look_around(comm, ucv, hum, radius=NAVIGATION_SCAN_RADIUS)
    candidates = get_navigation_candidates(results)
    candidates = filter_candidates_for_query(candidates, query)
    if not candidates:
        print(f'No semantic world objects relevant to "{query}" were found nearby.')
        store_survey_options(query, [])
        return []

    ranked = rank_navigation_candidates(model, query, candidates, limit=limit)
    if not ranked:
        target = choose_navigation_target(model, query, candidates)
        ranked = [target] if target is not None else []

    if not ranked:
        print('Could not find any plausible candidates for that request.')
        store_survey_options(query, [])
        return []

    ranked = dedupe_ranked_candidates(ranked, limit=limit)
    store_survey_options(query, ranked[:limit])
    print_survey_options()
    return list(_last_survey_options)


def navigate_to_option(comm: Communicator, ucv: UnrealCV, hum: Humanoid, option_index: int):
    if option_index < 1 or option_index > len(_last_survey_options):
        print(f'Option {option_index} is out of range. Use "show options" to inspect available choices.')
        return
    target = _last_survey_options[option_index - 1]
    print(f'Navigating to option {option_index}: {target["name"]} ({target.get("label", "unknown")})')
    try:
        loc = ucv.get_location(target['name'])
        target_pos = Vector(loc[0], loc[1])
    except Exception as e:
        print(f'Failed to read selected option location: {e}')
        return
    navigate_to_coordinates(comm, ucv, hum, target_pos)


def choose_navigation_target(model: str, query: str, candidates) -> Optional[dict]:
    if not candidates:
        return None

    url = os.environ.get('OLLAMA_API_URL', 'http://localhost:11434/api/generate')
    system = (
        "You choose the best nearby navigation target for a humanoid in SimWorld. "
        "Reply with exactly one JSON object and no markdown. "
        "Given a user query and a list of nearby objects, select the single best candidate. "
        "Prefer semantically matching objects and the nearest reasonable option. "
        "Return {\"selected_name\":\"exact object name\",\"reason\":\"short reason\"}. "
        "If nothing fits, return {\"selected_name\":\"\",\"reason\":\"no good match\"}."
    )
    prompt = (
        f"System:\n{system}\n\n"
        f"User query:\n{query}\n\n"
        f"Nearby objects:\n{summarize_look_results(candidates, limit=12)}\n\n"
        "Respond with JSON only."
    )
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0
        }
    }
    debug_log(
        'choose_navigation_target_input',
        {'query': query, 'model': model, 'candidate_count': len(candidates), 'prompt': prompt},
    )
    try:
        resp = requests.post(url, json=payload, timeout=get_ollama_timeout_sec())
        resp.raise_for_status()
        body = resp.json()
        debug_log('choose_navigation_target_response_body', body)
        out = body.get('response', '') if isinstance(body, dict) else ''
        if not out:
            return None
        obj = json.loads(out)
        debug_log('choose_navigation_target_response_json', obj)
        selected_name = str(obj.get('selected_name', '')).strip()
        if not selected_name:
            return None
        for candidate in candidates:
            if candidate['name'] == selected_name:
                candidate = dict(candidate)
                candidate['reason'] = str(obj.get('reason', '')).strip()
                return candidate
        return None
    except Exception as e:
        print(f'Target selection failed: {e}')
        return None


def suggest_walk_steps(distance_cm: float) -> float:
    if distance_cm > 500:
        return 5.0
    if distance_cm > 300:
        return 4.0
    if distance_cm > 180:
        return 3.0
    if distance_cm > 90:
        return 2.0
    return 1.0


def angle_between(from_vec: Vector, to_vec: Vector):
    # compute signed yaw (degrees) to turn from from_vec to to_vec
    dot = from_vec.dot(to_vec)
    cross = from_vec.cross(to_vec)
    dot = max(min(dot, 1.0), -1.0)
    angle = math.degrees(math.acos(dot))
    direction = 'left' if cross < 0 else 'right'
    return direction, angle


def normalize_angle_deg(angle: float) -> float:
    return ((angle + 180.0) % 360.0) - 180.0


def compute_signed_angle_error(current_pos: Vector, yaw: float, target_pos: Vector) -> float:
    dx = target_pos.x - current_pos.x
    dy = target_pos.y - current_pos.y
    target_heading = math.degrees(math.atan2(dy, dx))
    return normalize_angle_deg(target_heading - yaw)


def choose_deterministic_navigation_step(current_pos: Vector, yaw: float, target_pos: Vector):
    distance = current_pos.distance(target_pos)
    angle_error = compute_signed_angle_error(current_pos, yaw, target_pos)
    if abs(angle_error) > GOTO_TURN_DEADBAND_DEG:
        direction = 'right' if angle_error > 0 else 'left'
        angle = clamp(abs(angle_error) * 0.7, 5.0, GOTO_MAX_TURN_DEG)
        return ('turn', direction, angle), angle_error

    steps = suggest_walk_steps(distance)
    if distance < 120:
        steps = min(steps, 2.0)
    return ('walk_steps', steps), angle_error


def get_humanoid_pose(comm: Communicator, ucv: UnrealCV, hum: Humanoid):
    try:
        info = comm.get_position_and_direction(humanoid_ids=[hum.id])
        pos_dir = info.get(('humanoid', hum.id))
        if pos_dir:
            pos, yaw = pos_dir
            return pos, float(yaw)
    except Exception:
        pass

    name = comm.get_humanoid_name(hum.id)
    loc = ucv.get_location(name)
    ori = ucv.get_orientation(name)
    pos = Vector(loc[0], loc[1])
    yaw = float(ori[1]) if len(ori) > 1 else 0.0
    return pos, yaw


def get_walk_speed_cm_per_sec():
    return _walk_speed_cm_per_sec


def duration_for_steps(steps: float) -> float:
    distance_cm = max(0.0, float(steps)) * CALIBRATION_STEP_DURATION * get_walk_speed_cm_per_sec()
    speed = max(1.0, get_walk_speed_cm_per_sec())
    return clamp(distance_cm / speed, 0.1, MAX_STEP_DURATION)


def duration_for_distance_cm(distance_cm: float, max_duration: float = MAX_STEP_DURATION) -> float:
    speed = max(1.0, get_walk_speed_cm_per_sec())
    return clamp(max(0.0, float(distance_cm)) / speed, 0.1, max_duration)


def compute_goto_iteration_budget(initial_remaining_cm: float) -> int:
    extra_iters = int(math.ceil(max(0.0, float(initial_remaining_cm)) / GOTO_ITER_DISTANCE_CM))
    return max(GOTO_MAX_ITERS, extra_iters)


def calibrate_walk_speed(comm: Communicator, ucv: UnrealCV, hum: Humanoid):
    global _walk_speed_cm_per_sec
    if os.environ.get('CALIBRATE_WALK_SPEED', '1') == '0':
        print(f'Walk calibration skipped. Using default speed {_walk_speed_cm_per_sec:.1f} cm/s')
        return

    try:
        start_pos, _ = get_humanoid_pose(comm, ucv, hum)
        print(f'Calibrating walk speed with a {CALIBRATION_STEP_DURATION:.2f}s forward step...')
        comm.humanoid_step_forward(hum.id, CALIBRATION_STEP_DURATION)
        end_pos, _ = get_humanoid_pose(comm, ucv, hum)
        distance = start_pos.distance(end_pos)
        if distance > 5.0:
            _walk_speed_cm_per_sec = distance / CALIBRATION_STEP_DURATION
            print(f'Calibrated walk speed: {_walk_speed_cm_per_sec:.1f} cm/s over {distance:.1f} cm')
        else:
            _walk_speed_cm_per_sec = DEFAULT_WALK_SPEED_CM_PER_SEC
            print(
                f'Calibration movement was too small ({distance:.1f} cm). '
                f'Using default speed {_walk_speed_cm_per_sec:.1f} cm/s'
            )
    except Exception as e:
        _walk_speed_cm_per_sec = DEFAULT_WALK_SPEED_CM_PER_SEC
        print(f'Walk calibration failed, using default speed {_walk_speed_cm_per_sec:.1f} cm/s: {e}')


def cleanup_prompt_agent_actors(comm: Communicator):
    try:
        objects = [str(obj) for obj in comm.unrealcv.get_objects()]
    except Exception as e:
        print(f'Startup cleanup skipped: {e}')
        return

    targets = []
    for obj_name in objects:
        lowered = obj_name.lower()
        if lowered.startswith('gen_bp_humanoid_') or lowered == 'gen_bp_uemanager':
            targets.append(obj_name)

    if not targets:
        print('No previous humanoids or prompt-agent manager found.')
        return

    print(f'Cleaning {len(targets)} previously spawned humanoid/helper actors...')
    for obj_name in targets:
        try:
            comm.unrealcv.destroy(obj_name)
        except Exception as e:
            print(f'Could not destroy {obj_name}: {e}')

    try:
        comm.unrealcv.clean_garbage()
    except Exception:
        pass


def navigate_to_target_position(comm: Communicator, hum: Humanoid, current_pos: Vector, yaw: float, target_pos: Vector):
    to_target = Vector(target_pos.x - current_pos.x, target_pos.y - current_pos.y)
    distance = to_target.length()
    if distance <= 0:
        return 0.0
    dir_vec = Vector(1, 0)
    try:
        dir_vec = Vector(math.cos(math.radians(yaw)), math.sin(math.radians(yaw)))
    except Exception:
        pass
    turn_dir, angle = angle_between(dir_vec, to_target.normalize())
    print(f'Navigating: turning {turn_dir} by {angle:.1f} degrees')
    comm.humanoid_rotate(hum.id, angle, turn_dir)
    duration = clamp(min(distance / max(1.0, get_walk_speed_cm_per_sec()), NAVIGATION_STEP_LIMIT), 0.2, MAX_STEP_DURATION)
    print(f'Navigating: walking toward target for {duration:.2f}s')
    comm.humanoid_step_forward(hum.id, duration)
    return distance


def recover_from_stuck(comm: Communicator, hum: Humanoid, attempt: int):
    recovery_angle = 25.0 if attempt % 2 == 1 else 45.0
    recovery_dir = 'right' if attempt % 2 == 1 else 'left'
    print(f'Navigation: detected no progress, trying recovery turn {recovery_dir} {recovery_angle:.1f} degrees')
    comm.humanoid_rotate(hum.id, recovery_angle, recovery_dir)
    print('Navigation: trying a short recovery walk')
    comm.humanoid_step_forward(hum.id, 0.5)


def execute_final_approach(comm: Communicator, ucv: UnrealCV, hum: Humanoid, target: Vector) -> bool:
    try:
        pos, yaw = get_humanoid_pose(comm, ucv, hum)
    except Exception as e:
        print(f'Navigation: final approach aborted, current position unknown: {e}')
        return False

    remaining = pos.distance(target)
    angle_error = compute_signed_angle_error(pos, yaw, target)
    print(
        f'Navigation: final approach triggered at remaining={remaining:.1f} cm, '
        f'angle_error={angle_error:.1f} degrees'
    )

    if abs(angle_error) > 2.0:
        direction = 'right' if angle_error > 0 else 'left'
        angle = clamp(abs(angle_error), 1.0, 20.0)
        print(f'Navigation: final approach turning {direction} by {angle:.1f} degrees')
        comm.humanoid_rotate(hum.id, angle, direction)

    walk_distance_cm = min(remaining, GOTO_FINAL_APPROACH_WALK_CM)
    duration = duration_for_distance_cm(walk_distance_cm)
    print(f'Navigation: final approach walking {walk_distance_cm:.1f} cm for {duration:.2f}s')
    comm.humanoid_step_forward(hum.id, duration)

    try:
        final_pos, _ = get_humanoid_pose(comm, ucv, hum)
    except Exception as e:
        print(f'Navigation: final approach completed but could not verify final distance: {e}')
        return False

    final_remaining = final_pos.distance(target)
    print(f'Navigation: final approach remaining distance {final_remaining:.1f} cm')
    if final_remaining <= GOTO_FINAL_APPROACH_STOP_DISTANCE_CM:
        print('Navigation: final approach marked target as reached')
        return True
    return False


def navigate_to_coordinates(comm: Communicator, ucv: UnrealCV, hum: Humanoid, target: Vector):
    print(f'Navigation: moving toward coordinates ({target.x:.1f}, {target.y:.1f})')
    stuck_count = 0
    previous_pos = None
    previous_action = None
    started_at = time.time()
    max_iters = GOTO_MAX_ITERS
    iteration = 0
    while iteration < max_iters:
        iteration += 1
        try:
            pos, yaw = get_humanoid_pose(comm, ucv, hum)
        except Exception:
            print('Navigation: current position unknown, cannot continue goto')
            return

        remaining = pos.distance(target)
        if iteration == 1:
            max_iters = compute_goto_iteration_budget(remaining)
            print(f'Navigation: iteration budget set to {max_iters} steps for initial remaining distance {remaining:.1f} cm')

        elapsed = time.time() - started_at
        if elapsed > GOTO_MAX_TIME_SEC:
            print(f'Navigation: stopped after reaching time limit of {GOTO_MAX_TIME_SEC:.1f}s')
            return

        print(f'Navigation step {iteration}/{max_iters}: current={pos}, remaining={remaining:.1f} cm')
        if remaining <= GOTO_STOP_DISTANCE:
            print('Navigation: reached target coordinates')
            return
        if remaining <= GOTO_FINAL_APPROACH_TRIGGER_CM:
            if execute_final_approach(comm, ucv, hum, target):
                return

        if previous_action in ('walk_steps', 'recovery_walk') and previous_pos is not None and pos.distance(previous_pos) < STUCK_DISTANCE_EPS:
            stuck_count += 1
            print(f'Navigation: progress since last step was too small ({pos.distance(previous_pos):.1f} cm)')
        else:
            stuck_count = 0

        if stuck_count >= STUCK_MAX_COUNT:
            recover_from_stuck(comm, hum, stuck_count)
            previous_pos = pos
            previous_action = 'recovery_walk'
            continue

        next_cmd, angle_error = choose_deterministic_navigation_step(pos, yaw, target)
        print(f'Navigation controller: angle_error={angle_error:.1f} degrees, selected {next_cmd}')

        if iteration == max_iters and remaining <= GOTO_FINAL_WALK_DISTANCE_CM:
            duration = duration_for_distance_cm(remaining)
            estimated_steps = max(1.0, remaining / max(1.0, CALIBRATION_STEP_DURATION * get_walk_speed_cm_per_sec()))
            print(
                f'Navigation: final iteration fallback, forcing last walk '
                f'({remaining:.1f} cm, est {estimated_steps:.1f} step(s))'
            )
            print(f'Navigating: walking for {duration:.2f}s')
            comm.humanoid_step_forward(hum.id, duration)
            previous_action = 'walk_steps'
            previous_pos = pos
            continue

        if next_cmd[0] == 'walk_steps':
            chunk_distance_cm = max(remaining / GOTO_DISTANCE_DIVISOR, GOTO_STOP_DISTANCE)
            duration = duration_for_distance_cm(chunk_distance_cm)
            estimated_steps = max(1.0, chunk_distance_cm / max(1.0, CALIBRATION_STEP_DURATION * get_walk_speed_cm_per_sec()))
            print(
                f'Navigation: using one-fifth remaining distance '
                f'({chunk_distance_cm:.1f} cm, est {estimated_steps:.1f} step(s))'
            )
            print(f'Navigating: walking for {duration:.2f}s')
            comm.humanoid_step_forward(hum.id, duration)
            previous_action = 'walk_steps'
        elif next_cmd[0] == 'turn':
            _, direction, angle = next_cmd
            angle = clamp(float(angle), 5.0, GOTO_MAX_TURN_DEG if remaining > 150 else 90.0)
            print(f'Navigating: turning {direction} by {angle:.1f} degrees')
            comm.humanoid_rotate(hum.id, angle, direction)
            previous_action = 'turn'
        previous_pos = pos

    print(f'Navigation: stopped after max iteration budget ({max_iters}) without fully reaching target')


def navigate_to_semantic_target(comm: Communicator, ucv: UnrealCV, hum: Humanoid, model: str, query: str):
    print(f'Navigation: searching for "{query}"')
    options = survey_semantic_candidates(comm, ucv, hum, model, query)
    if not options:
        return
    top_option = options[0]
    top_distance = top_option.get('distance')
    print(f'Navigation: best current option is {top_option["name"]}')
    if len(options) > 1:
        print('Navigation: multiple plausible matches found. Use "go to option N" to pick one explicitly.')
        return
    if isinstance(top_distance, (int, float)) and top_distance <= NAVIGATION_STOP_DISTANCE:
        print('Navigation: already near the selected target area')
        return
    print('Navigation: only one strong candidate found, proceeding automatically')
    navigate_to_option(comm, ucv, hum, 1)


def print_help():
    print('Commands:')
    print(' - walk 2 steps')
    print(' - walk forward')
    print(' - turn left 90')
    print(' - where am i')
    print(' - view / show view')
    print(' - look / scan')
    print(' - caption / describe')
    print(' - explore')
    print(' - go to X Y')
    print(' - go to the nearest store')
    print(' - walk to the closest building')
    print(' - survey building')
    print(' - show options')
    print(' - go to option 2')
    print(' - go to the left tree')
    print(' - go to the right one')
    print(' - stop')
    print(' - quit')
    print('All command parsing is handled by Ollama in this script.')


def execute_command(comm: Communicator, ucv: UnrealCV, hum: Humanoid, ollama_model: str, cmd):
    debug_log('execute_command', cmd)
    if cmd[0] == 'walk_steps':
        steps = float(cmd[1])
        duration = duration_for_steps(steps)
        print(f'Walking {steps} steps -> duration {duration}s')
        comm.humanoid_step_forward(hum.id, duration)

    elif cmd[0] == 'turn':
        _, direction, angle = cmd
        angle = clamp(float(angle), 1.0, 180.0)
        print(f'Turning {direction} by {angle} degrees')
        comm.humanoid_rotate(hum.id, angle, direction)

    elif cmd[0] == 'stop':
        print('Stopping humanoid')
        comm.humanoid_stop(hum.id)

    elif cmd[0] == 'where':
        try:
            pos, yaw = get_humanoid_pose(comm, ucv, hum)
            print(f'Position={pos}, yaw={yaw}')
        except Exception as e:
            print('No position information available (error):', e)

    elif cmd[0] == 'view':
        try:
            img = comm.get_camera_observation(hum.camera_id, 'lit', mode='direct')
            comm.show_img(img)
        except Exception as e:
            print('Failed to get camera image:', e)

    elif cmd[0] == 'caption':
        try:
            captions = caption_current_view(comm, hum)
            print('Captions:')
            for i, c in enumerate(captions):
                print(f' {i+1}. {c}')
        except Exception as e:
            print('Vision caption failed:', e)

    elif cmd[0] == 'explore':
        try:
            rounds = 4
            agg = []
            for i in range(rounds):
                print(f'View {i+1}/{rounds}: capturing...')
                try:
                    captions = caption_current_view(comm, hum)
                    agg.append({'view': i, 'captions': captions})
                    for j, c in enumerate(captions):
                        print(f'  {j+1}. {c}')
                except Exception as e:
                    print('  capture failed:', e)
                comm.humanoid_rotate(hum.id, 90, 'right')
                time.sleep(0.6)
            print('Exploration summary:')
            seen = {}
            for v in agg:
                for c in v['captions']:
                    seen[c] = seen.get(c, 0) + 1
            for k, v in sorted(seen.items(), key=lambda x: -x[1]):
                print(f' - {k} (seen {v} times)')
        except Exception as e:
            print('Explore failed:', e)

    elif cmd[0] == 'look':
        try:
            look_around(comm, ucv, hum)
        except Exception as e:
            print('Look failed:', e)

    elif cmd[0] == 'goto':
        navigate_to_coordinates(comm, ucv, hum, cmd[1])

    elif cmd[0] == 'navigate_to_query':
        navigate_to_semantic_target(comm, ucv, hum, ollama_model, cmd[1])

    elif cmd[0] == 'survey':
        survey_semantic_candidates(comm, ucv, hum, ollama_model, cmd[1])

    elif cmd[0] == 'show_options':
        print_survey_options()

    elif cmd[0] == 'goto_option':
        navigate_to_option(comm, ucv, hum, int(cmd[1]))

    elif cmd[0] == 'goto_directional_option':
        navigate_to_directional_option(comm, ucv, hum, str(cmd[1]))

    elif cmd[0] == 'help':
        print_help()

    elif cmd[0] == 'unknown':
        print('Unknown command:', cmd[1])

    elif cmd[0] == 'quit':
        print('Exiting')
        return False

    return True


def main():
    launch_state = maybe_launch_simworld()
    if launch_state in ('launched', 'reused'):
        wait_for_user_world_ready()
    wait_for_simworld_server()
    print('Connecting to UnrealCV (localhost:9000)...')
    resolution_text = os.environ.get('SIMWORLD_RESOLUTION', '320x240').lower()
    try:
        width_text, height_text = resolution_text.split('x', 1)
        resolution = (int(width_text), int(height_text))
    except Exception:
        resolution = (320, 240)
    host = os.environ.get('SIMWORLD_HOST', '127.0.0.1')
    port = int(os.environ.get('SIMWORLD_PORT', str(DEFAULT_UNREALCV_PORT)))
    ucv = UnrealCV(port=port, ip=host, resolution=resolution)
    comm = Communicator(ucv)
    config_path = os.environ.get('SIMWORLD_CONFIG')
    cfg = Config(config_path) if config_path else Config()

    cleanup_prompt_agent_actors(comm)
    time.sleep(0.5)

    # UE manager is optional; disabling it keeps the scene lighter.
    if os.environ.get('USE_UE_MANAGER', '0') == '1':
        try:
            ue_manager_path = cfg.get('simworld.ue_manager_path', None)
            if ue_manager_path:
                print(f'Spawning UE manager asset: {ue_manager_path}')
                try:
                    comm.spawn_ue_manager(ue_manager_path)
                    time.sleep(0.5)
                    try:
                        comm.update_objects()
                    except Exception:
                        pass
                except Exception as e:
                    print('Failed to spawn UE manager (continuing):', e)
        except Exception:
            pass

    if os.environ.get('SIMWORLD_GENERATE_WORLD', '0') == '1':
        try:
            generate_lightweight_world(comm, cfg)
        except Exception as e:
            print('Failed to generate procedural world:', e)
            print('Tip: start SimWorld with /Game/Maps/empty.umap before enabling SIMWORLD_GENERATE_WORLD=1')

    # spawn a humanoid at origin facing +X
    hum = Humanoid(Vector(0, 0), Vector(1, 0), communicator=comm)
    print(f'Spawning humanoid id={hum.id}...')
    comm.spawn_agent(hum, name=None)
    calibrate_walk_speed(comm, ucv, hum)

    # Ollama integration is the only parser in this script.
    use_ollama = os.environ.get('USE_OLLAMA', '1') != '0'
    ollama_model = os.environ.get('OLLAMA_MODEL', 'phi3')
    print('Ready. Type commands.')
    print_help()
    print_runtime_status(use_ollama, ollama_model)
    if debug_enabled():
        print('Debug logging enabled via DEBUG_PROMPT_AGENT=1')

    if not use_ollama or not ollama_model:
        raise RuntimeError('Ollama parsing is required. Set USE_OLLAMA=1 and OLLAMA_MODEL to a local model name.')

    last_parser = None
    try:
        while True:
            try:
                text = input('> ')

                # quick status check before parsing
                if text.strip().lower() in ('mode', 'status'):
                    print(f'USE_OLLAMA={use_ollama}, OLLAMA_MODEL={ollama_model}, last_parser={last_parser}')
                    print_runtime_status(use_ollama, ollama_model)
                    continue

                local_cmd = parse_local_command(text)
                if local_cmd is not None:
                    parsed = local_cmd
                    last_parser = 'local'
                else:
                    parsed = ollama_parse_command(text, ollama_model)
                    if parsed is None:
                        print('Ollama could not parse the command. Check that "ollama serve" is running and the model is installed.')
                        last_parser = 'ollama-error'
                        continue
                    last_parser = 'ollama'
                debug_log('user_input', text)
                debug_log('selected_parser', last_parser)
                debug_log('parsed_command', parsed)

                cmd = parsed
                if cmd[0] == 'sequence':
                    print(f'Executing {len(cmd[1])} actions in sequence')
                    keep_running = True
                    for index, sub_cmd in enumerate(cmd[1], start=1):
                        print(f'Step {index}/{len(cmd[1])}: {sub_cmd[0]}')
                        keep_running = execute_command(comm, ucv, hum, ollama_model, sub_cmd)
                        if not keep_running:
                            break
                    if not keep_running:
                        break
                else:
                    keep_running = execute_command(comm, ucv, hum, ollama_model, cmd)
                    if not keep_running:
                        break

            except Exception as e:
                print('Command processing error:', e)
                # keep the loop running for the next command
                continue
    except KeyboardInterrupt:
        print('\nInterrupted by user')

    finally:
        try:
            if cfg.get('manual_scene.clear_on_exit', True):
                print('Clearing generated world and returning to empty map...')
                comm.clear_env(keep_roads=False)
        except Exception as e:
            print('Cleanup warning:', e)
        print('Disconnecting...')
        try:
            ucv.disconnect()
        except Exception:
            pass


def generate_lightweight_world(comm: Communicator, cfg: Config):
    """Generate and load a procedural world into the currently opened UE map."""
    fixed_world_json = os.environ.get('SIMWORLD_FIXED_WORLD_JSON')
    if fixed_world_json:
        world_json = Path(fixed_world_json)
        ue_asset_path = Path(cfg['citygen.ue_asset_path'])
        if not world_json.exists():
            raise FileNotFoundError(f'Fixed world file not found: {world_json}')
        if not ue_asset_path.exists():
            raise FileNotFoundError(f'UE asset library not found: {ue_asset_path}')

        print(f'Loading fixed world from {world_json}...')
        comm.clear_env(keep_roads=False)
        comm.generate_world(str(world_json), str(ue_asset_path), run_time=False)
        return

    output_dir = Path(cfg['citygen.output_dir'])
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f'Generating procedural city into {output_dir}...')
    from simworld.citygen.city.city_generator import CityGenerator
    from simworld.utils.data_exporter import DataExporter

    city = CityGenerator(cfg)
    city.generate()
    exporter = DataExporter(city)
    exporter.export_to_json(str(output_dir))
    apply_manual_scene_overrides(Path(cfg['citygen.world_json']), cfg)

    world_json = Path(cfg['citygen.world_json'])
    ue_asset_path = Path(cfg['citygen.ue_asset_path'])
    if not world_json.exists():
        raise FileNotFoundError(f'Generated world file not found: {world_json}')
    if not ue_asset_path.exists():
        raise FileNotFoundError(f'UE asset library not found: {ue_asset_path}')

    print(f'Loading generated world from {world_json}...')
    comm.clear_env(keep_roads=False)
    comm.generate_world(str(world_json), str(ue_asset_path), run_time=False)


def apply_manual_scene_overrides(world_json: Path, cfg: Config):
    """Apply deterministic scene tweaks after procedural export."""
    if cfg.get('manual_scene.scattered_trees.enabled', False):
        add_scattered_trees(
            world_json,
            count=int(cfg.get('manual_scene.scattered_trees.count', 10)),
            min_radius_cm=float(cfg.get('manual_scene.scattered_trees.min_radius_cm', 500)),
            max_radius_cm=float(cfg.get('manual_scene.scattered_trees.max_radius_cm', 1500)),
        )


def add_scattered_trees(world_json: Path, count: int, min_radius_cm: float, max_radius_cm: float):
    """Replace generated element clutter with a small scattered set of trees."""
    data = json.loads(world_json.read_text(encoding='utf-8'))
    nodes = data.get('nodes', [])

    # Keep roads/buildings from citygen and remove any previously generated tree/element clutter.
    kept_nodes = [node for node in nodes if not node.get('instance_name', '').startswith('BP_Tree')]

    tree_types = ['BP_Tree1_C', 'BP_Tree2_C', 'BP_Tree3_C', 'BP_Tree4_C', 'BP_Tree5_C', 'BP_Tree6_C']
    rng = random.Random(42)
    min_radius_cm = max(0.0, float(min_radius_cm))
    max_radius_cm = max(min_radius_cm, float(max_radius_cm))

    for index in range(max(0, count)):
        angle = rng.uniform(0.0, 2.0 * math.pi)
        radius = rng.uniform(min_radius_cm, max_radius_cm)
        x = round(math.cos(angle) * radius, 2)
        y = round(math.sin(angle) * radius, 2)
        kept_nodes.append(
            {
                'id': f'ScatterTree_{index + 1}',
                'instance_name': tree_types[index % len(tree_types)],
                'properties': {
                    'location': {'x': x, 'y': y, 'z': 20},
                    'orientation': {'pitch': 0, 'yaw': rng.randint(0, 359), 'roll': 0},
                    'scale': {'x': 1.0, 'y': 1.0, 'z': 1.0},
                },
            }
        )

    data['nodes'] = kept_nodes
    world_json.write_text(json.dumps(data, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
