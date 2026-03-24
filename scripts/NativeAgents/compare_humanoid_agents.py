"""Compare custom humanoid vs native humanoid in the same SimWorld scene."""

from pathlib import Path
import json
import os
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.Drone.common import maybe_launch_simworld, startup_log, wait_for_simworld_server, wait_for_user_world_ready
from scripts.NativeAgents.comparison_world import load_comparison_world
from scripts.NativeAgents.native_command_interpreter import NativeCommandInterpreter
from scripts.NativeAgents.native_local_planner import NativeHumanoidPlanner
from scripts.NativeAgents.native_semantics import resolve_semantic_target
from scripts.NativeAgents.ollama_a2a import OllamaA2AAdapter
from scripts.humanoid.map.humanoid_map import navigate_to_option, survey_semantic_candidates
from scripts.humanoid.movement.humanoid_movement import cleanup_prompt_agent_actors, get_humanoid_pose
from scripts.humanoid.world import generate_lightweight_world

from simworld.agent.humanoid import Humanoid
from simworld.communicator.communicator import Communicator
from simworld.communicator.unrealcv import UnrealCV
from simworld.config import Config
from simworld.map.map import Map
from simworld.utils.vector import Vector

DEFAULT_PROMPTS = [
    'go to the nearest building',
    'go to the nearest store',
    'go to the nearest tree',
]
VALID_ACCURACY_LABELS = {'correct', 'partial', 'wrong'}


def build_map(cfg: Config) -> Map:
    world_map = Map(cfg)
    world_map.initialize_map_from_file()
    return world_map


def spawn_humanoid(comm: Communicator, cfg: Config, world_map: Map, start_pos: Vector):
    hum = Humanoid(start_pos, Vector(1, 0), map=world_map, communicator=comm, config=cfg)
    comm.spawn_agent(hum, name=None)
    time.sleep(0.5)
    return hum


def read_prompt_list():
    prompt_text = os.environ.get('COMPARE_PROMPTS', '').strip()
    if prompt_text:
        return [item.strip() for item in prompt_text.split('|') if item.strip()]
    return list(DEFAULT_PROMPTS)


def run_custom_trial(comm, ucv, cfg, world_map, start_pos: Vector, prompt: str, ollama_model: str):
    cleanup_prompt_agent_actors(comm)
    hum = spawn_humanoid(comm, cfg, world_map, start_pos)
    result = {'controller': 'custom', 'prompt': prompt}
    try:
        start_pose, _ = get_humanoid_pose(comm, ucv, hum)
        options = survey_semantic_candidates(comm, ucv, hum, ollama_model, prompt)
        if not options:
            result.update({'success': False, 'reason': 'no_options'})
            return result
        target = options[0]
        target_pos = Vector(float(target['world_x']), float(target['world_y']))
        started_at = time.time()
        navigate_to_option(comm, ucv, hum, 1)
        elapsed = time.time() - started_at
        end_pose, end_yaw = get_humanoid_pose(comm, ucv, hum)
        remaining = end_pose.distance(target_pos)
        result.update(
            {
                'success': True,
                'selected_target': target['name'],
                'target_category': target.get('category'),
                'target_position': {'x': target_pos.x, 'y': target_pos.y},
                'start_position': {'x': start_pose.x, 'y': start_pose.y},
                'end_position': {'x': end_pose.x, 'y': end_pose.y},
                'end_yaw': end_yaw,
                'elapsed_sec': elapsed,
                'remaining_distance_cm': remaining,
            }
        )
        return result
    finally:
        cleanup_prompt_agent_actors(comm)


def run_native_trial(comm, ucv, cfg, world_map, start_pos: Vector, prompt: str, interpreter: NativeCommandInterpreter, model: OllamaA2AAdapter):
    cleanup_prompt_agent_actors(comm)
    hum = spawn_humanoid(comm, cfg, world_map, start_pos)
    planner = NativeHumanoidPlanner(
        agent=hum,
        model=model,
        rule_based=cfg.get('user.rule_based', True),
        dt=float(cfg.get('simworld.dt', 0.1)),
    )
    result = {'controller': 'native', 'prompt': prompt}
    try:
        start_pose, _ = planner.sync_agent_pose()
        parsed, parser_name = interpreter.parse(prompt)
        result['parser'] = parser_name
        if parsed is None:
            result.update({'success': False, 'reason': 'parse_failed'})
            return result

        action = str(parsed.get('action', 'unknown')).lower()
        if action == 'semantic_goto':
            query = str(parsed.get('query', prompt)).strip() or prompt
            visible_only = bool(parsed.get('visible_only', False))
            target, candidates = resolve_semantic_target(comm, hum, query, visible_only=visible_only)
            result['candidate_count'] = len(candidates)
            if target is None:
                result.update({'success': False, 'reason': 'no_target'})
                return result
            target_pos = Vector(target['world_x'], target['world_y'])
            destination = world_map.get_closest_node(target_pos).position
            started_at = time.time()
            planner.navigate_to(destination)
            elapsed = time.time() - started_at
            end_pose, end_yaw = planner.sync_agent_pose()
            result.update(
                {
                    'success': True,
                    'selected_target': target['name'],
                    'target_category': target.get('category'),
                    'target_position': {'x': target_pos.x, 'y': target_pos.y},
                    'nav_destination': {'x': destination.x, 'y': destination.y},
                    'start_position': {'x': start_pose.x, 'y': start_pose.y},
                    'end_position': {'x': end_pose.x, 'y': end_pose.y},
                    'end_yaw': end_yaw,
                    'elapsed_sec': elapsed,
                    'remaining_distance_cm': end_pose.distance(target_pos),
                    'remaining_to_nav_node_cm': end_pose.distance(destination),
                }
            )
            return result

        if action == 'planner_plan':
            plan = str(parsed.get('plan', prompt)).strip() or prompt
            started_at = time.time()
            actions = planner.parse(plan)
            if actions is None:
                result.update({'success': False, 'reason': 'planner_parse_failed'})
                return result
            planner.execute(actions)
            elapsed = time.time() - started_at
            end_pose, end_yaw = planner.sync_agent_pose()
            result.update(
                {
                    'success': True,
                    'selected_target': None,
                    'start_position': {'x': start_pose.x, 'y': start_pose.y},
                    'end_position': {'x': end_pose.x, 'y': end_pose.y},
                    'end_yaw': end_yaw,
                    'elapsed_sec': elapsed,
                    'remaining_distance_cm': None,
                }
            )
            return result

        result.update({'success': False, 'reason': f'unhandled_action:{action}'})
        return result
    finally:
        cleanup_prompt_agent_actors(comm)


