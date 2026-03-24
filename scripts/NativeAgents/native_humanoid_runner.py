"""Experimental runner that reuses SimWorld Humanoid + LocalPlanner + Map."""

from pathlib import Path
import os
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.Drone.common import maybe_launch_simworld, startup_log, wait_for_simworld_server, wait_for_user_world_ready
from scripts.humanoid.world import generate_lightweight_world
from scripts.NativeAgents.native_command_interpreter import NativeCommandInterpreter
from scripts.NativeAgents.native_local_planner import NativeHumanoidPlanner
from scripts.NativeAgents.ollama_a2a import OllamaA2AAdapter
from scripts.NativeAgents.native_semantics import resolve_semantic_target, summarize_candidates

try:
    from simworld.agent.humanoid import Humanoid
    from simworld.communicator.communicator import Communicator
    from simworld.communicator.unrealcv import UnrealCV
    from simworld.config import Config
    from simworld.map.map import Map
    from simworld.utils.vector import Vector
except Exception as e:
    startup_log(f'Native agent imports failed: {type(e).__name__}: {e}')
    raise


def build_map(cfg: Config) -> Map:
    world_map = Map(cfg)
    world_map.initialize_map_from_file()
    return world_map


def print_help():
    print('Native commands:')
    print(' - go to [0, 0]')
    print(' - navigate to 200 0')
    print(' - go to the nearest building')
    print(' - go to the nearest store')
    print(' - go to the nearest tree')
    print(' - go to the visible store')
    print(' - look')
    print(' - status')
    print(' - quit')


def main():
    startup_log('Starting native SimWorld humanoid experiment...')
    launch_state = maybe_launch_simworld()
    if launch_state in ('launched', 'reused'):
        wait_for_user_world_ready()
    wait_for_simworld_server()

    config_path = os.environ.get('SIMWORLD_CONFIG', 'config/light.yaml')
    cfg = Config(config_path)
    host = os.environ.get('SIMWORLD_HOST', '127.0.0.1')
    port = int(os.environ.get('SIMWORLD_PORT', '9000'))
    ucv = UnrealCV(port=port, ip=host, resolution=(640, 480))
    comm = Communicator(ucv)

    if os.environ.get('SIMWORLD_GENERATE_WORLD', '1') == '1':
        generate_lightweight_world(comm, cfg)

    world_map = build_map(cfg)
    hum = Humanoid(Vector(0, 0), Vector(1, 0), map=world_map, communicator=comm, config=cfg)
    comm.spawn_agent(hum, name=None)
    time.sleep(0.5)

    model = OllamaA2AAdapter()
    interpreter = NativeCommandInterpreter(model)
    planner = NativeHumanoidPlanner(
        agent=hum,
        model=model,
        rule_based=cfg.get('user.rule_based', True),
        dt=float(cfg.get('simworld.dt', 0.1)),
    )
    planner.sync_agent_pose()

    print('Native SimWorld planner ready.')
    print('This experiment reuses simworld.agent.Humanoid, simworld.map.Map, simworld.local_planner.LocalPlanner, and simworld.llm.BaseLLM patterns.')
    print('It now also supports semantic native tests like nearest building/store/tree resolution before map navigation.')
    print_help()

    try:
        while True:
            text = input('native-humanoid> ').strip()
            if not text:
                continue
            planner.sync_agent_pose()

            parsed, parser_name = interpreter.parse(text)
            print(f'Parser={parser_name}, parsed={parsed}')
            if parsed is None:
                print('Interpreter could not parse that command.')
                continue

            action = str(parsed.get('action', 'unknown')).lower()
            if action == 'quit':
                break
            if action == 'help':
                print_help()
                continue
            if action == 'status':
                pos, yaw = planner.sync_agent_pose()
                print(f'Current pose: position={pos}, yaw={yaw:.1f}')
                continue
            if action == 'look':
                target, candidates = resolve_semantic_target(comm, hum, 'building')
                print('Nearby semantic snapshot:')
                print(summarize_candidates(candidates))
                continue
            if action == 'semantic_goto':
                query = str(parsed.get('query', text)).strip() or text
                visible_only = bool(parsed.get('visible_only', False))
                target, candidates = resolve_semantic_target(comm, hum, query, visible_only=visible_only)
                print('Candidates:')
                print(summarize_candidates(candidates))
                if target is None:
                    print(f'No semantic target matched "{query}".')
                    continue
                destination = Vector(target['world_x'], target['world_y'])
                nearest_node = world_map.get_closest_node(destination)
                print(f'Selected target: {target["name"]}')
                print(f'Navigating to nearest map node at {nearest_node.position}')
                planner.navigate_to(nearest_node.position)
            else:
                plan = str(parsed.get('plan', text)).strip() or text
                actions = planner.parse(plan)
                if actions is None:
                    print('Planner could not parse that plan.')
                    continue
                print(f'Parsed planner actions: {actions}')
                planner.execute(actions)

            planner.sync_agent_pose()
            print(f'Current pose: position={hum.position}, yaw={hum.yaw}')
    except KeyboardInterrupt:
        print('\nInterrupted by user')
    finally:
        try:
            if cfg.get('manual_scene.clear_on_exit', True):
                comm.clear_env(keep_roads=False)
        except Exception:
            pass
        try:
            ucv.disconnect()
        except Exception:
            pass


if __name__ == '__main__':
    main()
