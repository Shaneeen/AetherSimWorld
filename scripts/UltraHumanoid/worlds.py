from pathlib import Path
import json
import math
import os
import random

from simworld.communicator.communicator import Communicator
from simworld.config import Config


def cleanup_ultra_humanoid_actors(comm: Communicator):
    try:
        objects = [str(obj) for obj in comm.unrealcv.get_objects()]
    except Exception as exc:
        print(f'Startup cleanup skipped: {exc}')
        return

    targets = []
    for obj_name in objects:
        lowered = obj_name.lower()
        if lowered.startswith('gen_bp_humanoid_') or lowered == 'gen_bp_uemanager':
            targets.append(obj_name)

    if not targets:
        print('No previous humanoids or helper actors found.')
        return

    print(f'Cleaning {len(targets)} previously spawned humanoid/helper actors...')
    for obj_name in targets:
        try:
            comm.unrealcv.destroy(obj_name)
        except Exception as exc:
            print(f'Could not destroy {obj_name}: {exc}')

    try:
        comm.unrealcv.clean_garbage()
    except Exception:
        pass


def generate_lightweight_world(comm: Communicator, cfg: Config):
    fixed_world_json = os.environ.get('SIMWORLD_FIXED_WORLD_JSON')
    if fixed_world_json:
        world_json = Path(fixed_world_json)
        ue_asset_path = Path(cfg['citygen.ue_asset_path'])
        if not world_json.exists():
            raise FileNotFoundError(f'Fixed world file not found: {world_json}')
        if not ue_asset_path.exists():
            raise FileNotFoundError(f'UE asset library not found: {ue_asset_path}')

        print(f'Loading fixed world from {world_json}...')
        comm.clear_env(keep_roads=False)
        comm.generate_world(str(world_json), str(ue_asset_path), run_time=False)
        return

    output_dir = Path(cfg['citygen.output_dir'])
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f'Generating procedural city into {output_dir}...')
    from simworld.citygen.city.city_generator import CityGenerator
    from simworld.utils.data_exporter import DataExporter

    city = CityGenerator(cfg)
    city.generate()
    exporter = DataExporter(city)
    exporter.export_to_json(str(output_dir))
    apply_manual_scene_overrides(Path(cfg['citygen.world_json']), cfg)

    world_json = Path(cfg['citygen.world_json'])
    ue_asset_path = Path(cfg['citygen.ue_asset_path'])
    if not world_json.exists():
        raise FileNotFoundError(f'Generated world file not found: {world_json}')
    if not ue_asset_path.exists():
        raise FileNotFoundError(f'UE asset library not found: {ue_asset_path}')

    print(f'Loading generated world from {world_json}...')
    comm.clear_env(keep_roads=False)
    comm.generate_world(str(world_json), str(ue_asset_path), run_time=False)


def apply_manual_scene_overrides(world_json: Path, cfg: Config):
    if cfg.get('manual_scene.scattered_trees.enabled', False):
        add_scattered_trees(
            world_json,
            count=int(cfg.get('manual_scene.scattered_trees.count', 10)),
            min_radius_cm=float(cfg.get('manual_scene.scattered_trees.min_radius_cm', 500)),
            max_radius_cm=float(cfg.get('manual_scene.scattered_trees.max_radius_cm', 1500)),
        )


def add_scattered_trees(world_json: Path, count: int, min_radius_cm: float, max_radius_cm: float):
    data = json.loads(world_json.read_text(encoding='utf-8'))
    nodes = data.get('nodes', [])

    kept_nodes = [node for node in nodes if not node.get('instance_name', '').startswith('BP_Tree')]

    tree_types = ['BP_Tree1_C', 'BP_Tree2_C', 'BP_Tree3_C', 'BP_Tree4_C', 'BP_Tree5_C', 'BP_Tree6_C']
    rng = random.Random(42)
    min_radius_cm = max(0.0, float(min_radius_cm))
    max_radius_cm = max(min_radius_cm, float(max_radius_cm))

    for index in range(max(0, count)):
        angle = rng.uniform(0.0, 2.0 * math.pi)
        radius = rng.uniform(min_radius_cm, max_radius_cm)
        x = round(math.cos(angle) * radius, 2)
        y = round(math.sin(angle) * radius, 2)
        kept_nodes.append(
            {
                'id': f'ScatterTree_{index + 1}',
                'instance_name': tree_types[index % len(tree_types)],
                'properties': {
                    'location': {'x': x, 'y': y, 'z': 20},
                    'orientation': {'pitch': 0, 'yaw': rng.randint(0, 359), 'roll': 0},
                    'scale': {'x': 1.0, 'y': 1.0, 'z': 1.0},
                },
            }
        )

    data['nodes'] = kept_nodes
    world_json.write_text(json.dumps(data, indent=2), encoding='utf-8')


