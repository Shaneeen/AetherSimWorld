import math
import os
import time

from simworld.agent.humanoid import Humanoid
from simworld.communicator.communicator import Communicator
from simworld.communicator.unrealcv import UnrealCV
from simworld.utils.vector import Vector

from scripts.humanoid.common import (
    CALIBRATION_STEP_DURATION,
    DEFAULT_WALK_SPEED_CM_PER_SEC,
    GOTO_DISTANCE_DIVISOR,
    GOTO_FINAL_APPROACH_STOP_DISTANCE_CM,
    GOTO_FINAL_APPROACH_TRIGGER_CM,
    GOTO_FINAL_APPROACH_WALK_CM,
    GOTO_FINAL_WALK_DISTANCE_CM,
    GOTO_MAX_ITERS,
    GOTO_MAX_TIME_SEC,
    GOTO_MAX_TURN_DEG,
    GOTO_ITER_DISTANCE_CM,
    GOTO_STOP_DISTANCE,
    GOTO_TURN_DEADBAND_DEG,
    MAX_STEP_DURATION,
    NAVIGATION_STOP_DISTANCE,
    NAVIGATION_STEP_LIMIT,
    STUCK_DISTANCE_EPS,
    STUCK_MAX_COUNT,
    clamp,
    get_walk_speed_cm_per_sec as get_shared_walk_speed_cm_per_sec,
    set_walk_speed_cm_per_sec,
)

def suggest_walk_steps(distance_cm: float) -> float:
    if distance_cm > 500:
        return 5.0
    if distance_cm > 300:
        return 4.0
    if distance_cm > 180:
        return 3.0
    if distance_cm > 90:
        return 2.0
    return 1.0


def angle_between(from_vec: Vector, to_vec: Vector):
    # compute signed yaw (degrees) to turn from from_vec to to_vec
    dot = from_vec.dot(to_vec)
    cross = from_vec.cross(to_vec)
    dot = max(min(dot, 1.0), -1.0)
    angle = math.degrees(math.acos(dot))
    direction = 'left' if cross < 0 else 'right'
    return direction, angle


def normalize_angle_deg(angle: float) -> float:
    return ((angle + 180.0) % 360.0) - 180.0


def compute_signed_angle_error(current_pos: Vector, yaw: float, target_pos: Vector) -> float:
    dx = target_pos.x - current_pos.x
    dy = target_pos.y - current_pos.y
    target_heading = math.degrees(math.atan2(dy, dx))
    return normalize_angle_deg(target_heading - yaw)


def choose_deterministic_navigation_step(current_pos: Vector, yaw: float, target_pos: Vector):
    distance = current_pos.distance(target_pos)
    angle_error = compute_signed_angle_error(current_pos, yaw, target_pos)
    if abs(angle_error) > GOTO_TURN_DEADBAND_DEG:
        direction = 'right' if angle_error > 0 else 'left'
        angle = clamp(abs(angle_error) * 0.7, 5.0, GOTO_MAX_TURN_DEG)
        return ('turn', direction, angle), angle_error

    steps = suggest_walk_steps(distance)
    if distance < 120:
        steps = min(steps, 2.0)
    return ('walk_steps', steps), angle_error


def get_humanoid_pose(comm: Communicator, ucv: UnrealCV, hum: Humanoid):
    try:
        info = comm.get_position_and_direction(humanoid_ids=[hum.id])
        pos_dir = info.get(('humanoid', hum.id))
        if pos_dir:
            pos, yaw = pos_dir
            return pos, float(yaw)
    except Exception:
        pass

    name = comm.get_humanoid_name(hum.id)
    loc = ucv.get_location(name)
    ori = ucv.get_orientation(name)
    pos = Vector(loc[0], loc[1])
    yaw = float(ori[1]) if len(ori) > 1 else 0.0
    return pos, yaw


def get_walk_speed_cm_per_sec():
    return get_shared_walk_speed_cm_per_sec()


def duration_for_steps(steps: float) -> float:
    distance_cm = max(0.0, float(steps)) * CALIBRATION_STEP_DURATION * get_walk_speed_cm_per_sec()
    speed = max(1.0, get_walk_speed_cm_per_sec())
    return clamp(distance_cm / speed, 0.1, MAX_STEP_DURATION)


def duration_for_distance_cm(distance_cm: float, max_duration: float = MAX_STEP_DURATION) -> float:
    speed = max(1.0, get_walk_speed_cm_per_sec())
    return clamp(max(0.0, float(distance_cm)) / speed, 0.1, max_duration)


def compute_goto_iteration_budget(initial_remaining_cm: float) -> int:
    extra_iters = int(math.ceil(max(0.0, float(initial_remaining_cm)) / GOTO_ITER_DISTANCE_CM))
    return max(GOTO_MAX_ITERS, extra_iters)


