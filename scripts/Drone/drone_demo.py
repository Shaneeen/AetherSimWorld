"""Drone demo and manager for SimWorld.

This script demonstrates spawning simple drone actors (using a generic blueprint)
and controlling them (move-to, orbit). It also shows a basic interaction with a
`Humanoid` agent so you can test multi-agent behaviour.

Usage:
  python scripts/drone_demo.py [num_drones]

While running, type `add N` to spawn N more drones, or `quit` to exit.
"""
import math
import time
import sys
import os
import re
import json
import requests

from simworld.communicator.unrealcv import UnrealCV
from simworld.communicator.communicator import Communicator
from simworld.agent.humanoid import Humanoid
from simworld.utils.vector import Vector
from simworld.config import Config


class Drone:
    _id_counter = 0

    def __init__(self, comm: Communicator, model_path: str = None, position: Vector = None, z_height: float = 600.0):
        self.id = Drone._id_counter
        Drone._id_counter += 1
        self.comm = comm
        self.name = f'GEN_BP_Drone_{self.id}'
        self.model = model_path
        self.z = z_height
        self.position = position or Vector(0, 0)

    def spawn(self):
        # fallback model: use BP_Box if not provided
        model = self.model or '/Game/CityDatabase/blueprints/BP_Box.BP_Box_C'
        try:
            self.comm.unrealcv.spawn_bp_asset(model, self.name)
            self.comm.unrealcv.set_location((self.position.x, self.position.y, self.z), self.name)
            self.comm.unrealcv.set_scale((1, 1, 1), self.name)
            self.comm.unrealcv.set_movable(self.name, True)
        except Exception as e:
            print('Failed to spawn drone', e)

    def set_location(self, x: float, y: float, z: float = None):
        z = z if z is not None else self.z
        try:
            self.comm.unrealcv.set_location((x, y, z), self.name)
            self.position = Vector(x, y)
            self.z = z
        except Exception as e:
            print('Failed set_location for', self.name, e)

    def move_to(self, x: float, y: float, z: float = None, duration: float = 1.0, steps: int = 10):
        z = z if z is not None else self.z
        try:
            start = self.position
            dx = (x - start.x) / steps
            dy = (y - start.y) / steps
            dz = (z - self.z) / steps
            for i in range(1, steps + 1):
                nx = start.x + dx * i
                ny = start.y + dy * i
                nz = self.z + dz * i
                self.comm.unrealcv.set_location((nx, ny, nz), self.name)
                time.sleep(duration / steps)
            self.position = Vector(x, y)
            self.z = z
        except Exception as e:
            print('move_to failed for', self.name, e)


class DroneManager:
    def __init__(self, comm: Communicator, model_path: str = None, default_z: float = 600.0):
        self.comm = comm
        self.model_path = model_path
        self.default_z = default_z
        self.drones = []

    def spawn_drones(self, n: int, center: Vector = Vector(0, 0), radius: float = 400.0):
        created = []
        for i in range(n):
            angle = (len(self.drones) + i) * (2 * math.pi / max(1, n))
            px = center.x + math.cos(angle) * radius
            py = center.y + math.sin(angle) * radius
            d = Drone(self.comm, model_path=self.model_path, position=Vector(px, py), z_height=self.default_z)
            d.spawn()
            self.drones.append(d)
            created.append(d)
        return created

    def orbit_center(self, center: Vector, radius: float = 400.0, speed: float = 0.5, duration: float = 10.0):
        """Make all drones orbit around center for duration (seconds).

        speed: radians per second for orbital motion.
        """
        t0 = time.time()
        while time.time() - t0 < duration:
            t = time.time() - t0
            for idx, d in enumerate(self.drones):
                phase = (2 * math.pi * idx) / max(1, len(self.drones))
                angle = phase + speed * t
                x = center.x + math.cos(angle) * radius
                y = center.y + math.sin(angle) * radius
                d.set_location(x, y)
            time.sleep(0.15)

    def follow_center(self, center: Vector = None, humanoid_id: int = None, yaw: float = 0.0, distance: float = 300.0, spacing: float = 200.0, height: float = None, duration: float = 5.0, speed: float = 1.0):
        """Arrange drones in a trailing formation behind `center` or a humanoid actor.

        If `humanoid_id` is provided, the manager will query the communicator each
        loop to obtain the latest humanoid position and heading so drones truly follow.
        """
        if height is None:
            height = self.default_z
        t0 = time.time()
        while time.time() - t0 < duration:
            # update center and yaw if following a humanoid
            if humanoid_id is not None:
                try:
                    info = self.comm.get_position_and_direction(humanoid_ids=[humanoid_id])
                    pd = info.get(('humanoid', humanoid_id))
                    if pd:
                        center, yaw = pd
                    else:
                        # fallback to direct query from UnrealCV
                        name = self.comm.get_humanoid_name(humanoid_id)
                        loc = self.comm.unrealcv.get_location(name)
                        ori = self.comm.unrealcv.get_orientation(name)
                        center = Vector(loc[0], loc[1])
                        yaw = float(ori[1]) if len(ori) > 1 else yaw
                except Exception:
                    # keep previous center/yaw on error
                    pass

            # compute heading vector
            dx = math.cos(math.radians(yaw))
            dy = math.sin(math.radians(yaw))
            for idx, d in enumerate(self.drones):
                offset = distance + idx * spacing
                tx = center.x - dx * offset
                ty = center.y - dy * offset
                # small lateral offset so drones don't collide exactly
                lateral = ((idx % 2) * 2 - 1) * min(50, spacing * 0.2)
                # lateral vector perpendicular to heading
                lx = -dy
                ly = dx
                tx += lx * lateral
                ty += ly * lateral
                d.set_location(tx, ty, height)
            time.sleep(max(0.05, 0.2 / max(1.0, speed)))


