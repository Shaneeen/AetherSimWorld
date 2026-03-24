from pathlib import Path
import json
import math
import os

from simworld.utils.vector import Vector


def load_json_if_exists(path: Path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}


def load_metadata():
    data_dir = Path(__file__).resolve().parents[3] / 'data'
    desc_map = load_json_if_exists(data_dir / 'description_map.json')
    assets_map = load_json_if_exists(data_dir / 'ue_assets.json')
    bbox_map = load_json_if_exists(data_dir / 'bounding_boxes.json')
    return desc_map, assets_map, bbox_map


def current_world_json_path(cfg):
    fixed_world_json = os.environ.get('SIMWORLD_FIXED_WORLD_JSON')
    if fixed_world_json:
        return Path(fixed_world_json)
    world_path = cfg.get('citygen.world_json', None)
    return Path(world_path) if world_path else None


def load_world_nodes(cfg):
    world_path = current_world_json_path(cfg)
    if world_path is None or not world_path.exists():
        return {}
    data = load_json_if_exists(world_path)
    return {str(node.get('id')): node for node in data.get('nodes', [])}


def infer_category(name: str, assets_map: dict):
    lowered = str(name).lower()
    if any(token in lowered for token in ('store', 'shop', 'market', 'visible_store')):
        return 'store'
    if any(token in lowered for token in ('building', 'office', 'apartment', 'tower')):
        return 'building'
    if any(token in lowered for token in ('tree', 'vegetation')):
        return 'tree'
    if any(token in lowered for token in ('trash', 'bin', 'garbage')):
        return 'trash'
    for key, value in assets_map.items():
        if key == 'colors':
            continue
        if key.lower() in lowered:
            color = str(value.get('color', '')).strip().lower()
            if color == 'building':
                return 'building'
            if color == 'vegetation':
                return 'tree'
            if color == 'trash':
                return 'trash'
    return ''


def describe_object(name: str, desc_map: dict, assets_map: dict):
    lowered = str(name).lower()
    for key, value in desc_map.items():
        if key.lower() in lowered:
            return str(value)
    if 'store' in lowered:
        return 'Store target'
    if 'office' in lowered:
        return 'Office target'
    if 'apartment' in lowered:
        return 'Apartment target'
    if 'building' in lowered:
        return 'Building target'
    if 'tree' in lowered:
        return 'Tree target'
    if 'trash' in lowered:
        return 'Trash target'
    for key, value in assets_map.items():
        if key == 'colors':
            continue
        if key.lower() in lowered:
            return str(value.get('asset_path', key))
    return ''


def estimated_radius_cm(obj_name: str, instance_name: str, world_nodes: dict, bbox_map: dict):
    lowered = str(obj_name).lower()
    if any(token in lowered for token in ('store_marker', 'visible_store', 'comparisontrash')):
        return 120.0
    if any(token in lowered for token in ('office_marker', 'apartment_marker')):
        return 180.0
    if any(token in lowered for token in ('tall_building_marker',)):
        return 220.0
    if any(token in lowered for token in ('comparisontree',)):
        return 120.0

    node = world_nodes.get(obj_name) or {}
    instance_name = instance_name or str(node.get('instance_name', ''))
    scale = node.get('properties', {}).get('scale', {'x': 1.0, 'y': 1.0})
    sx = float(scale.get('x', 1.0))
    sy = float(scale.get('y', 1.0))

    for section in ('buildings', 'elements'):
        section_map = bbox_map.get(section, {})
        if instance_name in section_map:
            bbox = section_map[instance_name].get('bbox', {})
            x = float(bbox.get('x', 100.0)) * sx
            y = float(bbox.get('y', 100.0)) * sy
            return max(80.0, 0.5 * math.hypot(x, y))
    return 150.0


def get_agent_pose(comm, hum):
    try:
        info = comm.get_position_and_direction(humanoid_ids=[hum.id])
        pos_dir = info.get(('humanoid', hum.id))
        if pos_dir:
            pos, yaw = pos_dir
            return pos, float(yaw)
    except Exception:
        pass
    name = comm.get_humanoid_name(hum.id)
    loc = comm.unrealcv.get_location(name)
    ori = comm.unrealcv.get_orientation(name)
    return Vector(loc[0], loc[1]), float(ori[1]) if len(ori) > 1 else 0.0


def normalize_angle_deg(angle: float) -> float:
    return ((angle + 180.0) % 360.0) - 180.0


