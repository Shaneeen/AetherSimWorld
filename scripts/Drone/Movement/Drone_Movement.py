"""High-level drone movement and semantic target helpers."""
import math
import json
from pathlib import Path
from typing import Iterable, Optional

from simworld.utils.vector import Vector
from scripts.Drone.Vision.Drone_Vision import obstacle_ahead, get_forward_tree_mask_stats


DEFAULT_ALTITUDE_OFFSET_CM = 900.0
DEFAULT_MOVE_CHUNK_CM = 700.0
DEFAULT_MAX_ITERATIONS = 8
DEFAULT_TREE_SAFETY_RADIUS_CM = 350.0
DEFAULT_TREE_TOP_CLEARANCE_CM = 250.0

REPO_ROOT = Path(__file__).resolve().parents[3]
WORLD_JSON_PATH = REPO_ROOT / 'output' / 'light_world' / 'progen_world.json'
BOUNDING_BOXES_PATH = REPO_ROOT / 'data' / 'bounding_boxes.json'


def get_actor_xy(comm, actor_name: str) -> Vector:
    loc = comm.unrealcv.get_location(actor_name)
    return Vector(float(loc[0]), float(loc[1]))


def list_tree_targets(comm) -> list[dict]:
    """Return generated tree actors currently present in the world."""
    targets = []
    world_tree_data = load_tree_metadata()
    try:
        objects = comm.unrealcv.get_objects()
    except Exception:
        return targets

    for name in objects:
        lowered = str(name).lower()
        if 'scattertree_' not in lowered and 'dronescattertree_' not in lowered and 'bp_tree' not in lowered:
            continue
        try:
            loc = comm.unrealcv.get_location(name)
        except Exception:
            continue
        tree_meta = world_tree_data.get(name, {})
        targets.append(
            {
                'name': name,
                'position': Vector(float(loc[0]), float(loc[1])),
                'z': float(loc[2]),
                'instance_name': tree_meta.get('instance_name'),
                'height_cm': float(tree_meta.get('height_cm', 150.0)),
                'radius_cm': float(tree_meta.get('radius_cm', DEFAULT_TREE_SAFETY_RADIUS_CM)),
            }
        )
    return targets


def load_tree_metadata() -> dict:
    metadata = {}
    if not WORLD_JSON_PATH.exists() or not BOUNDING_BOXES_PATH.exists():
        return metadata

    try:
        world_data = json.loads(WORLD_JSON_PATH.read_text(encoding='utf-8'))
        bbox_data = json.loads(BOUNDING_BOXES_PATH.read_text(encoding='utf-8'))
        element_boxes = bbox_data.get('elements', {})
    except Exception:
        return metadata

    for node in world_data.get('nodes', []):
        instance_name = node.get('instance_name', '')
        node_id = node.get('id')
        if not node_id or not instance_name.startswith('BP_Tree'):
            continue
        bbox = element_boxes.get(instance_name, {}).get('bbox', {})
        width_cm = float(bbox.get('x', 0.0))
        depth_cm = float(bbox.get('y', width_cm))
        height_cm = float(bbox.get('z', max(width_cm, depth_cm, 150.0)))
        radius_cm = max(width_cm, depth_cm) / 2.0 + 120.0
        metadata[node_id] = {
            'instance_name': instance_name,
            'height_cm': height_cm,
            'radius_cm': max(radius_cm, DEFAULT_TREE_SAFETY_RADIUS_CM),
        }
    return metadata


def find_nearest_tree(comm, origin_xy: Vector) -> Optional[dict]:
    targets = list_tree_targets(comm)
    if not targets:
        return None
    return min(targets, key=lambda item: origin_xy.distance(item['position']))


