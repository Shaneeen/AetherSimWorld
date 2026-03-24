import math
import time

from simworld.utils.vector import Vector

from scripts.UltraHumanoid.Vision.perception import depth_stats_cm
from scripts.UltraHumanoid.common import clamp, debug_log
from scripts.UltraHumanoid.Map.world_model import get_agent_pose


DEFAULT_WALK_SPEED_CM_PER_SEC = 200.0
DEFAULT_STEP_MAX_SEC = 2.5
ANGLE_DEADBAND_DEG = 6.0
APPROACH_TRIGGER_CM = 450.0
MAX_ITER_TIME_SEC = 60.0
DEPTH_LOCK_TRIGGER_CM = 700.0
DEPTH_STOP_BUFFER_CM = 35.0
MIN_DEPTH_WALK_CM = 35.0


def calibrate_walk_speed(comm, hum):
    try:
        start, _ = get_agent_pose(comm, hum)
        comm.humanoid_step_forward(hum.id, 0.5)
        end, _ = get_agent_pose(comm, hum)
        distance = start.distance(end)
        if distance > 5.0:
            return max(50.0, distance / 0.5)
    except Exception:
        pass
    return DEFAULT_WALK_SPEED_CM_PER_SEC


def normalize_angle_deg(angle: float) -> float:
    return ((angle + 180.0) % 360.0) - 180.0


def angle_error(current_pos: Vector, yaw: float, target_pos: Vector) -> float:
    heading = math.degrees(math.atan2(target_pos.y - current_pos.y, target_pos.x - current_pos.x))
    return normalize_angle_deg(heading - yaw)


def duration_for_distance(distance_cm: float, walk_speed: float):
    return clamp(max(0.0, distance_cm) / max(1.0, walk_speed), 0.15, DEFAULT_STEP_MAX_SEC)


def desired_stop_distance_cm(target):
    radius_cm = float(target.get('radius_cm', 150.0))
    return max(90.0, radius_cm + 60.0)


def desired_surface_depth_cm(target):
    radius_cm = float(target.get('radius_cm', 150.0))
    # Desired final camera-to-surface gap.
    return max(90.0, min(220.0, radius_cm * 0.75))


def navigate_direct_to_target(comm, ucv, hum, target, walk_speed: float):
    target_pos = Vector(target['world_x'], target['world_y'])
    fallback_stop_distance = desired_stop_distance_cm(target)
    target_surface_depth = desired_surface_depth_cm(target)
    started_at = time.time()
    previous_pos = None
    stuck_count = 0

    while time.time() - started_at < MAX_ITER_TIME_SEC:
        pos, yaw = get_agent_pose(comm, hum)
        remaining = pos.distance(target_pos)
        err = angle_error(pos, yaw, target_pos)
        depth = depth_stats_cm(comm, hum) if remaining <= DEPTH_LOCK_TRIGGER_CM and abs(err) < 18.0 else None
        debug_log(
            'ultra_nav_state',
            {
                'pos': pos,
                'yaw': yaw,
                'remaining': remaining,
                'fallback_stop_distance': fallback_stop_distance,
                'target_surface_depth': target_surface_depth,
                'angle_error': err,
                'depth': depth,
            },
        )

        if depth is not None:
            median_depth = depth['median_depth_cm']
            min_depth = depth['min_depth_cm']
            print(
                f'Ultra navigation: depth lock on {target["name"]} '
                f'(min={min_depth:.1f} cm, median={median_depth:.1f} cm, desired={target_surface_depth:.1f} cm)'
            )
            if min_depth <= target_surface_depth + DEPTH_STOP_BUFFER_CM:
                print('Ultra navigation: stopping from depth-based surface estimate')
                return True, remaining

        if remaining <= fallback_stop_distance:
            print(
                f'Ultra navigation: reached fallback target standoff at {remaining:.1f} cm '
                f'(goal {fallback_stop_distance:.1f} cm)'
            )
            return True, remaining

        if abs(err) > ANGLE_DEADBAND_DEG:
            direction = 'right' if err > 0 else 'left'
            angle = clamp(abs(err) * 0.8, 5.0, 40.0)
            print(f'Ultra navigation: turning {direction} by {angle:.1f} degrees')
            comm.humanoid_rotate(hum.id, angle, direction)
            time.sleep(0.2)
            continue

        if depth is not None:
            step_distance = clamp(depth['median_depth_cm'] - target_surface_depth, MIN_DEPTH_WALK_CM, 120.0)
        elif remaining <= APPROACH_TRIGGER_CM:
            step_distance = min(max(remaining - fallback_stop_distance, 60.0), 140.0)
        else:
            step_distance = min(max(remaining - fallback_stop_distance, 80.0), max(120.0, remaining * 0.35))
        duration = duration_for_distance(step_distance, walk_speed)
        print(f'Ultra navigation: stepping toward {target["name"]} for {duration:.2f}s (step_distance={step_distance:.1f} cm)')
        comm.humanoid_step_forward(hum.id, duration)

        new_pos, _ = get_agent_pose(comm, hum)
        if previous_pos is not None and new_pos.distance(previous_pos) < 10.0:
            stuck_count += 1
            recovery_dir = 'left' if stuck_count % 2 == 0 else 'right'
            print(f'Ultra navigation: low progress detected, recovery turn {recovery_dir} 20 deg')
            comm.humanoid_rotate(hum.id, 20.0, recovery_dir)
            time.sleep(0.2)
        else:
            stuck_count = 0
        previous_pos = new_pos

    final_pos, _ = get_agent_pose(comm, hum)
    final_remaining = final_pos.distance(target_pos)
    print(f'Ultra navigation: time limit reached with {final_remaining:.1f} cm remaining')
    return False, final_remaining