def _node(node_id: str, instance_name: str, x: float, y: float, z: float = 20.0, yaw: float = 0.0, scale=(1.0, 1.0, 1.0)):
    return {
        'id': node_id,
        'instance_name': instance_name,
        'properties': {
            'location': {'x': x, 'y': y, 'z': z},
            'orientation': {'pitch': 0, 'yaw': yaw, 'roll': 0},
            'scale': {'x': scale[0], 'y': scale[1], 'z': scale[2]},
        },
    }


MARKER_COLORS = {
    'Visible_Store_Marker_1': (255, 105, 180),
    'Store_Marker_2': (255, 105, 180),
    'Office_Marker_1': (65, 105, 225),
    'Apartment_Marker_1': (70, 130, 180),
    'Tall_Building_Marker_1': (30, 144, 255),
    'ComparisonTree_1': (34, 139, 34),
    'ComparisonTree_2': (34, 139, 34),
    'ComparisonTrash_1': (128, 128, 128),
}


def write_comparison_world() -> Path:
    output_dir = Path('output/comparison_world')
    output_dir.mkdir(parents=True, exist_ok=True)
    world_json = output_dir / 'comparison_world.json'

    nodes = [
        _node('Road_East_1', 'BP_Road1_C', 11000.0, 0.0, z=0.0, yaw=0.0, scale=(1.045, 0.9, 1.0)),
        _node('Road_West_1', 'BP_Road1_C', -11000.0, 0.0, z=0.0, yaw=180.0, scale=(1.045, 0.9, 1.0)),
        _node('Road_North_1', 'BP_Road1_C', 0.0, 11000.0, z=0.0, yaw=90.0, scale=(1.045, 0.9, 1.0)),
        _node('Road_South_1', 'BP_Road1_C', 0.0, -11000.0, z=0.0, yaw=270.0, scale=(1.045, 0.9, 1.0)),
        _node('Visible_Store_Marker_1', 'BP_Box_C', 1600.0, 0.0, z=40.0, scale=(0.5, 0.5, 0.5)),
        _node('Store_Marker_2', 'BP_Box_C', 2800.0, 1800.0, z=40.0, scale=(0.5, 0.5, 0.5)),
        _node('Office_Marker_1', 'BP_Box2_C', -2800.0, 1800.0, z=40.0, scale=(0.6, 0.4, 0.8)),
        _node('Apartment_Marker_1', 'BP_Box2_C', 3200.0, -2400.0, z=40.0, scale=(0.6, 0.4, 0.8)),
        _node('Tall_Building_Marker_1', 'BP_Box3_C', -3600.0, -2800.0, z=40.0, scale=(0.6, 0.4, 1.2)),
        _node('ComparisonTree_1', 'BP_Box3_C', 1800.0, -1800.0, z=40.0, scale=(0.3, 0.3, 0.9)),
        _node('ComparisonTree_2', 'BP_Box3_C', -1800.0, 1800.0, z=40.0, scale=(0.3, 0.3, 0.9)),
        _node('ComparisonTrash_1', 'BP_Box_C', 1800.0, 2200.0, z=40.0, scale=(0.25, 0.25, 0.35)),
    ]

    data = {
        'base_map': {
            'name': 'comparison_map',
            'env_bin': 'gym_citynav\\Binaries\\Win64\\gym_citynav.exe',
            'width': 1000,
            'height': 1000,
        },
        'nodes': nodes,
    }
    world_json.write_text(json.dumps(data, indent=2), encoding='utf-8')
    return world_json


def load_comparison_world(comm: Communicator, cfg: Config) -> Path:
    world_json = write_comparison_world()
    ue_asset_path = Path(cfg['citygen.ue_asset_path'])
    if not ue_asset_path.exists():
        raise FileNotFoundError(f'UE asset library not found: {ue_asset_path}')
    print(f'Loading deterministic comparison world from {world_json}...')
    comm.clear_env(keep_roads=False)
    comm.generate_world(str(world_json), str(ue_asset_path), run_time=False)
    for actor_name, color in MARKER_COLORS.items():
        try:
            comm.unrealcv.set_color(actor_name, list(color))
        except Exception:
            pass
    return world_json