def main():
    num = 2
    if len(sys.argv) > 1:
        try:
            num = int(sys.argv[1])
        except Exception:
            pass

    print('Connecting to UnrealCV...')
    ucv = UnrealCV(port=9000, ip='127.0.0.1', resolution=(640, 480))
    comm = Communicator(ucv)

    # spawn UE manager if config has path (best-effort)
    # Ollama toggle
    use_ollama = os.environ.get('USE_OLLAMA', '0') == '1'
    ollama_model = os.environ.get('OLLAMA_MODEL', None)

    def ollama_parse_drone_command(text: str, model: str):
        url = os.environ.get('OLLAMA_API_URL', 'http://localhost:11434/api/generate')
        system = (
            "You are a drone command parser. Given a natural language instruction, respond with ONLY a JSON object describing the command."
            " Allowed commands: add {count}, follow, unfollow, move {dx} {dy}, orbit {radius}, goto {x} {y} (absolute coords), quit."
        )
        prompt = "System:\n" + system + "\n\nUser:\n" + text + "\n\nRespond with JSON only. Examples: {\"action\": \"add\", \"count\": 2}, {\"action\": \"follow\"}, {\"action\": \"move\", \"dx\": 10, \"dy\": 0}."
        payload = {"model": model, "prompt": prompt, "max_tokens": 256}
        try:
            resp = requests.post(url, json=payload, timeout=8)
            resp.raise_for_status()
            out = resp.text
            m = re.search(r'\{.*\}', out, re.S)
            if not m:
                return None
            obj = json.loads(m.group(0))
            return obj
        except Exception:
            return None

    def rule_parse(text: str):
        t = text.strip().lower()
        if t.startswith('add'):
            m = re.match(r'add\s+(\d+)', t)
            return ('add', int(m.group(1)) if m else 1)
        if t in ('follow', 'follow me'):
            return ('follow',)
        if t in ('unfollow', 'stop following'):
            return ('unfollow',)
        if t.startswith('move'):
            m = re.match(r'move\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)', t)
            if m:
                return ('move', float(m.group(1)), float(m.group(2)))
        if t.startswith('orbit'):
            m = re.match(r'orbit\s*(\d+)?', t)
            return ('orbit', float(m.group(1)) if m and m.group(1) else 500.0)
        if t.startswith('goto') or t.startswith('fly to'):
            m = re.match(r'.*?(?:goto|fly to)\s+(-?\d+\.?\d*)[,\s]+(-?\d+\.?\d*)', t)
            if m:
                return ('goto', float(m.group(1)), float(m.group(2)))
        if t in ('quit', 'exit'):
            return ('quit',)
        return ('unknown', t)

    try:
        cfg = Config()
        ue_manager_path = cfg.get('simworld.ue_manager_path', None)
        if ue_manager_path:
            comm.spawn_ue_manager(ue_manager_path)
            time.sleep(0.5)
            try:
                comm.update_objects()
            except Exception:
                pass
    except Exception:
        pass

    # spawn humanoid
    hum = Humanoid(Vector(0, 0), Vector(1, 0), communicator=comm)
    comm.spawn_agent(hum, name=None)
    print('Spawned humanoid id=', hum.id)

    dm = DroneManager(comm, model_path=None, default_z=700.0)
    dm.spawn_drones(num, center=hum.position, radius=500.0)
    print(f'Spawned {num} drones. Type "add N" to add more, or "quit" to stop.')

    try:
        # run a background orbit / follow loop in a simple loop while reading user input
        running = True
        follow_mode = False
        print('Commands: add N | move dx dy | follow | unfollow | quit')
        while running:
            if follow_mode:
                # get humanoid pose
                try:
                    info = comm.get_position_and_direction(humanoid_ids=[hum.id])
                    pd = info.get(('humanoid', hum.id))
                    if pd:
                        pos, yaw = pd
                        dm.follow_center(center=pos, yaw=yaw, distance=300.0, spacing=200.0, duration=3.0, speed=1.2)
                    else:
                        # fallback to direct query
                        name = comm.get_humanoid_name(hum.id)
                        loc = ucv.get_location(name)
                        ori = ucv.get_orientation(name)
                        pos = Vector(loc[0], loc[1])
                        yaw = float(ori[1]) if len(ori) > 1 else 0.0
                        dm.follow_center(center=pos, yaw=yaw, distance=300.0, spacing=200.0, duration=3.0, speed=1.2)
                except Exception:
                    # if anything goes wrong, do a short idle orbit instead
                    dm.orbit_center(center=hum.position, radius=500.0, speed=0.8, duration=3.0)
            else:
                dm.orbit_center(center=hum.position, radius=500.0, speed=0.8, duration=3.0)

                # prompt for command after a short active period
            print('> ', end='', flush=True)
            cmd = sys.stdin.readline().strip()
            if not cmd:
                continue
            parsed = None
            if use_ollama and ollama_model:
                obj = ollama_parse_drone_command(cmd, ollama_model)
                if obj and 'action' in obj:
                    a = obj['action']
                    if a == 'add':
                        parsed = ('add', int(obj.get('count', 1)))
                    elif a == 'follow':
                        parsed = ('follow',)
                    elif a == 'unfollow':
                        parsed = ('unfollow',)
                    elif a == 'move':
                        parsed = ('move', float(obj.get('dx', 0.0)), float(obj.get('dy', 0.0)))
                    elif a == 'orbit':
                        parsed = ('orbit', float(obj.get('radius', 500.0)))
                    elif a == 'goto':
                        parsed = ('goto', float(obj.get('x', 0.0)), float(obj.get('y', 0.0)))
                    elif a in ('quit', 'exit'):
                        parsed = ('quit',)
                else:
                    parsed = rule_parse(cmd)
            else:
                parsed = rule_parse(cmd)

            if parsed[0] == 'add':
                n = parsed[1]
                dm.spawn_drones(n, center=hum.position, radius=500.0)
                print(f'Added {n} drones (total {len(dm.drones)})')
            elif parsed[0] == 'quit':
                running = False
            elif parsed[0] == 'move':
                try:
                    dx = parsed[1]; dy = parsed[2]
                    for d in dm.drones:
                        d.move_to(d.position.x + dx, d.position.y + dy, duration=0.8)
                    print('Moved drones by', dx, dy)
                except Exception as e:
                    print('Invalid move args', e)
            elif parsed[0] == 'follow':
                follow_mode = True
                print('Follow mode ON: drones will follow the humanoid')
            elif parsed[0] == 'unfollow':
                follow_mode = False
                print('Follow mode OFF: resuming orbit')
            elif parsed[0] == 'orbit':
                try:
                    radius = parsed[1]
                    dm.orbit_center(center=hum.position, radius=radius, speed=0.8, duration=3.0)
                except Exception:
                    print('Invalid orbit args')
            elif parsed[0] == 'goto':
                try:
                    x = parsed[1]; y = parsed[2]
                    # send all drones to this absolute position (spread slightly)
                    for i, d in enumerate(dm.drones):
                        d.move_to(x + i * 20, y + i * 20, duration=1.2)
                    print('Sent drones to', x, y)
                except Exception:
                    print('Invalid goto args')
            else:
                print('Unknown or unrecognized command')

            # status command
            if cmd.strip().lower() == 'status':
                print('Status:')
                print(' - drones:', len(dm.drones))
                print(' - follow_mode:', follow_mode)
                print(' - drone parsing (Ollama):', use_ollama and bool(ollama_model))

    finally:
        print('Cleaning up: disconnecting')
        try:
            ucv.disconnect()
        except Exception:
            pass


if __name__ == '__main__':
    main()
