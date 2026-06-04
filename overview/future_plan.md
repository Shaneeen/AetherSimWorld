# Future Plan

This roadmap is ordered by what should be built next. Phase 1, Phase 2A, Phase 2B, and Phase 3 are done for the current scope.

## Simple Roadmap

| Order | Phase | Name | Main Goal | Status |
| --- | --- | --- | --- | --- |
| 1 | Phase 1 | Basic chase prototype | Spawn/control two drones and run a chase | Done |
| 2 | Phase 2A | One-vs-one tactical upgrade | LOS, memory, AI tactics, stamina, heat, and compact logs | Done |
| 3 | Phase 2B | Duel 3D baseline | Altitude control, climb/dive tactics, and bounded vertical motion | Done |
| 4 | Phase 3 | Team-vs-team support | Red-vs-white support drones with coordinators and dynamic roles | Done |
| 5 | Phase 4 | Round and scoring loop | Repeatable rounds, timer, score, summaries, and presets | Future scope |
| 6 | Phase 5 | Better perception and obstacle intelligence | Real LOS/raycasting, better blockers, cover, gates, and search zones | Future scope |
| 7 | Phase 6 | Larger tactical sandbox | Bigger multi-agent experiments and richer objectives | Future scope |

## Phase 4 - Round and Scoring Loop

Status: future scope.

Goal: make matches repeatable and measurable.

Potential tasks:

- round start/end manager
- scorekeeping
- match timer
- configurable difficulty presets
- red-elimination summary
- debug HUD or compact telemetry overlay
- improve the current Drone Team Panel with score/timer summaries
- process-health checks that warn when duplicate target/chaser/bridge/team nodes are running
- one-command clean start that stops stale nodes, verifies no duplicates, then launches the current source-module stack

## Phase 5 - Better Perception and Obstacles

Status: future scope.

Goal: make drones use the actual arena more intelligently.

Potential tasks:

- replace simple geometric blockers with real SimWorld/Unreal line traces if available
- investigate whether the current UnrealCV runtime can expose swept movement or line trace support
- add rectangular/polygon blockers for wall-like map geometry
- add measured map presets for arena bounds, wall margins, and named cover blockers
- add search zones and last-seen confidence
- add height-difference scoring for line-of-sight breaks
- add manual gate/window/bridge waypoints
- let drones choose obvious gates/tunnels when safer

## Phase 6 - Larger Red-vs-White Sandbox

Status: future scope.

Potential tasks:

- 5v5 or larger teams if performance allows
- multiple objectives
- dynamic role switching
- team communication
- commander AI layer
- different drone behavior classes
- richer scoring and metrics

## Recommended Immediate Next Work

1. Run `.\launch\stop.cmd` before every fresh test.
2. Confirm no stale installed `target_brain.exe`, `chaser_brain.exe`, or `*-script.py` processes are alive.
3. Confirm the bridge log prints the arena guard line.
4. Run a clean 5v5 demo test through `.\launch\set_teams_5v5.cmd`, bridge, target, chaser, panel, and start.
5. Tune `SIM_TARGET_BOUND_X`, `SIM_TARGET_BOUND_Y`, and `SIM_ARENA_BOUNDARY_MARGIN_CM` if the visible wall does not match the current default.
6. Tune `SIM_TACTICAL_BLOCKERS` or `SIM_COLLISION_BLOCKERS` for actual cover objects after the basic lifecycle is clean.
