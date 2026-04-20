from pathlib import Path
import os
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.UltraHumanoid.common import (
    DEFAULT_UNREALCV_PORT,
    debug_enabled,
    debug_log,
    maybe_launch_simworld,
    parse_local_command,
    parse_ollama_command,
    wait_for_simworld_server,
    wait_for_user_world_ready,
)
from scripts.UltraHumanoid.Movement.navigation import calibrate_walk_speed
from scripts.UltraHumanoid.Robots.controller import execute_command, print_help

from simworld.agent.humanoid import Humanoid
from simworld.communicator.communicator import Communicator
from simworld.communicator.unrealcv import UnrealCV
from simworld.config import Config
from simworld.map.map import Map
from simworld.utils.vector import Vector

from scripts.UltraHumanoid.worlds import cleanup_ultra_humanoid_actors, generate_lightweight_world, load_comparison_world


def build_map(cfg):
    world_map = Map(cfg)
    world_map.initialize_map_from_file()
    return world_map


def reusing_current_world() -> bool:
    return os.environ.get('SIMWORLD_REUSE_CURRENT_WORLD', '0') == '1'


def main():
    launch_state = maybe_launch_simworld()
    if launch_state in ('launched', 'reused'):
        wait_for_user_world_ready()
    wait_for_simworld_server()

    resolution = (640, 480)
    host = os.environ.get('SIMWORLD_HOST', '127.0.0.1')
    port = int(os.environ.get('SIMWORLD_PORT', str(DEFAULT_UNREALCV_PORT)))
    ucv = UnrealCV(port=port, ip=host, resolution=resolution)
    comm = Communicator(ucv)
    cfg = Config(os.environ.get('SIMWORLD_CONFIG', 'config/light.yaml'))

    if not reusing_current_world():
        cleanup_ultra_humanoid_actors(comm)
        time.sleep(0.5)

    if os.environ.get('SIMWORLD_COMPARISON_WORLD', '0') == '1':
        load_comparison_world(comm, cfg)
    elif os.environ.get('SIMWORLD_GENERATE_WORLD', '1') == '1':
        generate_lightweight_world(comm, cfg)

    world_map = build_map(cfg)
    hum = Humanoid(Vector(0, 0), Vector(1, 0), map=world_map, communicator=comm, config=cfg)
    print(f'Spawning ultra humanoid id={hum.id}...')
    comm.spawn_agent(hum, name=None)
    walk_speed = calibrate_walk_speed(comm, hum)

    ollama_model = os.environ.get('OLLAMA_MODEL', 'phi3')
    print('Ultra humanoid ready.')
    print_help()
    if debug_enabled():
        print('Debug logging enabled via DEBUG_ULTRA_HUMANOID=1')

    try:
        while True:
            text = input('ultra> ')
            local = parse_local_command(text)
            if local is not None:
                cmd = local
                parser_name = 'local'
            else:
                cmd = parse_ollama_command(text, ollama_model)
                parser_name = 'ollama'
            if cmd is None:
                print('Could not parse command.')
                continue
            debug_log('ultra_input', text)
            debug_log('ultra_parser', parser_name)
            debug_log('ultra_command', cmd)
            keep_running = execute_command(comm, ucv, hum, cfg, walk_speed, cmd)
            if not keep_running:
                break
    except KeyboardInterrupt:
        print('\nInterrupted by user')
    finally:
        try:
            if (not reusing_current_world()) and cfg.get('manual_scene.clear_on_exit', True):
                comm.clear_env(keep_roads=False)
        except Exception:
            pass
        try:
            ucv.disconnect()
        except Exception:
            pass


if __name__ == '__main__':
    main()
