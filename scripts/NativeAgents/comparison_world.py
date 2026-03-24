"""Deterministic world builder for humanoid comparison tests."""

from pathlib import Path
import json
import os

from simworld.communicator.communicator import Communicator
from simworld.config import Config


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


def write_comparison_world(cfg: Config) -> Path:
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
    world_json = write_comparison_world(cfg)
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
