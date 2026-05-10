import math
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.Drone.common import (
    DEFAULT_UNREALCV_PORT,
    debug_enabled,
    debug_log,
    maybe_launch_simworld,
    ollama_parse_drone_command,
    parse_local_drone_command,
    startup_log,
    wait_for_simworld_server,
    wait_for_user_world_ready,
)

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

startup_log(f"Python executable: {sys.executable}")
startup_log(f"Working directory: {os.getcwd()}")
startup_log(f"Repo root: {REPO_ROOT}")

try:
    startup_log("Importing SimWorld modules...")
    from simworld.communicator.communicator import Communicator
    from simworld.communicator.unrealcv import UnrealCV
    from simworld.config import Config
    from simworld.utils.vector import Vector
    startup_log("SimWorld imports succeeded.")
except Exception as e:
    startup_log(f"SimWorld import failed: {type(e).__name__}: {e}")
    raise

from scripts.Drone.Map.Drone_Map import DroneMap
from scripts.Drone.Movement.Drone_Movement import send_drones_above_nearest_tree
from scripts.Drone.Robots.Drone_blue import DroneBlue
from scripts.Drone.Robots.Drone_red import DroneRed
from scripts.Drone.Vision.Drone_Vision import point_camera_at_drone


def parse_resolution() -> tuple[int, int]:
    resolution_text = os.environ.get("SIMWORLD_RESOLUTION", "320x240").lower()
    try:
        width_text, height_text = resolution_text.split("x", 1)
        return int(width_text), int(height_text)
    except Exception:
        return 320, 240


def print_help() -> None:
    print("Commands:")
    print("  takeoff")
    print("  land")
    print("  up 200")
    print("  down 200")
    print("  hover 2")
    print("  orbit 700")
    print("  goto 100 200 900")
    print("  move 100 0 0")
    print("  go above nearest tree")
    print("  view")
    print("  status")
    print("  help")
    print("  quit")


def connect() -> tuple[UnrealCV, Communicator, Config]:
    launch_state = maybe_launch_simworld()
    if launch_state in ("launched", "reused"):
        wait_for_user_world_ready()
    wait_for_simworld_server()

    host = os.environ.get("SIMWORLD_HOST", "127.0.0.1")
    port = int(os.environ.get("SIMWORLD_PORT", str(DEFAULT_UNREALCV_PORT)))
    resolution = parse_resolution()

    print(f"Connecting to UnrealCV ({host}:{port})...")
    ucv = UnrealCV(port=port, ip=host, resolution=resolution)
    comm = Communicator(ucv)
    config_path = os.environ.get("SIMWORLD_CONFIG")
    cfg = Config(config_path) if config_path else Config()
    return ucv, comm, cfg


def maybe_setup_world(comm: Communicator, cfg: Config) -> None:
    if os.environ.get("SIMWORLD_GENERATE_WORLD", "0") != "1":
        return
    try:
        DroneMap(cfg.config_path if hasattr(cfg, "config_path") else "config/light.yaml").setup_world(comm)
    except Exception as e:
        print("Failed to generate procedural world:", e)


def build_drones(comm: Communicator) -> list:
    drone_asset = os.environ.get("SIMWORLD_DRONE_ASSET")
    drone_a_asset = os.environ.get("SIMWORLD_DRONE_A_ASSET", os.environ.get("SIMWORLD_DRONE_ASSET_A", drone_asset))
    drone_b_asset = os.environ.get("SIMWORLD_DRONE_B_ASSET", os.environ.get("SIMWORLD_DRONE_ASSET_B", drone_asset))

    drone_a = DroneBlue(
        comm=comm,
        model_path=drone_a_asset,
        position=Vector(
            float(os.environ.get("SIMWORLD_DRONE_A_X", "600")),
            float(os.environ.get("SIMWORLD_DRONE_A_Y", os.environ.get("SIMWORLD_DRONE_Y", "0"))),
        ),
        z_height=float(os.environ.get("SIMWORLD_DRONE_A_Z", os.environ.get("SIMWORLD_DRONE_Z", "600"))),
        color=(255, 50, 50),
    )
    drone_b = DroneRed(
        comm=comm,
        model_path=drone_b_asset,
        position=Vector(
            float(os.environ.get("SIMWORLD_DRONE_B_X", "-600")),
            float(os.environ.get("SIMWORLD_DRONE_B_Y", os.environ.get("SIMWORLD_DRONE_Y", "0"))),
        ),
        z_height=float(os.environ.get("SIMWORLD_DRONE_B_Z", os.environ.get("SIMWORLD_DRONE_Z", "600"))),
    )
    return [drone_a, drone_b]


