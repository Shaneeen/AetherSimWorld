from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
import re
import threading
import time
import tkinter as tk
from tkinter import ttk

from geometry_msgs.msg import PoseStamped, Twist
import rclpy
from rclpy.node import Node
from std_msgs.msg import String


MAX_TEAM_SIZE = 5
PULSE_SECONDS = 0.9

TEAM_COLORS = {
    "blue": {
        "label": "CHASER",
        "base": "#14243c",
        "active": "#1f80ff",
        "pulse": "#5fd0ff",
        "text": "#d9ecff",
    },
    "red": {
        "label": "TARGET",
        "base": "#3a181a",
        "active": "#ff5c5c",
        "pulse": "#ffb15f",
        "text": "#ffe4e4",
    },
}


@dataclass
class DroneCard:
    name: str
    team: str
    index: int
    actor: str
    active: bool
    role: str = "waiting"
    action: str = "idle"
    detail: str = "no signal"
    pose: tuple[float, float, float] | None = None
    last_pose_at: float = 0.0
    last_action_at: float = 0.0


def _team_size(name: str) -> int:
    env_name = "SIM_BLUE_TEAM_SIZE" if name == "blue" else "SIM_RED_TEAM_SIZE"
    try:
        return max(1, min(MAX_TEAM_SIZE, int(float(os.environ.get(env_name, "1")))))
    except ValueError:
        return 1


def _actor_name(team: str, index: int) -> str:
    base = "DroneB" if team == "blue" else "DroneA"
    return base if index == 1 else f"{base}{index - 1}"


def _shorten(text: str, limit: int = 86) -> str:
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _extract_json_between(text: str, prefix: str, suffix: str | None = None) -> dict:
    start = text.find(prefix)
    if start < 0:
        return {}
    start += len(prefix)
    end = text.find(suffix, start) if suffix else -1
    blob = text[start:] if end < 0 else text[start:end]
    try:
        data = json.loads(blob.strip())
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _extract_field(text: str, field: str) -> str:
    match = re.search(rf"{re.escape(field)}=([^,\s]+)", text)
    return match.group(1) if match else ""


def _command_action(msg: Twist) -> str:
    x = float(msg.linear.x)
    y = float(msg.linear.y)
    z = float(msg.linear.z)
    speed_xy = math.hypot(x, y)
    parts: list[str] = []

    if speed_xy > 4.0:
        vertical = "N" if x >= 0 else "S"
        horizontal = "E" if y >= 0 else "W"
        if abs(x) < speed_xy * 0.35:
            direction = horizontal
        elif abs(y) < speed_xy * 0.35:
            direction = vertical
        else:
            direction = vertical + horizontal
        parts.append(f"move {direction}")

    if z > 4.0:
        parts.append("climb")
    elif z < -4.0:
        parts.append("descend")

    return " + ".join(parts) if parts else "hold"


