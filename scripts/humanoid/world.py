from pathlib import Path
import json
import math
import os
import random

from simworld.communicator.communicator import Communicator
from simworld.config import Config

def generate_lightweight_world(comm: Communicator, cfg: Config):
    """Generate and load a procedural world into the currently opened UE map."""
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
    """Apply deterministic scene tweaks after procedural export."""
    if cfg.get('manual_scene.scattered_trees.enabled', False):
        add_scattered_trees(
            world_json,
            count=int(cfg.get('manual_scene.scattered_trees.count', 10)),
            min_radius_cm=float(cfg.get('manual_scene.scattered_trees.min_radius_cm', 500)),
            max_radius_cm=float(cfg.get('manual_scene.scattered_trees.max_radius_cm', 1500)),
        )


def add_scattered_trees(world_json: Path, count: int, min_radius_cm: float, max_radius_cm: float):
    """Replace generated element clutter with a small scattered set of trees."""
    data = json.loads(world_json.read_text(encoding='utf-8'))
    nodes = data.get('nodes', [])

    # Keep roads/buildings from citygen and remove any previously generated tree/element clutter.
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