def spawn_drones(drones: list) -> None:
    for drone in drones:
        print(f"Spawning {drone.name} using {drone.model_path}...")
        drone.spawn()
        time.sleep(0.2)


def print_status(drones: list) -> None:
    for drone in drones:
        print(
            f"{drone.name}: x={drone.position.x:.1f}, "
            f"y={drone.position.y:.1f}, z={drone.z:.1f}, "
            f"asset={drone.model_path}"
        )


def handle_command(comm: Communicator, drones: list, parsed: tuple) -> bool:
    action = parsed[0]

    if action == "quit":
        return False
    if action == "help":
        print_help()
        return True
    if action == "status":
        print_status(drones)
        return True
    if action == "takeoff":
        altitude = parsed[1] if len(parsed) > 1 and parsed[1] is not None else 900.0
        for drone in drones:
            drone.takeoff(target_z=float(altitude))
        return True
    if action == "land":
        for drone in drones:
            drone.land()
        return True
    if action == "hover":
        duration = float(parsed[1]) if len(parsed) > 1 else 1.0
        for drone in drones:
            drone.hover(duration)
        return True
    if action == "up":
        amount = float(parsed[1]) if len(parsed) > 1 else 100.0
        for drone in drones:
            drone.move_up(amount)
        return True
    if action == "down":
        amount = float(parsed[1]) if len(parsed) > 1 else 100.0
        for drone in drones:
            drone.move_down(amount)
        return True
    if action == "move":
        dx, dy, dz = float(parsed[1]), float(parsed[2]), float(parsed[3])
        for drone in drones:
            drone.move_by(dx, dy, dz)
        return True
    if action == "goto":
        x, y = float(parsed[1]), float(parsed[2])
        z = None if parsed[3] is None else float(parsed[3])
        for drone in drones:
            drone.move_to(x, y, drone.z if z is None else z)
        return True
    if action == "orbit":
        radius = float(parsed[1]) if len(parsed) > 1 else 700.0
        center = Vector(
            sum(drone.position.x for drone in drones) / len(drones),
            sum(drone.position.y for drone in drones) / len(drones),
        )
        start = time.time()
        duration = 8.0
        while time.time() - start < duration:
            t = time.time() - start
            for index, drone in enumerate(drones):
                drone.orbit(center, radius, angular_offset=index * math.pi, t=t, speed=0.7)
            time.sleep(0.1)
        return True
    if action == "above_nearest_tree":
        send_drones_above_nearest_tree(comm, drones)
        return True
    if action in ("look", "view"):
        heading_deg = 0.0
        point_camera_at_drone(comm, drones[0], heading_deg=heading_deg)
        image = comm.get_camera_observation(0, "lit", mode="direct")
        comm.show_img(image)
        return True

    print(f"Unknown command: {parsed}")
    return True


def main() -> None:
    ucv = None
    try:
        ucv, comm, cfg = connect()
        maybe_setup_world(comm, cfg)
        drones = build_drones(comm)
        spawn_drones(drones)

        use_ollama = os.environ.get("USE_OLLAMA", "1") != "0"
        ollama_model = os.environ.get("OLLAMA_MODEL", "phi3")

        print("Ready. Type commands.")
        print_help()
        if debug_enabled():
            print("Debug logging enabled via DEBUG_DRONE_AGENT=1")

        last_parser = None
        while True:
            text = input("> ")
            local_cmd = parse_local_drone_command(text)
            if local_cmd is not None:
                parsed = local_cmd
                last_parser = "local"
            else:
                if not use_ollama:
                    print("Only help/status/quit are available when USE_OLLAMA=0.")
                    continue
                parsed = ollama_parse_drone_command(text, ollama_model)
                if parsed is None:
                    print('Ollama could not parse the command. Check that "ollama serve" is running and the model is installed.')
                    last_parser = "ollama-error"
                    continue
                last_parser = "ollama"

            debug_log("user_input", text)
            debug_log("selected_parser", last_parser)
            debug_log("parsed_command", parsed)

            keep_running = handle_command(comm, drones, parsed)
            if not keep_running:
                break
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        print("Disconnecting...")
        if ucv is not None:
            try:
                ucv.disconnect()
            except Exception:
                pass


if __name__ == "__main__":
    main()
