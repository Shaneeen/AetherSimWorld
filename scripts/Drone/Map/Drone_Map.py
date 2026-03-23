"""World setup for drone scenarios."""
from pathlib import Path
import json
import math
import random

from simworld.config import Config
from simworld.citygen.city.city_generator import CityGenerator
from simworld.utils.data_exporter import DataExporter


class DroneMap:
    """Build and load the lightweight drone world using config/light.yaml."""

    def __init__(self, config_path: str = 'config/light.yaml'):
        self.config_path = config_path
        self.config = Config(config_path)

    def setup_world(self, comm):
        output_dir = Path(self.config['citygen.output_dir'])
        output_dir.mkdir(parents=True, exist_ok=True)

        print(f'Generating drone world into {output_dir}...')
        city = CityGenerator(self.config)
        city.generate()
        exporter = DataExporter(city)
        exporter.export_to_json(str(output_dir))

        world_json = Path(self.config['citygen.world_json'])
        self._apply_tree_layout(world_json)
        ue_asset_path = Path(self.config['citygen.ue_asset_path'])

        print(f'Loading drone world from {world_json}...')
        comm.clear_env(keep_roads=False)
        comm.generate_world(str(world_json), str(ue_asset_path), run_time=False)

    def clear_world(self, comm):
        comm.clear_env(keep_roads=False)

    def _apply_tree_layout(self, world_json: Path):
        data = json.loads(world_json.read_text(encoding='utf-8'))
        nodes = data.get('nodes', [])
        kept_nodes = [node for node in nodes if not node.get('instance_name', '').startswith('BP_Tree')]

        if not self.config.get('manual_scene.scattered_trees.enabled', False):
            data['nodes'] = kept_nodes
            world_json.write_text(json.dumps(data, indent=2), encoding='utf-8')
            return

        count = int(self.config.get('manual_scene.scattered_trees.count', 10))
        min_radius_cm = max(0.0, float(self.config.get('manual_scene.scattered_trees.min_radius_cm', 500)))
        max_radius_cm = max(min_radius_cm, float(self.config.get('manual_scene.scattered_trees.max_radius_cm', 1500)))
        tree_types = ['BP_Tree1_C', 'BP_Tree2_C', 'BP_Tree3_C', 'BP_Tree4_C', 'BP_Tree5_C', 'BP_Tree6_C']
        rng = random.Random(42)

        for index in range(max(0, count)):
            angle = rng.uniform(0.0, 2.0 * math.pi)
            radius = rng.uniform(min_radius_cm, max_radius_cm)
            x = round(math.cos(angle) * radius, 2)
            y = round(math.sin(angle) * radius, 2)
            kept_nodes.append(
                {
                    'id': f'DroneScatterTree_{index + 1}',
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