def relative_angle(current_pos: Vector, yaw: float, target_pos: Vector):
    heading = math.degrees(math.atan2(target_pos.y - current_pos.y, target_pos.x - current_pos.x))
    return normalize_angle_deg(heading - yaw)


def scan_world(comm, hum, cfg, radius: float = 6000.0):
    desc_map, assets_map, bbox_map = load_metadata()
    world_nodes = load_world_nodes(cfg)
    pos, yaw = get_agent_pose(comm, hum)
    results = []
    for obj in comm.unrealcv.get_objects():
        name = str(obj)
        lowered = name.lower()
        if any(skip in lowered for skip in ('gen_bp_humanoid_', 'gen_bp_uemanager', 'worldsettings', 'defaultpawn_', 'skylight_')):
            continue
        try:
            loc = comm.unrealcv.get_location(name)
        except Exception:
            continue
        target = Vector(float(loc[0]), float(loc[1]))
        distance = pos.distance(target)
        if distance > radius:
            continue
        node = world_nodes.get(name, {})
        instance_name = str(node.get('instance_name', ''))
        category = infer_category(name, assets_map)
        description = describe_object(name, desc_map, assets_map)
        results.append(
            {
                'name': name,
                'instance_name': instance_name,
                'category': category,
                'description': description,
                'world_x': target.x,
                'world_y': target.y,
                'distance': distance,
                'relative_angle': relative_angle(pos, yaw, target),
                'radius_cm': estimated_radius_cm(name, instance_name, world_nodes, bbox_map),
            }
        )
    results.sort(key=lambda item: item['distance'])
    return results


def filter_candidates(results, query: str, visible_only: bool = False):
    terms = normalize_terms(query)
    out = []
    for item in results:
        if visible_only and abs(item['relative_angle']) > 45.0:
            continue
        blob = ' '.join([item['name'], item['category'], item['description']]).lower().replace('_', ' ')
        score = sum(1 for term in terms if term in blob)
        if score > 0:
            enriched = dict(item)
            enriched['query_score'] = score
            out.append(enriched)
    out.sort(key=lambda item: (-item['query_score'], item['distance'], abs(item['relative_angle'])))
    return out


def candidate_key(item):
    return (
        str(item.get('category', '')).lower(),
        round(float(item.get('world_x', 0.0)), 1),
        round(float(item.get('world_y', 0.0)), 1),
    )


def dedupe_candidates(candidates):
    deduped = []
    seen = set()
    for item in candidates:
        key = candidate_key(item)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def selection_from_query(query: str):
    lowered = str(query).lower()
    if any(token in lowered for token in ('furthest', 'farthest', 'furtherest', 'furthermost')):
        return 'farthest'
    if any(token in lowered for token in ('another', 'different', 'other')):
        return 'different'
    return 'nearest'


def normalize_terms(query: str):
    stop = {'go', 'to', 'the', 'nearest', 'closest', 'visible', 'find', 'a', 'an'}
    synonyms = {
        'store': {'store', 'shop', 'market'},
        'building': {'building', 'office', 'apartment', 'tower'},
        'tree': {'tree', 'vegetation'},
        'trash': {'trash', 'bin', 'garbage'},
    }
    tokens = []
    for raw in str(query).lower().replace('-', ' ').replace('_', ' ').split():
        cleaned = ''.join(ch for ch in raw if ch.isalnum())
        if cleaned and cleaned not in stop:
            tokens.append(cleaned)
    expanded = set()
    for token in tokens:
        expanded.update(synonyms.get(token, {token}))
    return expanded or set(tokens)


def resolve_target(comm, hum, cfg, query: str, visible_only: bool = False, selector: str | None = None, exclude_key=None):
    results = scan_world(comm, hum, cfg)
    candidates = dedupe_candidates(filter_candidates(results, query, visible_only=visible_only))
    selector = str(selector or selection_from_query(query)).lower()
    filtered = candidates
    if isinstance(exclude_key, (list, tuple, set)):
        excluded = set(exclude_key)
    elif exclude_key is None:
        excluded = set()
    else:
        excluded = {exclude_key}
    if excluded and selector in ('another', 'different'):
        filtered = [item for item in candidates if candidate_key(item) not in excluded]
    if not filtered:
        return None, candidates
    if selector in ('farthest', 'furthest'):
        return filtered[-1], candidates
    return filtered[0], candidates