def calibrate_walk_speed(comm: Communicator, ucv: UnrealCV, hum: Humanoid):
    if os.environ.get('CALIBRATE_WALK_SPEED', '1') == '0':
        print(f'Walk calibration skipped. Using default speed {get_walk_speed_cm_per_sec():.1f} cm/s')
        return

    try:
        start_pos, _ = get_humanoid_pose(comm, ucv, hum)
        print(f'Calibrating walk speed with a {CALIBRATION_STEP_DURATION:.2f}s forward step...')
        comm.humanoid_step_forward(hum.id, CALIBRATION_STEP_DURATION)
        end_pos, _ = get_humanoid_pose(comm, ucv, hum)
        distance = start_pos.distance(end_pos)
        if distance > 5.0:
            set_walk_speed_cm_per_sec(distance / CALIBRATION_STEP_DURATION)
            print(f'Calibrated walk speed: {get_walk_speed_cm_per_sec():.1f} cm/s over {distance:.1f} cm')
        else:
            set_walk_speed_cm_per_sec(DEFAULT_WALK_SPEED_CM_PER_SEC)
            print(
                f'Calibration movement was too small ({distance:.1f} cm). '
                f'Using default speed {get_walk_speed_cm_per_sec():.1f} cm/s'
            )
    except Exception as e:
        set_walk_speed_cm_per_sec(DEFAULT_WALK_SPEED_CM_PER_SEC)
        print(f'Walk calibration failed, using default speed {get_walk_speed_cm_per_sec():.1f} cm/s: {e}')


def cleanup_prompt_agent_actors(comm: Communicator):
    try:
        objects = [str(obj) for obj in comm.unrealcv.get_objects()]
    except Exception as e:
        print(f'Startup cleanup skipped: {e}')
        return

    targets = []
    for obj_name in objects:
        lowered = obj_name.lower()
        if lowered.startswith('gen_bp_humanoid_') or lowered == 'gen_bp_uemanager':
            targets.append(obj_name)

    if not targets:
        print('No previous humanoids or prompt-agent manager found.')
        return

    print(f'Cleaning {len(targets)} previously spawned humanoid/helper actors...')
    for obj_name in targets:
        try:
            comm.unrealcv.destroy(obj_name)
        except Exception as e:
            print(f'Could not destroy {obj_name}: {e}')

    try:
        comm.unrealcv.clean_garbage()
    except Exception:
        pass


def navigate_to_target_position(comm: Communicator, hum: Humanoid, current_pos: Vector, yaw: float, target_pos: Vector):
    to_target = Vector(target_pos.x - current_pos.x, target_pos.y - current_pos.y)
    distance = to_target.length()
    if distance <= 0:
        return 0.0
    dir_vec = Vector(1, 0)
    try:
        dir_vec = Vector(math.cos(math.radians(yaw)), math.sin(math.radians(yaw)))
    except Exception:
        pass
    turn_dir, angle = angle_between(dir_vec, to_target.normalize())
    print(f'Navigating: turning {turn_dir} by {angle:.1f} degrees')
    comm.humanoid_rotate(hum.id, angle, turn_dir)
    duration = clamp(min(distance / max(1.0, get_walk_speed_cm_per_sec()), NAVIGATION_STEP_LIMIT), 0.2, MAX_STEP_DURATION)
    print(f'Navigating: walking toward target for {duration:.2f}s')
    comm.humanoid_step_forward(hum.id, duration)
    return distance


def recover_from_stuck(comm: Communicator, hum: Humanoid, attempt: int):
    recovery_angle = 25.0 if attempt % 2 == 1 else 45.0
    recovery_dir = 'right' if attempt % 2 == 1 else 'left'
    print(f'Navigation: detected no progress, trying recovery turn {recovery_dir} {recovery_angle:.1f} degrees')
    comm.humanoid_rotate(hum.id, recovery_angle, recovery_dir)
    print('Navigation: trying a short recovery walk')
    comm.humanoid_step_forward(hum.id, 0.5)


def execute_final_approach(comm: Communicator, ucv: UnrealCV, hum: Humanoid, target: Vector) -> bool:
    try:
        pos, yaw = get_humanoid_pose(comm, ucv, hum)
    except Exception as e:
        print(f'Navigation: final approach aborted, current position unknown: {e}')
        return False

    remaining = pos.distance(target)
    angle_error = compute_signed_angle_error(pos, yaw, target)
    print(
        f'Navigation: final approach triggered at remaining={remaining:.1f} cm, '
        f'angle_error={angle_error:.1f} degrees'
    )

    if abs(angle_error) > 2.0:
        direction = 'right' if angle_error > 0 else 'left'
        angle = clamp(abs(angle_error), 1.0, 20.0)
        print(f'Navigation: final approach turning {direction} by {angle:.1f} degrees')
        comm.humanoid_rotate(hum.id, angle, direction)

    walk_distance_cm = min(remaining, GOTO_FINAL_APPROACH_WALK_CM)
    duration = duration_for_distance_cm(walk_distance_cm)
    print(f'Navigation: final approach walking {walk_distance_cm:.1f} cm for {duration:.2f}s')
    comm.humanoid_step_forward(hum.id, duration)

    try:
        final_pos, _ = get_humanoid_pose(comm, ucv, hum)
    except Exception as e:
        print(f'Navigation: final approach completed but could not verify final distance: {e}')
        return False

    final_remaining = final_pos.distance(target)
    print(f'Navigation: final approach remaining distance {final_remaining:.1f} cm')
    if final_remaining <= GOTO_FINAL_APPROACH_STOP_DISTANCE_CM:
        print('Navigation: final approach marked target as reached')
        return True
    return False


