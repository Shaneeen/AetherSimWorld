import json
import math
import os
import time
from pathlib import Path
from typing import Optional

import numpy as np
import requests

from simworld.agent.humanoid import Humanoid
from simworld.communicator.communicator import Communicator
from simworld.communicator.unrealcv import UnrealCV
from simworld.utils.vector import Vector

from scripts.humanoid.common import (
    IGNORED_OBJECT_PATTERNS,
    MASK_MIN_PIXELS,
    MAX_SURVEY_OPTIONS,
    NAVIGATION_SCAN_RADIUS,
    SURVEY_SWEEP_ANGLES,
    VISIBLE_FOV_DEG,
    debug_log,
    get_ollama_timeout_sec,
)
from scripts.humanoid.movement.humanoid_movement import get_humanoid_pose, navigate_to_coordinates

_last_survey_options = []
_last_survey_query = ''


def normalize_angle_deg(angle: float) -> float:
    return ((angle + 180.0) % 360.0) - 180.0

def load_asset_maps():
    data_dir = Path(__file__).resolve().parents[3] / 'data'
    desc_path = data_dir / 'description_map.json'
    assets_path = data_dir / 'ue_assets.json'
    desc = {}
    assets = {}
    try:
        with desc_path.open('r', encoding='utf-8') as f:
            desc = json.load(f)
    except Exception:
        pass
    try:
        with assets_path.open('r', encoding='utf-8') as f:
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
    if any(token in lowered for token in ('store_marker', 'store_target', 'visible_store')):
        return 'building'
    if any(token in lowered for token in ('office_marker', 'apartment_marker', 'tall_building_marker', 'building_marker')):
        return 'building'
    if any(token in lowered for token in ('comparisontree', 'tree_marker', 'tree_target')):
        return 'vegetation'
    if any(token in lowered for token in ('comparisontrash', 'trash_marker', 'trash_target')):
        return 'trash'
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
            if 'store_marker' in obj_name.lower() or 'visible_store' in obj_name.lower():
                short_label = 'store'
                description = 'Store marker'
            elif 'office_marker' in obj_name.lower():
                short_label = 'office'
                description = 'Office marker'
            elif 'apartment_marker' in obj_name.lower():
                short_label = 'building'
                description = 'Apartment marker'
            elif 'tall_building_marker' in obj_name.lower():
                short_label = 'building'
                description = 'Tall building marker'
            elif 'comparisontrash' in obj_name.lower():
                short_label = 'trash'
                description = 'Trash marker'
            elif 'comparisontree' in obj_name.lower():
                short_label = 'tree'
                description = 'Tree marker'
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


