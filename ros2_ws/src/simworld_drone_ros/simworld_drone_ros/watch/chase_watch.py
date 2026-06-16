import os
import re
import time
from datetime import datetime
from pathlib import Path

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class ChaseWatch(Node):
    def __init__(self) -> None:
        super().__init__("chase_watch")
        self.sub = self.create_subscription(String, "/sim/status", self.status_callback, 50)
        self.last_by_key = {}
        self.started_at = time.time()
        self.last_message_at = None
        self.target = {}
        self.chaser = {}
        self.last_summary = ""
        self.last_display_state = {}
        self.team_mode = False
        self.detail_log = self._open_detail_log()
        self.summary_timer = self.create_timer(5.0, self.summary_tick)

    def _open_detail_log(self):
        log_dir = Path(os.environ.get("SIM_CHASE_WATCH_LOG_DIR", "C:/CodeSimWorld/AetherSimWorld/logs/chase_watch"))
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / f"chase_detail_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        existing = sorted(log_dir.glob("chase_detail_*.log"), key=lambda item: item.stat().st_mtime)
        for old_path in existing[:-1]:
            try:
                old_path.unlink()
            except OSError:
                pass
        handle = path.open("a", encoding="utf-8")
        handle.write(f"# Chase detail log started {datetime.now().isoformat(timespec='seconds')}\n")
        handle.flush()
        print(f"Detailed log: {path}", flush=True)
        return handle

    def _stamp(self) -> str:
        return f"{time.time() - self.started_at:6.1f}s"

    def _log_detail(self, text: str) -> None:
        self.detail_log.write(f"[{self._stamp()}] {text}\n")
        self.detail_log.flush()

    def _emit(self, key: str, text: str, cooldown: float = 0.0, display: bool = True) -> None:
        now = time.time()
        last = self.last_by_key.get(key)
        if last and last[0] == text and now - last[1] < cooldown:
            return
        self.last_by_key[key] = (text, now)
        self._log_detail(f"EVENT {text}")
        if display:
            print(f"[{self._stamp()}] {text}", flush=True)

    def _display_changed(self, key: str, value: str, cooldown: float) -> bool:
        now = time.time()
        last = self.last_display_state.get(key)
        if last is None or last[0] != value or now - last[1] >= cooldown:
            self.last_display_state[key] = (value, now)
            return True
        return False

    def _plain_tactic(self, tactic: str) -> str:
        return tactic.replace("[cached]", "")

    def _tactic_group(self, tactic: str) -> str:
        plain = self._plain_tactic(tactic)
        if plain.startswith("cutoff_"):
            return "cutoff"
        if plain.startswith("juke_"):
            return "juke"
        return plain

    def status_callback(self, msg: String) -> None:
        text = msg.data.strip()
        lower = text.lower()
        self.last_message_at = time.time()
        self._log_detail(f"RAW {text}")

        if "chase start reset" in lower:
            match = re.search(r"distance_cm=([0-9.]+)", text)
            suffix = f" start distance {match.group(1)} cm" if match else ""
            self._emit("reset", f"RESET:{suffix}")
            return

        if "brain ready" in lower:
            who = "TARGET" if text.startswith("Target") else "CHASER" if text.startswith("Chaser") else "SYS"
            self._emit(f"ready:{who}", f"{who}: ready")
            return

        if lower.startswith("team bridge ready") or lower.startswith("team support ready"):
            self.team_mode = True
            self._emit("team_ready", f"TEAM: {text}", cooldown=3.0)
            return

        if lower.startswith("team support received") or lower.startswith("team support active"):
            self.team_mode = True
            self._emit("team_support", f"TEAM: {text}", cooldown=5.0)
            return

        if "received start" in lower:
            who = "TARGET" if text.startswith("Target") else "CHASER" if text.startswith("Chaser") else "SYS"
            self._emit(f"start:{who}", f"{who}: started", cooldown=2.0)
            return

        if "received stop" in lower:
            who = "TARGET" if text.startswith("Target") else "CHASER" if text.startswith("Chaser") else "SYS"
            self._emit(f"stop:{who}", f"{who}: stopped", cooldown=2.0)
            return

        if "ollama fallback" in lower:
            reason = text.split("fallback:", 1)[-1].strip()
            reason = re.sub(r"; retrying in \d+s", "", reason)
            if text.startswith("Team coordinator"):
                who = "PLANNER"
                self._state(who)["ai"] = "fallback"
                self._emit(
                    f"planner_fallback:{reason[:80]}",
                    f"PLANNER: live role planner fallback - {reason}",
                    cooldown=5.0,
                )
            else:
                who = "TARGET" if text.startswith("Target") else "CHASER"
                self._state(who)["ai"] = "fallback"
                self._emit(f"ai_fail:{who}", f"{who}: duel Ollama fallback - {reason}", cooldown=5.0)
            return

        if "visibility:" in lower:
            who = "TARGET" if text.startswith("Target") else "CHASER" if text.startswith("Chaser") else "SYS"
            event = text.split("visibility:", 1)[-1].strip()
            self._state(who)["visibility"] = event
            self._emit(f"visibility:{who}", f"{who}: {event}", cooldown=5.0)
            return

        if lower.startswith("vision scene:"):
            observer = self._field(text, "observer") or "unknown"
            source = self._field(text, "source") or "vision"
            visible = self._field(text, "runner_visible") or "unknown"
            blocked_by = self._field(text, "blocked_by") or "none"
            search = self._field(text, "search") or "none"
            confidence = self._field(text, "confidence") or "0.00"
            self._emit(
                "vision_scene",
                f"VISION: {observer} {source}, runner_visible={visible}, blocked_by={blocked_by}, search={search}, confidence={confidence}",
                cooldown=2.0,
            )
            return

        if "cached ollama" in lower:
            who = "TARGET" if text.startswith("Target") else "CHASER"
            strategy = self._field(text, "strategy") or "unknown"
            tactic = self._field(text, "tactic") or "unknown"
            self._state(who)["ai"] = f"{strategy}->{tactic}"
            self._emit(f"ai:{who}", f"{who}: AI chose {strategy} -> {tactic}")
            return

        if "commit strategy" in lower:
            strategy = self._field(text, "strategy") or "unknown"
            tactic = self._field(text, "tactic") or "unknown"
            display_tactic = self._plain_tactic(tactic)
            visible = self._field(text, "visible")
            reason = self._field(text, "visibility_reason") or "unknown"
            distance = self._field(text, "distance_cm") or "unknown"
            heat = self._field(text, "heat")
            thermal = self._field(text, "thermal")
            self.chaser["strategy"] = strategy
            self.chaser["tactic"] = tactic
            if visible is not None:
                sight = "sees target" if visible == "1" else f"no sight ({reason})"
                if distance:
                    sight = f"{sight}, distance {distance} cm"
                self.chaser["visibility"] = sight
            if heat:
                self.chaser["resource"] = f"heat {heat} ({thermal or 'unknown'})"
            detail = []
            if self.chaser.get("visibility"):
                detail.append(self.chaser["visibility"])
            if self.chaser.get("resource"):
                detail.append(self.chaser["resource"])
            suffix = f", {', '.join(detail)}" if detail else ""
            display_state = f"{strategy}->{self._tactic_group(tactic)}:{visible}:{reason}:{thermal}"
            self._emit(
                "chaser_commit",
                f"CHASER: commits {strategy} -> {display_tactic}{suffix}",
                cooldown=0.0,
                display=self._display_changed("chaser_commit", display_state, 12.0),
            )
            return

        if "target brain move phase" in lower:
            strategy = self._field(text, "strategy") or "unknown"
            tactic = self._field(text, "tactic") or "unknown"
            display_tactic = self._plain_tactic(tactic)
            threat = self._field(text, "threat") or "unknown"
            visible = self._field(text, "visible")
            distance = self._field(text, "distance_cm")
            distance_source = self._field(text, "distance_source") or "live"
            stamina = self._field(text, "stamina")
            boost = self._field(text, "boost")
            actual_speed = self._field(text, "actual_speed")
            stuck = self._field(text, "stuck")
            seen = "sees chaser" if visible == "1" else "using memory"
            visibility = seen
            if distance != "unknown":
                label = "estimated distance" if distance_source == "memory" else "distance"
                visibility = f"{visibility}, {label} {distance} cm"
            resource_bits = []
            if stamina:
                resource_bits.append(f"stamina {stamina} ({boost or 'unknown'})")
            if actual_speed:
                resource_bits.append(f"actual {actual_speed} cm/s")
            if stuck == "1":
                resource_bits.append("unstucking")
            self.target.update(
                {
                    "strategy": strategy,
                    "tactic": tactic,
                    "threat": threat,
                    "seen": seen,
                    "visibility": visibility,
                    "distance": distance,
                    "resource": " | ".join(resource_bits) if resource_bits else None,
                }
            )
            resource = f", {self.target['resource']}" if self.target.get("resource") else ""
            display_state = f"{strategy}->{self._tactic_group(tactic)}:{threat}:{visible}:{boost}:{stuck}"
            self._emit(
                "target_move",
                f"TARGET: {strategy} -> {display_tactic}, {threat}, {seen}, distance {distance} cm{resource}",
                cooldown=0.0,
                display=self._display_changed("target_move", display_state, 12.0),
            )
            return

        if "catch zone reached" in lower:
            match = re.search(r"distance=([0-9.]+)", text)
            suffix = f" at {match.group(1)} cm" if match else ""
            self._emit("caught", f"CAUGHT:{suffix}")
            return

        if "ue bridge error" in lower or "spawn failed" in lower:
            self._emit("bridge_error", f"BRIDGE: {text}", cooldown=3.0)

    def _field(self, text: str, name: str) -> str | None:
        match = re.search(rf"{re.escape(name)}=([^,\s]+)", text)
        return match.group(1) if match else None

    def _state(self, who: str) -> dict:
        return self.target if who == "TARGET" else self.chaser

    def summary_tick(self) -> None:
        if self.last_message_at is None:
            self._emit("summary_wait", "WAITING: no /sim/status messages yet", cooldown=6.0)
            return
        if self.team_mode:
            return

        target_bits = []
        if self.target:
            target_bits.append(f"{self.target.get('strategy', '?')}->{self.target.get('tactic', '?')}")
            if self.target.get("threat"):
                target_bits.append(self.target["threat"])
            if self.target.get("visibility"):
                target_bits.append(self.target["visibility"])
            elif self.target.get("distance"):
                target_bits.append(f"{self.target['distance']} cm")
            if self.target.get("resource"):
                target_bits.append(self.target["resource"])
            if self.target.get("ai"):
                target_bits.append(f"AI {self.target['ai']}")
        else:
            target_bits.append("no target move yet")

        chaser_bits = []
        if self.chaser:
            if self.chaser.get("strategy") or self.chaser.get("tactic"):
                chaser_bits.append(f"{self.chaser.get('strategy', '?')}->{self.chaser.get('tactic', '?')}")
            if self.chaser.get("ai"):
                chaser_bits.append(f"AI {self.chaser['ai']}")
            if self.chaser.get("visibility"):
                chaser_bits.append(self.chaser["visibility"])
            if self.chaser.get("resource"):
                chaser_bits.append(self.chaser["resource"])
        else:
            chaser_bits.append("no chaser commit yet")

        summary = f"LIVE: TARGET {' | '.join(target_bits)} || CHASER {' | '.join(chaser_bits)}"
        self._emit("live", summary)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ChaseWatch()
    try:
        print("Watching /sim/status. Press Ctrl+C to stop.", flush=True)
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.detail_log.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