class TeamPanelNode(Node):
    def __init__(self) -> None:
        super().__init__("simworld_team_panel")
        self.lock = threading.Lock()
        self.cards: dict[str, DroneCard] = {}
        self.last_status = "waiting for /sim/status"
        self._kept_subscriptions = []

        for team in ("blue", "red"):
            size = _team_size(team)
            for index in range(1, MAX_TEAM_SIZE + 1):
                name = f"{team}_{index}"
                self.cards[name] = DroneCard(
                    name=name,
                    team=team,
                    index=index,
                    actor=_actor_name(team, index),
                    active=index <= size,
                )

        self._kept_subscriptions.append(self.create_subscription(String, "/sim/status", self._status_callback, 50))
        self._watch_primary("red_1", "/drone_a/pose", "/drone_a/cmd_vel")
        self._watch_primary("blue_1", "/drone_b/pose", "/drone_b/cmd_vel")

        for team in ("red", "blue"):
            for index in range(1, MAX_TEAM_SIZE + 1):
                name = f"{team}_{index}"
                self._kept_subscriptions.append(
                    self.create_subscription(
                        PoseStamped,
                        f"/team/{team}/{name}/pose",
                        lambda msg, selected=name: self._pose_callback(selected, msg),
                        10,
                    )
                )
                self._kept_subscriptions.append(
                    self.create_subscription(
                        Twist,
                        f"/team/{team}/{name}/cmd_vel",
                        lambda msg, selected=name: self._cmd_callback(selected, msg),
                        10,
                    )
                )
                self._kept_subscriptions.append(
                    self.create_subscription(
                        String,
                        f"/team/{team}/{name}/role",
                        lambda msg, selected=name: self._role_callback(selected, msg),
                        10,
                    )
                )

    def _watch_primary(self, name: str, pose_topic: str, cmd_topic: str) -> None:
        self._kept_subscriptions.append(
            self.create_subscription(
                PoseStamped,
                pose_topic,
                lambda msg, selected=name: self._pose_callback(selected, msg),
                10,
            )
        )
        self._kept_subscriptions.append(
            self.create_subscription(Twist, cmd_topic, lambda msg, selected=name: self._cmd_callback(selected, msg), 10)
        )

    def snapshot(self) -> tuple[dict[str, DroneCard], str]:
        with self.lock:
            return {name: DroneCard(**vars(card)) for name, card in self.cards.items()}, self.last_status

    def _mark_action(self, name: str, action: str, detail: str = "") -> None:
        card = self.cards.get(name)
        if card is None:
            return
        card.action = _shorten(action, 34)
        if detail:
            card.detail = _shorten(detail)
        card.last_action_at = time.time()

    def _pose_callback(self, name: str, msg: PoseStamped) -> None:
        with self.lock:
            card = self.cards.get(name)
            if card is None:
                return
            card.pose = (
                float(msg.pose.position.x),
                float(msg.pose.position.y),
                float(msg.pose.position.z),
            )
            card.last_pose_at = time.time()
            if card.detail == "no signal":
                card.detail = "pose online"

    def _cmd_callback(self, name: str, msg: Twist) -> None:
        with self.lock:
            self._mark_action(name, _command_action(msg), "command fired")

    def _role_callback(self, name: str, msg: String) -> None:
        with self.lock:
            try:
                payload = json.loads(msg.data)
            except json.JSONDecodeError:
                payload = {}
            role = payload.get("role") if isinstance(payload, dict) else None
            if not role:
                return
            card = self.cards.get(name)
            if card is None:
                return
            card.role = str(role)
            self._mark_action(name, str(role), "role assigned")

    def _status_callback(self, msg: String) -> None:
        text = msg.data
        with self.lock:
            self.last_status = _shorten(text, 150)
            self._parse_status(text)

    def _parse_status(self, text: str) -> None:
        if text.startswith("Target brain move phase:"):
            tactic = _extract_field(text, "tactic") or "evade"
            strategy = _extract_field(text, "strategy")
            threat = _extract_field(text, "threat")
            detail = ", ".join(part for part in (strategy, f"threat {threat}" if threat else "") if part)
            self._mark_action("red_1", tactic, detail)
            self.cards["red_1"].role = "runner"
            return

        if text.startswith("Target brain rest phase:"):
            self._mark_action("red_1", "rest", text)
            self.cards["red_1"].role = "runner"
            return

        if text.startswith("Chaser brain commit"):
            tactic = _extract_field(text, "tactic") or "intercept"
            strategy = _extract_field(text, "strategy")
            self._mark_action("blue_1", tactic, strategy)
            self.cards["blue_1"].role = "lead chaser"
            return

        if text.startswith("Chaser brain catch zone reached"):
            self._mark_action("blue_1", "catch zone", text)
            self.cards["blue_1"].role = "lead chaser"
            return

        if text.startswith("Team coordinator plan:"):
            team = _extract_field(text, "team")
            roles = _extract_json_between(text, "roles=", ", reason=")
            for name, role in roles.items():
                card = self.cards.get(name)
                if card is None:
                    continue
                card.role = str(role)
                if team and name.startswith(f"{team}_"):
                    self._mark_action(name, str(role), "coordinator plan")
            return

        if text.startswith("Team support active:"):
            roles = _extract_json_between(text, "roles=", ", intent=")
            intents = _extract_json_between(text, "intent=")
            for name, role in roles.items():
                card = self.cards.get(name)
                if card is None:
                    continue
                card.role = str(role)
                intent = str(intents.get(name, "tracking role"))
                self._mark_action(name, str(role), intent)
            return

        if text.startswith("Team support ready:"):
            scope = _extract_field(text, "scope") or "team"
            for card in self.cards.values():
                if card.active and (scope == "all" or card.team == scope):
                    card.detail = "support ready"


