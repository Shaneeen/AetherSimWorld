"""Primary drone robot definition."""
import math
import time

from simworld.utils.vector import Vector


class DroneBlue:
    _id_counter = 0

    def __init__(
        self,
        comm,
        model_path: str = None,
        position: Vector = None,
        z_height: float = 700.0,
        color=(0, 0, 255),
        scale=(0.7, 0.7, 0.18),
    ):
        self.id = DroneBlue._id_counter
        DroneBlue._id_counter += 1
        self.comm = comm
        self.name = f'GEN_BP_DroneBlue_{self.id}'
        self.position = position or Vector(0, 0)
        self.z = z_height
        self.home_z = z_height
        self.model_path = model_path or '/Game/CityDatabase/blueprints/BP_Box3.BP_Box3_C'
        self.color = color
        self.scale = scale

    def spawn(self):
        self.comm.unrealcv.spawn_bp_asset(self.model_path, self.name)
        self.comm.unrealcv.set_location((self.position.x, self.position.y, self.z), self.name)
        self.comm.unrealcv.set_scale(self.scale, self.name)
        self.comm.unrealcv.set_color(self.name, list(self.color))
        self.comm.unrealcv.set_movable(self.name, True)

    def set_location(self, x: float, y: float, z: float = None):
        z = self.z if z is None else z
        self.comm.unrealcv.set_location((x, y, z), self.name)
        self.position = Vector(x, y)
        self.z = z

    def move_to(self, x: float, y: float, z: float = None, duration: float = 1.0, steps: int = 10):
        z = self.z if z is None else z
        start = self.position
        start_z = self.z
        steps = max(1, steps)
        dx = (x - start.x) / steps
        dy = (y - start.y) / steps
        dz = (z - start_z) / steps
        for i in range(1, steps + 1):
            self.set_location(start.x + dx * i, start.y + dy * i, start_z + dz * i)
            time.sleep(duration / steps)

    def move_by(self, dx: float, dy: float, dz: float = 0.0, duration: float = 1.0, steps: int = 10):
        self.move_to(self.position.x + dx, self.position.y + dy, self.z + dz, duration=duration, steps=steps)

    def move_up(self, amount_cm: float, duration: float = 1.0):
        self.move_to(self.position.x, self.position.y, self.z + max(0.0, amount_cm), duration=duration)

    def move_down(self, amount_cm: float, duration: float = 1.0, min_z: float = 80.0):
        target_z = max(min_z, self.z - max(0.0, amount_cm))
        self.move_to(self.position.x, self.position.y, target_z, duration=duration)

    def takeoff(self, target_z: float = 900.0, duration: float = 1.5):
        target_z = max(target_z, self.home_z)
        self.move_to(self.position.x, self.position.y, target_z, duration=duration)

    def land(self, target_z: float = 80.0, duration: float = 1.5):
        self.move_to(self.position.x, self.position.y, max(20.0, target_z), duration=duration)

    def hover(self, duration: float = 1.0):
        time.sleep(max(0.0, duration))

    def orbit(self, center: Vector, radius: float, angular_offset: float, t: float, speed: float = 0.5):
        angle = angular_offset + speed * t
        x = center.x + math.cos(angle) * radius
        y = center.y + math.sin(angle) * radius
        self.set_location(x, y, self.z)