def summarize_pair(custom_result, native_result):
    def score_line(item):
        if not item.get('success'):
            return f'fail ({item.get("reason", "unknown")})'
        remaining = item.get('remaining_distance_cm')
        if isinstance(remaining, (int, float)):
            return f'remaining={remaining:.1f}cm, time={item.get("elapsed_sec", 0.0):.2f}s'
        return f'time={item.get("elapsed_sec", 0.0):.2f}s'

    print(f'Prompt: {custom_result["prompt"]}')
    print(f' - custom: {score_line(custom_result)}')
    print(f' - native: {score_line(native_result)}')


def collect_manual_accuracy(controller_name: str, prompt: str):
    print(f'\nManual accuracy review for {controller_name} on prompt: {prompt}')
    while True:
        label = input('Accuracy [correct/partial/wrong]: ').strip().lower()
        if label in VALID_ACCURACY_LABELS:
            break
        print('Please enter exactly: correct, partial, or wrong')
    notes = input('Notes: ').strip()
    return {'label': label, 'notes': notes, 'timestamp': time.time()}


def main():
    startup_log('Starting custom-vs-native humanoid comparison...')
    launch_state = maybe_launch_simworld()
    if launch_state in ('launched', 'reused'):
        wait_for_user_world_ready()
    wait_for_simworld_server()

    cfg = Config(os.environ.get('SIMWORLD_CONFIG', 'config/light.yaml'))
    host = os.environ.get('SIMWORLD_HOST', '127.0.0.1')
    port = int(os.environ.get('SIMWORLD_PORT', '9000'))
    ucv = UnrealCV(port=port, ip=host, resolution=(640, 480))
    comm = Communicator(ucv)

    if os.environ.get('SIMWORLD_COMPARISON_WORLD', '1') == '1':
        load_comparison_world(comm, cfg)
    elif os.environ.get('SIMWORLD_GENERATE_WORLD', '1') == '1':
        generate_lightweight_world(comm, cfg)

    world_map = build_map(cfg)
    model = OllamaA2AAdapter()
    interpreter = NativeCommandInterpreter(model)
    ollama_model = os.environ.get('OLLAMA_MODEL', 'phi3')
    start_pos = Vector(0, 0)
    prompts = read_prompt_list()

    results = {
        'timestamp': time.time(),
        'world_config': os.environ.get('SIMWORLD_CONFIG', 'config/light.yaml'),
        'comparison_world_enabled': os.environ.get('SIMWORLD_COMPARISON_WORLD', '1') == '1',
        'ollama_model': ollama_model,
        'prompts': prompts,
        'trials': [],
    }
    output_dir = REPO_ROOT / 'logs'
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f'humanoid_comparison_{int(results["timestamp"])}.json'

    def persist_results():
        output_path.write_text(json.dumps(results, indent=2), encoding='utf-8')

    try:
        for prompt in prompts:
            print(f'\n=== Comparing prompt: {prompt} ===')
            custom_result = run_custom_trial(comm, ucv, cfg, world_map, start_pos, prompt, ollama_model)
            custom_result['manual_accuracy'] = collect_manual_accuracy('custom', prompt)
            native_result = run_native_trial(comm, ucv, cfg, world_map, start_pos, prompt, interpreter, model)
            native_result['manual_accuracy'] = collect_manual_accuracy('native', prompt)
            summarize_pair(custom_result, native_result)
            results['trials'].append({'prompt': prompt, 'custom': custom_result, 'native': native_result})
            persist_results()
    finally:
        persist_results()
        try:
            cleanup_prompt_agent_actors(comm)
        except Exception:
            pass
        try:
            if cfg.get('manual_scene.clear_on_exit', True):
                comm.clear_env(keep_roads=False)
        except Exception:
            pass
        try:
            ucv.disconnect()
        except Exception:
            pass
    print(f'\nSaved comparison results to {output_path}')


if __name__ == '__main__':
    main()
