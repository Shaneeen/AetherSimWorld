from simworld.utils.vector import Vector

from scripts.UltraHumanoid.Map.world_model import get_agent_pose, resolve_target, scan_world
from scripts.UltraHumanoid.Movement.navigation import navigate_direct_to_target


def print_help():
    print('Ultra humanoid commands:')
    print(' - go to the nearest building')
    print(' - go to the nearest store')
    print(' - go to the visible store')
    print(' - go to the nearest tree')
    print(' - look')
    print(' - status')
    print(' - quit')


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
    if action == 'semantic_goto':
        query = str(cmd.get('query', '')).strip()
        visible_only = bool(cmd.get('visible_only', False))
        target, candidates = resolve_target(comm, hum, cfg, query, visible_only=visible_only)
        print(f'Semantic candidates for "{query}":')
        for item in candidates[:8]:
            print(f' - {item["name"]} | {item["category"]} | {item["distance"]:.1f} cm | angle={item["relative_angle"]:.1f}')
        if target is None:
            print('No matching target found.')
            return True
        ok, remaining = navigate_direct_to_target(comm, ucv, hum, target, walk_speed)
        print(f'Target {target["name"]}: success={ok}, remaining={remaining:.1f} cm')
        return True
    print(f'Unknown command: {cmd}')
    return True
