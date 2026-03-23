"""Main entry point for drone-based SimWorld control."""
from pathlib import Path
import json
import os
import re
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.Drone.common import (
    maybe_launch_simworld,
    startup_log,
    wait_for_simworld_server,
    wait_for_user_world_ready,
)
from scripts.Drone.Map.Drone_Map import DroneMap
from scripts.Drone.Movement.Drone_Movement import send_drones_above_nearest_tree
from scripts.Drone.Robots.Drone_blue import DroneBlue
from scripts.Drone.Robots.Drone_red import DroneRed
from scripts.Drone.Vision.Drone_Vision import point_camera_at_drone

startup_log(f'Python executable: {sys.executable}')
startup_log(f'Working directory: {os.getcwd()}')
startup_log(f'Repo root: {REPO_ROOT}')

try:
    startup_log('Importing SimWorld modules...')
    from simworld.communicator.unrealcv import UnrealCV
    from simworld.communicator.communicator import Communicator
    from simworld.utils.vector import Vector
    startup_log('SimWorld imports succeeded.')
except Exception as e:
    startup_log(f'SimWorld import failed: {type(e).__name__}: {e}')
    raise

try:
    import airsim
except Exception:
    airsim = None


def check_airsim_connection():
    if airsim is None:
        return False, 'airsim package not importable'
    try:
        client = airsim.MultirotorClient()
        client.confirmConnection()
        return True, 'AirSim RPC connected'
    except Exception as e:
        return False, f'AirSim RPC unavailable: {e}'


def rule_parse(text: str):
    t = text.strip().lower()
    if t in ('quit', 'exit'):
        return ('quit',)
    if t in ('status',):
        return ('status',)
    if t in ('go above nearest tree', 'fly above nearest tree', 'hover above nearest tree'):
        return ('above_nearest_tree',)
    if t == 'takeoff':
        return ('takeoff',)
    if t == 'land':
        return ('land',)
    if t.startswith('hover'):
        m = re.match(r'hover(?:\s+(-?\d+\.?\d*))?', t)
        return ('hover', float(m.group(1)) if m and m.group(1) else 1.0)
    if t.startswith('up'):
        m = re.match(r'up\s+(-?\d+\.?\d*)', t)
        if m:
            return ('up', float(m.group(1)))
    if t.startswith('down'):
        m = re.match(r'down\s+(-?\d+\.?\d*)', t)
        if m:
            return ('down', float(m.group(1)))
    if t.startswith('orbit'):
        m = re.match(r'orbit\s*(\d+)?', t)
        return ('orbit', float(m.group(1)) if m and m.group(1) else 700.0)
    if t.startswith('goto') or t.startswith('fly to'):
        m = re.match(r'.*?(?:goto|fly to)\s+(-?\d+\.?\d*)[,\s]+(-?\d+\.?\d*)(?:[,\s]+(-?\d+\.?\d*))?', t)
        if m:
            z = float(m.group(3)) if m.group(3) else None
            return ('goto', float(m.group(1)), float(m.group(2)), z)
    if t.startswith('move'):
        m = re.match(r'move\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)(?:\s+(-?\d+\.?\d*))?', t)
        if m:
            dz = float(m.group(3)) if m.group(3) else 0.0
            return ('move', float(m.group(1)), float(m.group(2)), dz)
    if t in ('look', 'scan'):
        return ('look',)
    if t in ('view', 'show view', 'camera'):
        return ('view',)
    if t == 'help':
        return ('help',)
    return ('unknown', t)


def print_help():
    print('Commands:')
    print(' - go above nearest tree')
    print(' - takeoff')
    print(' - land')
    print(' - up 200')
    print(' - down 200')
    print(' - hover 2')
    print(' - orbit 700')
    print(' - goto 100 200 900')
    print(' - move 100 0 0')
    print(' - look')
    print(' - view')
    print(' - status')
    print(' - quit')


def get_actor_pose(comm: Communicator, actor_name: str):
    loc = comm.unrealcv.get_location(actor_name)
    ori = comm.unrealcv.get_orientation(actor_name)
    return Vector(loc[0], loc[1]), float(ori[1]) if len(ori) > 1 else 0.0, float(loc[2])


