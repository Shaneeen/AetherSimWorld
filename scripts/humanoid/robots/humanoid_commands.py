import time

from simworld.agent.humanoid import Humanoid
from simworld.communicator.communicator import Communicator
from simworld.communicator.unrealcv import UnrealCV

from scripts.humanoid.map.humanoid_map import (
    look_around,
    navigate_to_directional_option,
    navigate_to_option,
    print_survey_options,
    survey_semantic_candidates,
)
from scripts.humanoid.movement.humanoid_movement import (
    duration_for_steps,
    get_humanoid_pose,
    navigate_to_coordinates,
    navigate_to_semantic_target,
)
from scripts.humanoid.vision.humanoid_vision import caption_current_view
from scripts.humanoid.common import clamp, debug_log

def print_help():
    print('Commands:')
    print(' - walk 2 steps')
    print(' - walk forward')
    print(' - turn left 90')
    print(' - where am i')
    print(' - view / show view')
    print(' - look / scan')
    print(' - caption / describe')
    print(' - explore')
    print(' - go to X Y')
    print(' - go to the nearest store')
    print(' - walk to the closest building')
    print(' - survey building')
    print(' - show options')
    print(' - go to option 2')
    print(' - go to the left tree')
    print(' - go to the right one')
    print(' - stop')
    print(' - quit')
    print('All command parsing is handled by Ollama in this script.')


def execute_command(comm: Communicator, ucv: UnrealCV, hum: Humanoid, ollama_model: str, cmd):
    debug_log('execute_command', cmd)
    if cmd[0] == 'walk_steps':
        steps = float(cmd[1])
        duration = duration_for_steps(steps)
        print(f'Walking {steps} steps -> duration {duration}s')
        comm.humanoid_step_forward(hum.id, duration)

    elif cmd[0] == 'turn':
        _, direction, angle = cmd
        angle = clamp(float(angle), 1.0, 180.0)
        print(f'Turning {direction} by {angle} degrees')
        comm.humanoid_rotate(hum.id, angle, direction)

    elif cmd[0] == 'stop':
        print('Stopping humanoid')
        comm.humanoid_stop(hum.id)

    elif cmd[0] == 'where':
        try:
            pos, yaw = get_humanoid_pose(comm, ucv, hum)
            print(f'Position={pos}, yaw={yaw}')
        except Exception as e:
            print('No position information available (error):', e)

    elif cmd[0] == 'view':
        try:
            img = comm.get_camera_observation(hum.camera_id, 'lit', mode='direct')
            comm.show_img(img)
        except Exception as e:
            print('Failed to get camera image:', e)

    elif cmd[0] == 'caption':
        try:
            captions = caption_current_view(comm, hum)
            print('Captions:')
            for i, c in enumerate(captions):
                print(f' {i+1}. {c}')
        except Exception as e:
            print('Vision caption failed:', e)

    elif cmd[0] == 'explore':
        try:
            rounds = 4
            agg = []
            for i in range(rounds):
                print(f'View {i+1}/{rounds}: capturing...')
                try:
                    captions = caption_current_view(comm, hum)
                    agg.append({'view': i, 'captions': captions})
                    for j, c in enumerate(captions):
                        print(f'  {j+1}. {c}')
                except Exception as e:
                    print('  capture failed:', e)
                comm.humanoid_rotate(hum.id, 90, 'right')
                time.sleep(0.6)
            print('Exploration summary:')
            seen = {}
            for v in agg:
                for c in v['captions']:
                    seen[c] = seen.get(c, 0) + 1
            for k, v in sorted(seen.items(), key=lambda x: -x[1]):
                print(f' - {k} (seen {v} times)')
        except Exception as e:
            print('Explore failed:', e)

    elif cmd[0] == 'look':
        try:
            look_around(comm, ucv, hum)
        except Exception as e:
            print('Look failed:', e)

    elif cmd[0] == 'goto':
        navigate_to_coordinates(comm, ucv, hum, cmd[1])

    elif cmd[0] == 'navigate_to_query':
        navigate_to_semantic_target(comm, ucv, hum, ollama_model, cmd[1])

    elif cmd[0] == 'survey':
        survey_semantic_candidates(comm, ucv, hum, ollama_model, cmd[1])

    elif cmd[0] == 'show_options':
        print_survey_options()

    elif cmd[0] == 'goto_option':
        navigate_to_option(comm, ucv, hum, int(cmd[1]))

    elif cmd[0] == 'goto_directional_option':
        navigate_to_directional_option(comm, ucv, hum, str(cmd[1]))

    elif cmd[0] == 'help':
        print_help()

    elif cmd[0] == 'unknown':
        print('Unknown command:', cmd[1])

    elif cmd[0] == 'quit':
        print('Exiting')
        return False

    return True