def move_drone_toward_xy(drone, target_xy: Vector, target_z: Optional[float] = None, chunk_cm: float = DEFAULT_MOVE_CHUNK_CM, max_iterations: int = DEFAULT_MAX_ITERATIONS):
    """Move a drone toward a target in chunked iterations.

    One chunked movement command counts as one iteration, even if the drone
    uses multiple internal interpolation steps for smooth motion.
    """
    chunk_cm = max(50.0, float(chunk_cm))
    max_iterations = max(1, int(max_iterations))
    target_z = drone.z if target_z is None else float(target_z)

    for iteration in range(1, max_iterations + 1):
        current = drone.position
        remaining = current.distance(target_xy)
        print(f'Drone movement iteration {iteration}/{max_iterations}: remaining={remaining:.1f} cm')
        if remaining <= chunk_cm:
            drone.move_to(target_xy.x, target_xy.y, target_z, duration=1.0, steps=8)
            print('Drone movement: final approach completed.')
            return True

        direction_x = (target_xy.x - current.x) / remaining
        direction_y = (target_xy.y - current.y) / remaining
        heading_deg = math.degrees(math.atan2(direction_y, direction_x))
        blocked, stats = obstacle_ahead(drone.comm, drone, heading_deg=heading_deg)
        mask_stats = get_forward_tree_mask_stats(drone.comm, drone, heading_deg=heading_deg)
        if stats:
            print(
                'Drone vision: '
                f'min_depth={stats["min_depth_cm"]:.1f} cm, '
                f'mean_depth={stats["mean_depth_cm"]:.1f} cm, '
                f'blocked={blocked}'
            )
        else:
            print('Drone vision: no usable depth stats, treating path as clear.')
        if mask_stats:
            print(
                'Drone object_mask: '
                f'dominant_color={mask_stats["dominant_color"]}, '
                f'dominant_pixels={mask_stats["dominant_pixels"]}, '
                f'blocked={mask_stats["blocked"]}'
            )
        else:
            print('Drone object_mask: no usable mask stats.')

        blocked = blocked or bool(mask_stats and mask_stats['blocked'])
        if blocked:
            if stats:
                print(f'Drone vision: obstacle detected ahead at ~{stats["min_depth_cm"]:.1f} cm, climbing to avoid it.')
            else:
                print('Drone vision: object mask indicates obstruction ahead, climbing to avoid it.')
            drone.move_up(180.0, duration=0.8)
            lateral_sign = -1.0 if iteration % 2 == 0 else 1.0
            drone.move_by(-direction_y * 140.0 * lateral_sign, direction_x * 140.0 * lateral_sign, 0.0, duration=0.8, steps=6)

        next_x = current.x + direction_x * chunk_cm
        next_y = current.y + direction_y * chunk_cm
        drone.move_to(next_x, next_y, target_z, duration=1.0, steps=8)

    final_remaining = drone.position.distance(target_xy)
    print(f'Drone movement stopped after {max_iterations} iterations with {final_remaining:.1f} cm remaining.')
    return final_remaining <= chunk_cm


def compute_safe_tree_hover_xy(tree_xy: Vector, drone_xy: Vector, safety_radius_cm: float = DEFAULT_TREE_SAFETY_RADIUS_CM) -> Vector:
    """Pick a point near the tree but outside the trunk/canopy safety radius."""
    dx = drone_xy.x - tree_xy.x
    dy = drone_xy.y - tree_xy.y
    distance = math.hypot(dx, dy)

    if distance < 1e-6:
        return Vector(tree_xy.x + safety_radius_cm, tree_xy.y)

    scale = safety_radius_cm / distance
    return Vector(tree_xy.x + dx * scale, tree_xy.y + dy * scale)


def send_drones_above_nearest_tree(
    comm,
    drones: Iterable,
    altitude_offset_cm: float = DEFAULT_ALTITUDE_OFFSET_CM,
    chunk_cm: float = DEFAULT_MOVE_CHUNK_CM,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    safety_radius_cm: float = DEFAULT_TREE_SAFETY_RADIUS_CM,
):
    drones = list(drones)
    if not drones:
        print('No drones available.')
        return False

    anchor = drones[0].position
    target = find_nearest_tree(comm, anchor)
    if target is None:
        print('No tree targets found in the current world.')
        return False

    print(f'Nearest tree: {target["name"]} at {target["position"]}')
    success = True
    for index, drone in enumerate(drones):
        effective_radius = max(safety_radius_cm + index * 120.0, target.get('radius_cm', DEFAULT_TREE_SAFETY_RADIUS_CM) + index * 120.0)
        target_xy = compute_safe_tree_hover_xy(
            tree_xy=target['position'],
            drone_xy=drone.position,
            safety_radius_cm=effective_radius,
        )
        target_z = max(
            drone.z + 120.0,
            target['z'] + target.get('height_cm', 150.0) + DEFAULT_TREE_TOP_CLEARANCE_CM,
        )
        print(
            f'{drone.name}: safe hover target at {target_xy} '
            f'(tree safety radius {effective_radius:.1f} cm, target_z={target_z:.1f} cm)'
        )
        moved = move_drone_toward_xy(
            drone,
            target_xy=target_xy,
            target_z=target_z,
            chunk_cm=chunk_cm,
            max_iterations=max_iterations,
        )
        success = success and moved
    return success