class TeamPanelApp:
    def __init__(self, node: TeamPanelNode) -> None:
        self.node = node
        self.root = tk.Tk()
        self.root.title("SimWorld Drone Team Panel")
        self.root.geometry("1220x640")
        self.root.minsize(980, 560)
        self.root.configure(bg="#0d1117")
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Panel.TFrame", background="#0d1117")
        style.configure("Section.TFrame", background="#0d1117")
        style.configure("Header.TLabel", background="#0d1117", foreground="#f0f6fc", font=("Segoe UI", 17, "bold"))
        style.configure("Status.TLabel", background="#0d1117", foreground="#8b949e", font=("Segoe UI", 10))

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)
        self.root.rowconfigure(2, weight=1)

        title = ttk.Label(
            self.root,
            text="SimWorld 5v5 Drone Panel",
            style="Header.TLabel",
            anchor="center",
        )
        title.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 4))

        self.sections = {
            "blue": self._build_section(1, "blue"),
            "red": self._build_section(2, "red"),
        }
        self.status_var = tk.StringVar(value="waiting for /sim/status")
        status = ttk.Label(self.root, textvariable=self.status_var, style="Status.TLabel", anchor="w")
        status.grid(row=3, column=0, sticky="ew", padx=18, pady=(2, 10))

    def _build_section(self, row: int, team: str) -> dict[str, dict[str, tk.Widget | tk.StringVar]]:
        colors = TEAM_COLORS[team]
        frame = ttk.Frame(self.root, style="Section.TFrame")
        frame.grid(row=row, column=0, sticky="nsew", padx=18, pady=8)
        frame.columnconfigure(tuple(range(MAX_TEAM_SIZE)), weight=1, uniform=team)
        frame.rowconfigure(1, weight=1)

        header = ttk.Label(
            frame,
            text=f"{colors['label']} / {team.upper()}",
            style="Header.TLabel",
            anchor="w",
        )
        header.grid(row=0, column=0, columnspan=MAX_TEAM_SIZE, sticky="ew", pady=(0, 8))

        widgets: dict[str, dict[str, tk.Widget | tk.StringVar]] = {}
        for index in range(1, MAX_TEAM_SIZE + 1):
            name = f"{team}_{index}"
            card = tk.Frame(frame, bg=colors["base"], bd=0, highlightthickness=2, highlightbackground="#30363d")
            card.grid(row=1, column=index - 1, sticky="nsew", padx=5)
            card.columnconfigure(0, weight=1)

            name_var = tk.StringVar()
            role_var = tk.StringVar()
            action_var = tk.StringVar()
            detail_var = tk.StringVar()
            pose_var = tk.StringVar()

            tk.Label(card, textvariable=name_var, bg=colors["base"], fg=colors["text"], font=("Segoe UI", 12, "bold")).grid(
                row=0, column=0, sticky="ew", padx=10, pady=(10, 2)
            )
            tk.Label(card, textvariable=action_var, bg=colors["base"], fg="#ffffff", font=("Segoe UI", 15, "bold")).grid(
                row=1, column=0, sticky="ew", padx=10, pady=(4, 2)
            )
            tk.Label(card, textvariable=role_var, bg=colors["base"], fg="#c9d1d9", font=("Segoe UI", 10)).grid(
                row=2, column=0, sticky="ew", padx=10, pady=(0, 2)
            )
            tk.Label(card, textvariable=detail_var, bg=colors["base"], fg="#9da7b3", font=("Segoe UI", 9), wraplength=190).grid(
                row=3, column=0, sticky="ew", padx=10, pady=(5, 2)
            )
            tk.Label(card, textvariable=pose_var, bg=colors["base"], fg="#7d8590", font=("Consolas", 9)).grid(
                row=4, column=0, sticky="ew", padx=10, pady=(4, 10)
            )

            widgets[name] = {
                "card": card,
                "name": name_var,
                "role": role_var,
                "action": action_var,
                "detail": detail_var,
                "pose": pose_var,
            }
        return widgets

    def run(self) -> None:
        self._refresh()
        self.root.mainloop()

    def close(self) -> None:
        self.root.quit()
        self.root.destroy()

    def _refresh(self) -> None:
        snapshot, status = self.node.snapshot()
        self.status_var.set(status)
        now = time.time()
        for name, card in snapshot.items():
            widgets = self.sections[card.team][name]
            colors = TEAM_COLORS[card.team]
            pulse_age = now - card.last_action_at
            if not card.active:
                bg = "#161b22"
                outline = "#30363d"
            elif pulse_age < PULSE_SECONDS:
                bg = colors["pulse"]
                outline = colors["active"]
            else:
                bg = colors["base"]
                outline = "#30363d"

            frame = widgets["card"]
            assert isinstance(frame, tk.Frame)
            frame.configure(bg=bg, highlightbackground=outline)
            for child in frame.winfo_children():
                child.configure(bg=bg)

            widgets["name"].set(f"{card.actor}  ({card.name})" if card.active else f"empty slot {card.index}")
            widgets["action"].set(card.action if card.active else "unused")
            widgets["role"].set(f"role: {card.role}" if card.active else "")
            widgets["detail"].set(card.detail if card.active else "")
            if card.pose and card.active:
                age = now - card.last_pose_at
                widgets["pose"].set(f"x {card.pose[0]:.0f}  y {card.pose[1]:.0f}  z {card.pose[2]:.0f}  {age:.1f}s")
            else:
                widgets["pose"].set("no pose" if card.active else "")

        self.root.after(100, self._refresh)


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = TeamPanelNode()
    spin_thread = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
    spin_thread.start()
    app = TeamPanelApp(node)
    try:
        app.run()
    finally:
        rclpy.shutdown()
        spin_thread.join(timeout=1.0)
        node.destroy_node()


if __name__ == "__main__":
    main()
