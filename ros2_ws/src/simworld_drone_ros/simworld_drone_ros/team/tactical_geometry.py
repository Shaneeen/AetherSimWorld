from __future__ import annotations

from dataclasses import dataclass
import math
import os


@dataclass(frozen=True)
class TacticalBlocker:
    """Simple circular tactical blocker used for LOS, cover, and route hints."""

    name: str
    x: float
    y: float
    radius: float
    min_z: float
    max_z: float


def distance_xy(a: tuple[float, float] | tuple[float, float, float], b: tuple[float, float] | tuple[float, float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def normalize_xy(x: float, y: float) -> tuple[float, float]:
    length = math.hypot(x, y)
    if length <= 1e-6:
        return 1.0, 0.0
    return x / length, y / length


def segment_distance_xy(ax: float, ay: float, bx: float, by: float, cx: float, cy: float) -> float:
    dx = bx - ax
    dy = by - ay
    length_sq = dx * dx + dy * dy
    if length_sq <= 1e-6:
        return math.hypot(ax - cx, ay - cy)
    t = ((cx - ax) * dx + (cy - ay) * dy) / length_sq
    t = max(0.0, min(1.0, t))
    px = ax + t * dx
    py = ay + t * dy
    return math.hypot(px - cx, py - cy)


def segment_intersects_blocker(
    start: tuple[float, float] | tuple[float, float, float],
    end: tuple[float, float] | tuple[float, float, float],
    blocker: TacticalBlocker,
    clearance: float,
) -> bool:
    return (
        segment_distance_xy(start[0], start[1], end[0], end[1], blocker.x, blocker.y)
        <= blocker.radius + clearance
    )


def first_blocking_blocker(
    start: tuple[float, float] | tuple[float, float, float],
    end: tuple[float, float] | tuple[float, float, float],
    blockers: tuple[TacticalBlocker, ...],
    clearance: float,
) -> TacticalBlocker | None:
    best = None
    best_distance = float("inf")
    for blocker in blockers:
        if not segment_intersects_blocker(start, end, blocker, clearance):
            continue
        distance = distance_xy(start, (blocker.x, blocker.y))
        if distance < best_distance:
            best_distance = distance
            best = blocker
    return best


def line_of_sight_clear(
    start: tuple[float, float] | tuple[float, float, float],
    end: tuple[float, float] | tuple[float, float, float],
    blockers: tuple[TacticalBlocker, ...],
    clearance: float = 0.0,
) -> bool:
    return first_blocking_blocker(start, end, blockers, clearance) is None


def route_around_blockers(
    start: tuple[float, float] | tuple[float, float, float],
    desired: tuple[float, float] | tuple[float, float, float],
    blockers: tuple[TacticalBlocker, ...],
    clearance: float,
) -> tuple[float, float, str | None]:
    blocker = first_blocking_blocker(start, desired, blockers, clearance)
    if blocker is None:
        return desired[0], desired[1], None

    to_goal_x, to_goal_y = normalize_xy(desired[0] - start[0], desired[1] - start[1])
    perp_x, perp_y = -to_goal_y, to_goal_x
    shoulder = blocker.radius + clearance
    candidates = (
        (blocker.x + perp_x * shoulder, blocker.y + perp_y * shoulder),
        (blocker.x - perp_x * shoulder, blocker.y - perp_y * shoulder),
    )
    best = min(candidates, key=lambda point: distance_xy(start, point) + distance_xy(point, desired))
    return best[0], best[1], f"routing around {blocker.name}"


def cover_point(
    protected: tuple[float, float] | tuple[float, float, float],
    threat: tuple[float, float] | tuple[float, float, float],
    blockers: tuple[TacticalBlocker, ...],
    clearance: float,
) -> tuple[float, float, str] | None:
    if not blockers:
        return None

    best = None
    best_score = float("inf")
    for blocker in blockers:
        to_safe_x, to_safe_y = normalize_xy(protected[0] - threat[0], protected[1] - threat[1])
        x = blocker.x + to_safe_x * (blocker.radius + clearance)
        y = blocker.y + to_safe_y * (blocker.radius + clearance)
        blocker_to_line = segment_distance_xy(
            protected[0],
            protected[1],
            threat[0],
            threat[1],
            blocker.x,
            blocker.y,
        )
        score = blocker_to_line * 1.5 + distance_xy(protected, (x, y)) * 0.5 + distance_xy(threat, (x, y)) * 0.15
        if score < best_score:
            best_score = score
            best = (x, y, f"using {blocker.name} as cover")
    return best


def read_tactical_blockers(min_z: float, max_z: float) -> tuple[TacticalBlocker, ...]:
    """Read tactical blockers from existing sim env vars.

    Preferred format:
      SIM_TACTICAL_BLOCKERS=name,x,y,radius[,min_z,max_z];...

    Compatibility formats:
      SIM_COLLISION_BLOCKERS=x,y,radius[,min_z,max_z];...
      SIM_LOS_BLOCKERS=x,y,radius;...
    """

    blockers: list[TacticalBlocker] = []
    blockers.extend(_read_named_blockers(os.environ.get("SIM_TACTICAL_BLOCKERS", ""), min_z, max_z))
    blockers.extend(_read_unnamed_blockers("collision", os.environ.get("SIM_COLLISION_BLOCKERS", ""), min_z, max_z))
    blockers.extend(_read_unnamed_blockers("los", os.environ.get("SIM_LOS_BLOCKERS", ""), min_z, max_z))
    deduped: dict[tuple[int, int, int], TacticalBlocker] = {}
    for blocker in blockers:
        key = (round(blocker.x), round(blocker.y), round(blocker.radius))
        deduped.setdefault(key, blocker)
    return tuple(deduped.values())


def _read_named_blockers(value: str, default_min_z: float, default_max_z: float) -> list[TacticalBlocker]:
    blockers = []
    for index, item in enumerate(part.strip() for part in value.split(";")):
        if not item:
            continue
        parts = [part.strip() for part in item.split(",")]
        try:
            if len(parts) == 4:
                name = parts[0] or f"tactical_{index}"
                x, y, radius = (float(parts[1]), float(parts[2]), float(parts[3]))
                min_z, max_z = default_min_z, default_max_z
            elif len(parts) == 6:
                name = parts[0] or f"tactical_{index}"
                x, y, radius, min_z, max_z = (
                    float(parts[1]),
                    float(parts[2]),
                    float(parts[3]),
                    float(parts[4]),
                    float(parts[5]),
                )
            else:
                continue
            blockers.append(TacticalBlocker(name, x, y, max(0.0, radius), min(min_z, max_z), max(min_z, max_z)))
        except ValueError:
            continue
    return blockers


def _read_unnamed_blockers(prefix: str, value: str, default_min_z: float, default_max_z: float) -> list[TacticalBlocker]:
    blockers = []
    for index, item in enumerate(part.strip() for part in value.split(";")):
        if not item:
            continue
        try:
            parts = [float(part.strip()) for part in item.split(",")]
            if len(parts) == 3:
                min_z, max_z = default_min_z, default_max_z
            elif len(parts) == 5:
                min_z, max_z = parts[3], parts[4]
            else:
                continue
            blockers.append(
                TacticalBlocker(
                    name=f"{prefix}_{index}",
                    x=parts[0],
                    y=parts[1],
                    radius=max(0.0, parts[2]),
                    min_z=min(min_z, max_z),
                    max_z=max(min_z, max_z),
                )
            )
        except ValueError:
            continue
    return blockers