def navigate_to_coordinates(comm: Communicator, ucv: UnrealCV, hum: Humanoid, target: Vector):
    print(f'Navigation: moving toward coordinates ({target.x:.1f}, {target.y:.1f})')
    stuck_count = 0
    previous_pos = None
    previous_action = None
    started_at = time.time()
    max_iters = GOTO_MAX_ITERS
    iteration = 0
    while iteration < max_iters:
        iteration += 1
        try:
            pos, yaw = get_humanoid_pose(comm, ucv, hum)
        except Exception:
            print('Navigation: current position unknown, cannot continue goto')
            return

        remaining = pos.distance(target)
        if iteration == 1:
            max_iters = compute_goto_iteration_budget(remaining)
            print(f'Navigation: iteration budget set to {max_iters} steps for initial remaining distance {remaining:.1f} cm')

        elapsed = time.time() - started_at
        if elapsed > GOTO_MAX_TIME_SEC:
            print(f'Navigation: stopped after reaching time limit of {GOTO_MAX_TIME_SEC:.1f}s')
            return

        print(f'Navigation step {iteration}/{max_iters}: current={pos}, remaining={remaining:.1f} cm')
        if remaining <= GOTO_STOP_DISTANCE:
            print('Navigation: reached target coordinates')
            return
        if remaining <= GOTO_FINAL_APPROACH_TRIGGER_CM:
            if execute_final_approach(comm, ucv, hum, target):
                return

        if previous_action in ('walk_steps', 'recovery_walk') and previous_pos is not None and pos.distance(previous_pos) < STUCK_DISTANCE_EPS:
            stuck_count += 1
            print(f'Navigation: progress since last step was too small ({pos.distance(previous_pos):.1f} cm)')
        else:
            stuck_count = 0

        if stuck_count >= STUCK_MAX_COUNT:
            recover_from_stuck(comm, hum, stuck_count)
            previous_pos = pos
            previous_action = 'recovery_walk'
            continue

        next_cmd, angle_error = choose_deterministic_navigation_step(pos, yaw, target)
        print(f'Navigation controller: angle_error={angle_error:.1f} degrees, selected {next_cmd}')

        if iteration == max_iters and remaining <= GOTO_FINAL_WALK_DISTANCE_CM:
            duration = duration_for_distance_cm(remaining)
            estimated_steps = max(1.0, remaining / max(1.0, CALIBRATION_STEP_DURATION * get_walk_speed_cm_per_sec()))
            print(
                f'Navigation: final iteration fallback, forcing last walk '
                f'({remaining:.1f} cm, est {estimated_steps:.1f} step(s))'
            )
            print(f'Navigating: walking for {duration:.2f}s')
            comm.humanoid_step_forward(hum.id, duration)
            previous_action = 'walk_steps'
            previous_pos = pos
            continue

        if next_cmd[0] == 'walk_steps':
            chunk_distance_cm = max(remaining / GOTO_DISTANCE_DIVISOR, GOTO_STOP_DISTANCE)
            duration = duration_for_distance_cm(chunk_distance_cm)
            estimated_steps = max(1.0, chunk_distance_cm / max(1.0, CALIBRATION_STEP_DURATION * get_walk_speed_cm_per_sec()))
            print(
                f'Navigation: using one-fifth remaining distance '
                f'({chunk_distance_cm:.1f} cm, est {estimated_steps:.1f} step(s))'
            )
            print(f'Navigating: walking for {duration:.2f}s')
            comm.humanoid_step_forward(hum.id, duration)
            previous_action = 'walk_steps'
        elif next_cmd[0] == 'turn':
            _, direction, angle = next_cmd
            angle = clamp(float(angle), 5.0, GOTO_MAX_TURN_DEG if remaining > 150 else 90.0)
            print(f'Navigating: turning {direction} by {angle:.1f} degrees')
            comm.humanoid_rotate(hum.id, angle, direction)
            previous_action = 'turn'
        previous_pos = pos

    print(f'Navigation: stopped after max iteration budget ({max_iters}) without fully reaching target')


def navigate_to_semantic_target(comm: Communicator, ucv: UnrealCV, hum: Humanoid, model: str, query: str):
    from scripts.humanoid.map.humanoid_map import survey_semantic_candidates

    print(f'Navigation: searching for "{query}"')
    options = survey_semantic_candidates(comm, ucv, hum, model, query)
    if not options:
        return
    top_option = options[0]
    top_distance = top_option.get('distance')
    print(f'Navigation: best current option is {top_option["name"]}')
    if len(options) > 1:
        print('Navigation: multiple plausible matches found. Use "go to option N" to pick one explicitly.')
        return
    if isinstance(top_distance, (int, float)) and top_distance <= NAVIGATION_STOP_DISTANCE:
        print('Navigation: already near the selected target area')
        return
    print('Navigation: only one strong candidate found, proceeding automatically')
    navigate_to_option(comm, ucv, hum, 1)


