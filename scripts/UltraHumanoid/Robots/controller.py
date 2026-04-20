from scripts.UltraHumanoid.common import DEFAULT_STEP_DURATION_SEC, clamp
from simworld.utils.vector import Vector

from scripts.UltraHumanoid.Map.world_model import candidate_key, get_agent_pose, resolve_target, scan_world
from scripts.UltraHumanoid.Movement.navigation import navigate_direct_to_target

SESSION_STATE = {
    'last_semantic_target_key': None,
    'last_semantic_target_name': None,
}


def print_help():
    print('Ultra humanoid commands:')
    print(' - go to 1200 400')
    print(' - go to the nearest building')
    print(' - go to the nearest store')
    print(' - go to the visible store')
    print(' - go to the nearest tree')
    print(' - go to the furthest tree')
    print(' - go to another tree')
    print(' - go to a different tree')
    print(' - walk to 3 different trees')
    print(' - go 5 steps forward')
    print(' - take 5 steps left')
    print(' - look')
    print(' - status')
    print(' - quit')


def _semantic_goto(comm, ucv, hum, cfg, walk_speed, cmd):
    query = str(cmd.get('query', '')).strip()
    visible_only = bool(cmd.get('visible_only', False))
    selector = str(cmd.get('selector', '') or '').strip().lower() or None
    count = max(1, int(cmd.get('count', 1) or 1))
    visited_keys = []
    any_success = False

    for visit_index in range(count):
        exclude_key = None
        if selector in ('another', 'different'):
            if visit_index == 0:
                previous = SESSION_STATE.get('last_semantic_target_key')
                exclude_key = [previous] if previous is not None else []
            else:
                exclude_key = list(visited_keys)

        target, candidates = resolve_target(
            comm,
            hum,
            cfg,
            query,
            visible_only=visible_only,
            selector=selector,
            exclude_key=exclude_key,
        )
        label = f'Semantic candidates for "{query}"'
        if count > 1:
            label += f' [visit {visit_index + 1}/{count}]'
        print(f'{label}:')
        for item in candidates[:8]:
            print(f' - {item["name"]} | {item["category"]} | {item["distance"]:.1f} cm | angle={item["relative_angle"]:.1f}')
        if target is None:
            print('No matching target found.')
            return any_success or count == 0

        ok, remaining = navigate_direct_to_target(comm, ucv, hum, target, walk_speed)
        target_key = candidate_key(target)
        SESSION_STATE['last_semantic_target_key'] = target_key
        SESSION_STATE['last_semantic_target_name'] = target['name']
        visited_keys.append(target_key)
        print(f'Target {target["name"]}: success={ok}, remaining={remaining:.1f} cm')
        any_success = any_success or ok
    return True


def execute_command(comm, ucv, hum, cfg, walk_speed, cmd):
    action = str(cmd.get('action', 'unknown')).lower()
    if action == 'help':
        print_help()
        return True
    if action == 'quit':
        return False
    if action == 'status':
        pos, yaw = get_agent_pose(comm, hum)
        print(f'Position={pos}, yaw={yaw:.1f}, walk_speed={walk_speed:.1f} cm/s')
        return True
    if action == 'look':
        results = scan_world(comm, hum, cfg)
        print('Nearby objects:')
        for item in results[:12]:
            print(f' - {item["name"]} | {item["category"] or "unknown"} | {item["distance"]:.1f} cm')
        return True
    if action == 'goto':
        target = {'name': 'coordinate_target', 'world_x': float(cmd['x']), 'world_y': float(cmd['y']), 'radius_cm': 80.0}
        ok, remaining = navigate_direct_to_target(comm, ucv, hum, target, walk_speed)
        print(f'Coordinate navigation complete: success={ok}, remaining={remaining:.1f} cm')
        return True
    if action == 'manual_move':
        steps = max(0.1, float(cmd.get('steps', 1.0) or 1.0))
        direction_name = str(cmd.get('direction', 'forward') or 'forward').strip().lower()
        direction_map = {
            'forward': 0,
            'backward': 1,
            'left': 2,
            'right': 3,
        }
        direction_code = direction_map.get(direction_name)
        if direction_code is None:
            print(f'Unsupported step direction: {direction_name}')
            return True
        duration = clamp(steps * DEFAULT_STEP_DURATION_SEC, 0.1, 20.0)
        print(f'Ultra movement: taking {steps:.1f} step(s) {direction_name} for {duration:.2f}s')
        comm.humanoid_step_forward(hum.id, duration, direction=direction_code)
        pos, yaw = get_agent_pose(comm, hum)
        print(f'Ultra movement complete: position={pos}, yaw={yaw:.1f}')
        return True
    if action == 'sequence':
        steps = cmd.get('steps', [])
        if not isinstance(steps, list) or not steps:
            print('Sequence command has no steps.')
            return True
        for index, step in enumerate(steps, start=1):
            print(f'Executing sequence step {index}/{len(steps)}...')
            keep_running = execute_command(comm, ucv, hum, cfg, walk_speed, step)
            if not keep_running:
                return False
        return True
    if action == 'semantic_goto':
        _semantic_goto(comm, ucv, hum, cfg, walk_speed, cmd)
        return True
    print(f'Unknown command: {cmd}')
    return True
