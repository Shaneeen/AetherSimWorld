from __future__ import annotations

from dataclasses import dataclass, field
import os


@dataclass(frozen=True)
class TeamDrone:
    """Configuration for one drone in a team-vs-team match."""

    name: str
    team: str
    pose_topic: str
    cmd_topic: str
    role_topic: str


@dataclass
class TeamPlan:
    """A coordinator decision that can be sent to individual drone controllers."""

    team: str
    focus_enemy: str | None = None
    roles: dict[str, str] = field(default_factory=dict)
    rationale: str = ""


@dataclass(frozen=True)
class TeamSpeedProfile:
    """Team-level speed profile chosen during match setup."""

    team: str
    model_reference: str
    speeds: dict[str, float]


def _read_int_env(name: str, default: int, minimum: int = 1, maximum: int = 5) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        number = int(float(value))
    except ValueError:
        return default
    return max(minimum, min(maximum, number))


def _read_float_env(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def team_size(team: str) -> int:
    normalized = team.strip().lower()
    if normalized == "red":
        return _read_int_env("SIM_RED_TEAM_SIZE", 1)
    return _read_int_env("SIM_BLUE_TEAM_SIZE", 1)


def build_team(team: str, size: int | None = None) -> tuple[TeamDrone, ...]:
    normalized = team.strip().lower()
    count = team_size(normalized) if size is None else max(1, min(5, int(size)))
    return tuple(
        TeamDrone(
            name=f"{normalized}_{index}",
            team=normalized,
            pose_topic=f"/team/{normalized}/{normalized}_{index}/pose",
            cmd_topic=f"/team/{normalized}/{normalized}_{index}/cmd_vel",
            role_topic=f"/team/{normalized}/{normalized}_{index}/role",
        )
        for index in range(1, count + 1)
    )


def read_team_speed_profile(team: str) -> TeamSpeedProfile:
    normalized = team.strip().lower()
    if normalized == "red":
        speeds = {
            "cruise": _read_float_env("SIM_RED_CRUISE_SPEED", 235.0),
            "evade": _read_float_env("SIM_RED_EVADE_SPEED", 285.0),
            "burst": _read_float_env("SIM_RED_BURST_SPEED", 365.0),
        }
    else:
        speeds = {
            "base": _read_float_env("SIM_BLUE_BASE_SPEED", 250.0),
            "intercept": _read_float_env("SIM_BLUE_INTERCEPT_SPEED", 285.0),
            "search": _read_float_env("SIM_BLUE_SEARCH_SPEED", 190.0),
        }
    model_reference = os.environ.get(f"SIM_{normalized.upper()}_MODEL_REFERENCE", "default")
    return TeamSpeedProfile(team=normalized, model_reference=model_reference, speeds=speeds)


DEFAULT_RED_TEAM = build_team("red", 2)
DEFAULT_BLUE_TEAM = build_team("blue", 2)
