"""Semantic world-object helpers for NativeAgents experiments."""

from pathlib import Path
import json
import math

from simworld.utils.vector import Vector

VISIBLE_FOV_DEG = 100.0
DEFAULT_SCAN_RADIUS_CM = 4000.0


def load_asset_maps():
    data_dir = Path(__file__).resolve().parents[2] / 'data'
    desc_path = data_dir / 'description_map.json'
    assets_path = data_dir / 'ue_assets.json'
    desc = {}
    assets = {}
    try:
        desc = json.loads(desc_path.read_text(encoding='utf-8'))
    except Exception:
        pass
    try:
        assets = json.loads(assets_path.read_text(encoding='utf-8'))
    except Exception:
        pass
    return desc, assets


def infer_category_for_object(obj_name: str, assets_map: dict) -> str:
    lowered = str(obj_name).lower()
    if any(token in lowered for token in ('store_marker', 'store_target', 'visible_store')):
        return 'store'
    if any(token in lowered for token in ('building_marker', 'office_marker', 'apartment_marker', 'tall_building_marker')):
        return 'building'
    if any(token in lowered for token in ('tree_marker', 'comparisontree', 'tree_target')):
        return 'tree'
    if any(token in lowered for token in ('trash_marker', 'comparisontrash', 'trash_target')):
        return 'trash'
    for key, value in assets_map.items():
        if key == 'colors':
            continue
        if key.lower() in lowered:
            category = str(value.get('color', '')).strip().lower()
            if category:
                return category
    if any(token in lowered for token in ('store', 'shop', 'market', 'kiosk')):
        return 'store'
    if any(token in lowered for token in ('building', 'office', 'tower', 'house')):
        return 'building'
    if any(token in lowered for token in ('tree', 'vegetation')):
        return 'tree'
    if any(token in lowered for token in ('trash', 'bin', 'garbage')):
        return 'trash'
    return ''


def object_description(obj_name: str, desc_map: dict, assets_map: dict) -> str:
    lowered = str(obj_name).lower()
    if 'store_marker' in lowered or 'visible_store' in lowered:
        return 'Store marker'
    if 'office_marker' in lowered:
        return 'Office marker'
    if 'apartment_marker' in lowered:
        return 'Apartment marker'
    if 'tall_building_marker' in lowered:
        return 'Tall building marker'
    if 'comparisontree' in lowered:
        return 'Tree marker'
    if 'comparisontrash' in lowered:
        return 'Trash marker'
    for key, value in desc_map.items():
        if key.lower() in lowered:
            return str(value)
    for key, value in assets_map.items():
        if key == 'colors':
            continue
        if key.lower() in lowered:
            return str(value.get('asset_path', key))
    return ''


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


def relative_angle(current_pos: Vector, yaw: float, target_pos: Vector) -> float:
    heading = math.degrees(math.atan2(target_pos.y - current_pos.y, target_pos.x - current_pos.x))
    return normalize_angle_deg(heading - yaw)


def scan_world_objects(comm, hum, radius: float = DEFAULT_SCAN_RADIUS_CM):
    desc_map, assets_map = load_asset_maps()
    current_pos, yaw = get_agent_pose(comm, hum)
    results = []
    try:
        objects = comm.unrealcv.get_objects()
    except Exception:
        return []

    for obj in objects:
        obj_name = str(obj)
        lowered = obj_name.lower()
        if any(pattern in lowered for pattern in ('gen_bp_humanoid_', 'gen_bp_uemanager', 'worldsettings', 'defaultpawn_', 'skylight_')):
            continue
        try:
            loc = comm.unrealcv.get_location(obj_name)
        except Exception:
            continue
        pos = Vector(float(loc[0]), float(loc[1]))
        distance = current_pos.distance(pos)
        if distance > radius:
            continue
        category = infer_category_for_object(obj_name, assets_map)
        description = object_description(obj_name, desc_map, assets_map)
        rel_angle = relative_angle(current_pos, yaw, pos)
        results.append(
            {
                'name': obj_name,
                'category': category,
                'description': description,
                'world_x': pos.x,
                'world_y': pos.y,
                'distance': distance,
                'relative_angle': rel_angle,
                'visible': abs(rel_angle) <= VISIBLE_FOV_DEG / 2.0,
            }
        )
    results.sort(key=lambda item: item['distance'])
    return results


def filter_semantic_candidates(results, query: str, visible_only: bool = False):
    terms = normalize_query_terms(query)
    candidates = []
    for item in results:
        if visible_only and not item.get('visible', False):
            continue
        blob = ' '.join(
            [
                str(item.get('name', '')),
                str(item.get('category', '')),
                str(item.get('description', '')),
            ]
        ).lower().replace('_', ' ').replace('-', ' ')
        score = sum(1 for term in terms if term in blob)
        if score > 0:
            enriched = dict(item)
            enriched['query_score'] = score
            candidates.append(enriched)
    candidates.sort(key=lambda item: (-item['query_score'], item['distance'], abs(item['relative_angle'])))
    return candidates


def normalize_query_terms(query: str):
    stop_words = {'go', 'to', 'nearest', 'closest', 'visible', 'find', 'the', 'a', 'an', 'please'}
    synonym_groups = {
        'store': {'store', 'shop', 'market', 'kiosk', 'building'},
        'building': {'building', 'office', 'house', 'tower', 'store', 'shop'},
        'tree': {'tree', 'vegetation'},
        'trash': {'trash', 'bin', 'garbage'},
    }
    terms = []
    for token in str(query).lower().replace('-', ' ').replace('_', ' ').split():
        cleaned = ''.join(ch for ch in token if ch.isalnum())
        if not cleaned or cleaned in stop_words:
            continue
        terms.append(cleaned)
    expanded = set()
    for term in terms:
        expanded.update(synonym_groups.get(term, {term}))
    return expanded or set(terms)


def resolve_semantic_target(comm, hum, query: str, visible_only: bool = False):
    results = scan_world_objects(comm, hum)
    candidates = filter_semantic_candidates(results, query, visible_only=visible_only)
    return candidates[0] if candidates else None, candidates


def summarize_candidates(candidates, limit: int = 8):
    if not candidates:
        return 'No matching nearby objects found.'
    lines = []
    for index, item in enumerate(candidates[:limit], start=1):
        visibility = 'visible' if item.get('visible') else 'not visible'
        lines.append(
            f'{index}. {item["name"]} | category={item.get("category", "") or "unknown"} | '
            f'distance={item["distance"]:.1f} cm | angle={item["relative_angle"]:.1f} deg | {visibility}'
        )
    return '\n'.join(lines)
