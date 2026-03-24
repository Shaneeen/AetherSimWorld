from pathlib import Path
import os
import sys
import time

from scripts.humanoid.common import (
    DEFAULT_UNREALCV_PORT,
    REPO_ROOT,
    debug_enabled,
    debug_log,
    maybe_launch_simworld,
    ollama_parse_command,
    parse_local_command,
    startup_log,
    wait_for_simworld_server,
    wait_for_user_world_ready,
)

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

startup_log(f'Python executable: {sys.executable}')
startup_log(f'Working directory: {os.getcwd()}')
startup_log(f'Repo root: {REPO_ROOT}')

try:
    startup_log('Importing SimWorld modules...')
    from simworld.agent.humanoid import Humanoid
    from simworld.communicator.communicator import Communicator
    from simworld.communicator.unrealcv import UnrealCV
    from simworld.config import Config
    from simworld.utils.vector import Vector
    startup_log('SimWorld imports succeeded.')
except Exception as e:
    startup_log(f'SimWorld import failed: {type(e).__name__}: {e}')
    raise

from scripts.humanoid.movement.humanoid_movement import calibrate_walk_speed, cleanup_prompt_agent_actors
from scripts.humanoid.robots.humanoid_commands import execute_command, print_help
from scripts.humanoid.vision.humanoid_vision import print_runtime_status
from scripts.humanoid.world import generate_lightweight_world


def main():
    launch_state = maybe_launch_simworld()
    if launch_state in ('launched', 'reused'):
        wait_for_user_world_ready()
    wait_for_simworld_server()

    print(f'Connecting to UnrealCV (localhost:{DEFAULT_UNREALCV_PORT})...')
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

    if os.environ.get('USE_UE_MANAGER', '0') == '1':
        try:
            ue_manager_path = cfg.get('simworld.ue_manager_path', None)
            if ue_manager_path:
                print(f'Spawning UE manager asset: {ue_manager_path}')
                comm.spawn_ue_manager(ue_manager_path)
                time.sleep(0.5)
                try:
                    comm.update_objects()
                except Exception:
                    pass
        except Exception as e:
            print('Failed to spawn UE manager (continuing):', e)

    if os.environ.get('SIMWORLD_GENERATE_WORLD', '0') == '1':
        try:
            generate_lightweight_world(comm, cfg)
        except Exception as e:
            print('Failed to generate procedural world:', e)
            print('Tip: start SimWorld with /Game/Maps/empty.umap before enabling SIMWORLD_GENERATE_WORLD=1')

    hum = Humanoid(Vector(0, 0), Vector(1, 0), communicator=comm)
    print(f'Spawning humanoid id={hum.id}...')
    comm.spawn_agent(hum, name=None)
    calibrate_walk_speed(comm, ucv, hum)

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

                if parsed[0] == 'sequence':
                    keep_running = True
                    print(f'Executing {len(parsed[1])} actions in sequence')
                    for index, sub_cmd in enumerate(parsed[1], start=1):
                        print(f'Step {index}/{len(parsed[1])}: {sub_cmd[0]}')
                        keep_running = execute_command(comm, ucv, hum, ollama_model, sub_cmd)
                        if not keep_running:
                            break
                    if not keep_running:
                        break
                else:
                    keep_running = execute_command(comm, ucv, hum, ollama_model, parsed)
                    if not keep_running:
                        break
            except Exception as e:
                print('Command processing error:', e)
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


if __name__ == '__main__':
    main()
