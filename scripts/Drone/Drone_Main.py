"""Main entry point for drone-based SimWorld control."""
from pathlib import Path
import os
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.Drone.common import (
    debug_enabled,
    debug_log,
    maybe_launch_simworld,
    ollama_parse_drone_command,
    parse_local_drone_command,
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

    blue = DroneBlue(comm, position=Vector(0, 0), z_height=900.0)
    red = DroneRed(comm, position=Vector(250, 0), z_height=900.0)
    blue.spawn()
    red.spawn()
    drones = [blue, red]

    print('Drone world ready.')
    print_help()
    use_ollama = os.environ.get('USE_OLLAMA', '1') != '0'
    ollama_model = os.environ.get('OLLAMA_MODEL', 'phi3')
    print(f'Ollama enabled: {use_ollama}')
    print(f'Ollama model: {ollama_model}')
    if debug_enabled():
        print('Debug logging enabled via DEBUG_DRONE_AGENT=1 or DEBUG_PROMPT_AGENT=1')
    if not use_ollama or not ollama_model:
        raise RuntimeError('Ollama parsing is required for drones now. Set USE_OLLAMA=1 and OLLAMA_MODEL.')

    try:
        last_parser = None
        while True:
            text = input('drone> ')
            local_cmd = parse_local_drone_command(text)
            if local_cmd is not None:
                cmd = local_cmd
                last_parser = 'local'
            else:
                cmd = ollama_parse_drone_command(text, ollama_model)
                if cmd is None:
                    print('Ollama could not parse the drone command. Check that "ollama serve" is running and the model is installed.')
                    last_parser = 'ollama-error'
                    continue
                last_parser = 'ollama'
            debug_log('drone_user_input', text)
            debug_log('drone_selected_parser', last_parser)
            debug_log('drone_parsed_command', cmd)

            if cmd[0] == 'quit':
                print('Exiting drone controller')
                break
            if cmd[0] == 'help':
                print_help()
                continue
            if cmd[0] == 'status':
                print('Status:')
                for drone in drones:
                    pos, yaw, z = get_actor_pose(comm, drone.name)
                    print(f' - {drone.name}: pos={pos}, yaw={yaw:.1f}, z={z:.1f}')
                continue
            if cmd[0] == 'above_nearest_tree':
                send_drones_above_nearest_tree(comm, drones)
                continue
            if cmd[0] == 'takeoff':
                target_altitude = 900.0 if cmd[1] is None else float(cmd[1])
                for drone in drones:
                    drone.takeoff(target_z=target_altitude)
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

            print('Unknown command:', cmd[1] if len(cmd) > 1 else '')

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
