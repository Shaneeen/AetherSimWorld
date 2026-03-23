"""Secondary drone robot definition."""
from scripts.Drone.Robots.Drone_blue import DroneBlue


class DroneRed(DroneBlue):
    """Red variant of the drone robot."""

    def __init__(self, comm, model_path: str = None, position=None, z_height: float = 700.0):
        super().__init__(
            comm=comm,
            model_path=model_path or '/Game/CityDatabase/blueprints/BP_Box2.BP_Box2_C',
            position=position,
            z_height=z_height,
            color=(255, 0, 0),
            scale=(0.7, 0.7, 0.18),
        )