def look_around(comm: Communicator, drone):
    pos, yaw, z = get_actor_pose(comm, drone.name)
    print(f'{drone.name}: position={pos}, yaw={yaw:.1f}, z={z:.1f}')


def show_view(comm: Communicator, drone):
    try:
        point_camera_at_drone(comm, drone)
        img = comm.get_camera_observation(0, 'lit', mode='direct')
        comm.show_img(img)
    except Exception as e:
        print('View failed:', e)
        print('Note: drone view uses a follow camera, not a built-in onboard camera yet.')


def orbit_pair(drones, center: Vector, radius: float, duration: float = 3.0, speed: float = 0.5):
    start = time.time()
    while time.time() - start < duration:
        t = time.time() - start
        for index, drone in enumerate(drones):
            drone.orbit(center=center, radius=radius, angular_offset=index * 3.14159, t=t, speed=speed)
        time.sleep(0.15)


def main():
    launch_state = maybe_launch_simworld()
    if launch_state in ('launched', 'reused'):
        wait_for_user_world_ready()
    wait_for_simworld_server()
    print('Connecting to UnrealCV (localhost:9000)...')

    ucv = UnrealCV(port=9000, ip='127.0.0.1', resolution=(640, 480))
    comm = Communicator(ucv)
    drone_map = DroneMap('config/light.yaml')

    try:
        drone_map.clear_world(comm)
    except Exception:
        pass
    time.sleep(0.5)

    drone_map.setup_world(comm)

    airsim_ok, airsim_message = check_airsim_connection()
    print(airsim_message)

    blue = DroneBlue(comm, position=Vector(0, 0), z_height=900.0)
    red = DroneRed(comm, position=Vector(250, 0), z_height=900.0)
    blue.spawn()
    red.spawn()
    drones = [blue, red]

    print('Drone world ready.')
    print_help()

    try:
        while True:
            text = input('drone> ')
            cmd = rule_parse(text)

            if cmd[0] == 'quit':
                print('Exiting drone controller')
                break
            if cmd[0] == 'help':
                print_help()
                continue
            if cmd[0] == 'status':
                print('Status:')
                print(f' - AirSim connected: {airsim_ok}')
                for drone in drones:
                    pos, yaw, z = get_actor_pose(comm, drone.name)
                    print(f' - {drone.name}: pos={pos}, yaw={yaw:.1f}, z={z:.1f}')
                continue
            if cmd[0] == 'above_nearest_tree':
                send_drones_above_nearest_tree(comm, drones)
                continue
            if cmd[0] == 'takeoff':
                for drone in drones:
                    drone.takeoff()
                continue
            if cmd[0] == 'land':
                for drone in drones:
                    drone.land()
                continue
            if cmd[0] == 'hover':
                for drone in drones:
                    drone.hover(cmd[1])
                continue
            if cmd[0] == 'up':
                for drone in drones:
                    drone.move_up(cmd[1])
                continue
            if cmd[0] == 'down':
                for drone in drones:
                    drone.move_down(cmd[1])
                continue
            if cmd[0] == 'orbit':
                orbit_pair(drones, center=Vector(0, 0), radius=cmd[1])
                continue
            if cmd[0] == 'goto':
                _, x, y, z = cmd
                target_z = 900.0 if z is None else z
                for index, drone in enumerate(drones):
                    drone.move_to(x + index * 120, y + index * 120, target_z, duration=1.2)
                continue
            if cmd[0] == 'move':
                _, dx, dy, dz = cmd
                for drone in drones:
                    drone.move_to(drone.position.x + dx, drone.position.y + dy, drone.z + dz, duration=1.0)
                continue
            if cmd[0] == 'look':
                for drone in drones:
                    look_around(comm, drone)
                continue
            if cmd[0] == 'view':
                show_view(comm, blue)
                continue

            print('Unknown command')

    except KeyboardInterrupt:
        print('\nInterrupted by user')
    finally:
        try:
            if drone_map.config.get('manual_scene.clear_on_exit', True):
                print('Clearing drone world and returning to empty map...')
                drone_map.clear_world(comm)
        except Exception as e:
            print('Cleanup warning:', e)
        print('Disconnecting...')
        try:
            ucv.disconnect()
        except Exception:
            pass


if __name__ == '__main__':
    main()
