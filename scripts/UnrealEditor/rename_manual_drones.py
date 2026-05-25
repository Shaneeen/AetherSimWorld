"""
Rename manually placed drone static mesh actors for the ROS bridge.

How to use in Unreal Editor:
1. Open DroneArenaV1.umap.
2. Select the 10 drone actors in the Outliner, including the existing DroneA
   and DroneB. It is okay if their current names have random suffixes.
3. Run this file from Unreal's Python console:
   exec(open(r"D:/SimWorld/scripts/UnrealEditor/rename_manual_drones.py").read())

The script keeps the existing DroneA and DroneB actors as the primary drones,
then renames the closest four extra actors to:
  DroneA1, DroneA2, DroneA3, DroneA4
  DroneB1, DroneB2, DroneB3, DroneB4
"""

from __future__ import annotations

import math
import re

import unreal


PRIMARY_A = "DroneA"
PRIMARY_B = "DroneB"
EXTRAS_PER_TEAM = 4


def _selected_actors():
    try:
        subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        return list(subsystem.get_selected_level_actors())
    except Exception:
        return list(unreal.EditorLevelLibrary.get_selected_level_actors())


def _all_actors():
    try:
        subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        return list(subsystem.get_all_level_actors())
    except Exception:
        return list(unreal.EditorLevelLibrary.get_all_level_actors())


def _label(actor) -> str:
    return actor.get_actor_label()


def _find_actor_by_label(label: str):
    for actor in _all_actors():
        if _label(actor) == label:
            return actor
    return None


def _distance_xy(a, b) -> float:
    la = a.get_actor_location()
    lb = b.get_actor_location()
    return math.hypot(float(la.x) - float(lb.x), float(la.y) - float(lb.y))


def _natural_key(actor):
    text = _label(actor)
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", text)]


def _rename_actor(actor, target_name: str) -> None:
    # set_actor_label is what you see in the Outliner. rename tries to update
    # the internal object name too, which is what UnrealCV usually lists.
    actor.set_actor_label(target_name, mark_dirty=True)
    try:
        actor.rename(target_name)
    except Exception as exc:
        unreal.log_warning(f"Could not rename internal object for {target_name}: {exc}")


def _team_extras(candidates, primary, other_primary):
    extras = []
    for actor in candidates:
        if actor == primary or actor == other_primary:
            continue
        if _distance_xy(actor, primary) <= _distance_xy(actor, other_primary):
            extras.append(actor)
    extras.sort(key=lambda actor: (_distance_xy(actor, primary), _natural_key(actor)))
    return extras[:EXTRAS_PER_TEAM]


def main() -> None:
    selected = _selected_actors()
    if not selected:
        raise RuntimeError("Select the manually placed drone actors first, then run this script.")

    primary_a = _find_actor_by_label(PRIMARY_A)
    primary_b = _find_actor_by_label(PRIMARY_B)
    if primary_a is None or primary_b is None:
        raise RuntimeError("Could not find existing primary actors named DroneA and DroneB.")

    candidates = selected
    if primary_a not in candidates:
        candidates.append(primary_a)
    if primary_b not in candidates:
        candidates.append(primary_b)

    extras_a = _team_extras(candidates, primary_a, primary_b)
    extras_b = _team_extras(candidates, primary_b, primary_a)

    if len(extras_a) < EXTRAS_PER_TEAM or len(extras_b) < EXTRAS_PER_TEAM:
        raise RuntimeError(
            "Need DroneA, DroneB, and four extra selected meshes near each primary. "
            f"Found A extras={len(extras_a)}, B extras={len(extras_b)}."
        )

    # Temporarily move selected drone labels out of the way to avoid duplicate
    # names causing Unreal to append suffixes while we rename.
    for index, actor in enumerate(candidates, start=1):
        if actor != primary_a and actor != primary_b:
            _rename_actor(actor, f"TmpManualDroneRename_{index}")

    _rename_actor(primary_a, PRIMARY_A)
    _rename_actor(primary_b, PRIMARY_B)

    for index, actor in enumerate(extras_a, start=1):
        _rename_actor(actor, f"{PRIMARY_A}{index}")
    for index, actor in enumerate(extras_b, start=1):
        _rename_actor(actor, f"{PRIMARY_B}{index}")

    unreal.EditorLevelLibrary.save_current_level()
    unreal.log(
        "Manual drone rename complete: "
        "DroneA, DroneA1-DroneA4, DroneB, DroneB1-DroneB4. Level saved."
    )


main()
