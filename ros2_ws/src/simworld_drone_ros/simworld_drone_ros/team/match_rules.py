from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class MatchContact:
    """The red/blue contact that matters to the active match rules."""

    distance_cm: float
    red_id: str
    blue_id: str


class MatchRules:
    """Shared duel/team scoring rules for the chase bridge.

    Duel and team mode both ask this object which red/blue pair should count
    for catch distance. Team support can then exist without changing the core
    runner-vs-chaser scoring policy.
    """

    VALID_CATCH_MODES = {"primary", "any"}
    VALID_ROUND_MODES = {"tag", "red_elimination"}

    def __init__(self, team_mode: bool, catch_mode: str = "primary", round_mode: str = "tag") -> None:
        self.team_mode = bool(team_mode)
        self.catch_mode = self.normalize_catch_mode(catch_mode)
        self.round_mode = self.normalize_round_mode(round_mode)

    @classmethod
    def normalize_catch_mode(cls, catch_mode: str | None) -> str:
        normalized = (catch_mode or "primary").strip().lower()
        if normalized not in cls.VALID_CATCH_MODES:
            return "primary"
        return normalized

    @classmethod
    def normalize_round_mode(cls, round_mode: str | None) -> str:
        normalized = (round_mode or "tag").strip().lower()
        if normalized in {"elimination", "red-elimination", "red_elim"}:
            normalized = "red_elimination"
        if normalized not in cls.VALID_ROUND_MODES:
            return "tag"
        return normalized

    @property
    def scoring_mode(self) -> str:
        if not self.team_mode:
            return "duel"
        if self.round_mode == "red_elimination":
            return "red_elimination"
        return self.catch_mode

    @staticmethod
    def distance(first: dict, second: dict) -> float:
        return math.sqrt(
            (first["x"] - second["x"]) ** 2
            + (first["y"] - second["y"]) ** 2
            + (first["z"] - second["z"]) ** 2
        )

    def scoring_contact(
        self,
        actors: list[dict],
        primary_red: dict,
        primary_blue: dict,
        excluded_ids: set[str] | None = None,
    ) -> MatchContact:
        excluded = excluded_ids or set()
        if not self.team_mode or (self.catch_mode == "primary" and self.round_mode != "red_elimination"):
            return MatchContact(
                distance_cm=self.distance(primary_red, primary_blue),
                red_id=primary_red["id"],
                blue_id=primary_blue["id"],
            )

        red_candidates = [
            actor
            for actor in actors
            if actor.get("team") == "red" and actor["id"] not in excluded
        ]
        if self.round_mode == "red_elimination" and any(red["id"] != primary_red["id"] for red in red_candidates):
            red_candidates = [red for red in red_candidates if red["id"] != primary_red["id"]]

        best_distance = float("inf")
        best_red = primary_red
        best_blue = primary_blue
        for red in red_candidates:
            blue_candidates = (
                [primary_blue]
                if self.round_mode == "red_elimination" and red["id"] == primary_red["id"]
                else [actor for actor in actors if actor.get("team") == "blue" and actor["id"] not in excluded]
            )
            for blue in blue_candidates:
                distance = self.distance(red, blue)
                if distance < best_distance:
                    best_distance = distance
                    best_red = red
                    best_blue = blue
        return MatchContact(distance_cm=best_distance, red_id=best_red["id"], blue_id=best_blue["id"])
