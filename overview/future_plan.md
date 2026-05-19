# Future Plan

This roadmap is ordered by what should be built next, not by how ambitious the final project sounds.

## Simple Roadmap

| Order | Phase | Name | Main Goal | Status |
| --- | --- | --- | --- | --- |
| 1 | Phase 1 | Basic chase prototype | Spawn two drones and make one chase one target | Done |
| 2 | Phase 2A | One-vs-one tactical upgrade | Make the current chase believable with LOS, memory, AI tactics, stamina, heat, and compact logs | Done |
| 3 | Phase 2B | Basic 3D movement | Add altitude control and climb/dive tactics while still one-vs-one | In progress |
| 4 | Phase 3 | Small team tactics | Move to red-vs-white 2v2, then 3v3, with dynamic temporary roles | Later |
| 5 | Phase 4 | Round and scoring loop | Add repeatable rounds, timers, score, summaries, and presets | Later |
| 6 | Phase 5 | Better perception and obstacle intelligence | Improve obstacle/LOS logic, cover use, gate/window routes, and search zones | Later |
| 7 | Phase 6 | Larger tactical sandbox | Scale toward bigger multi-agent red-vs-white experiments | Future |

## Phase 2B - Basic 3D Movement

Goal: make the existing one-vs-one baseline support believable up/down movement before adding teams.

The correct structure is:

```text
LLM chooses tactic
rule-based controller converts tactic into x/y/z velocity
normal code enforces altitude, speed, stamina, heat, and safety limits
```

Do not let the LLM directly control raw `x/y/z` velocity every frame.

Tasks:

- track each drone's current altitude - started
- add vertical velocity control through `cmd.linear.z` - started
- add altitude limits - started:
  - minimum safe altitude
  - maximum safe altitude
  - preferred cruising altitude
- add smooth climb/dive behavior instead of instant height jumps - started
- add simple height-aware tactics - started:
  - `level_escape` - started
  - `climb_escape` - started
  - `dive_escape` - started
  - `spiral_evade`
  - `climb_over_obstacle`
  - `drop_under_los`
- let target/chaser tactics include an altitude bias - started
- make target vary height when panicking
- keep all height movement rule-based at first

Recommended first version:

```text
When target sees chaser:
- move away horizontally
- choose climb, dive, or level every few seconds
- avoid boundaries
- respect stamina and altitude limits
```

Do not add full 3D pathfinding in this phase.

## Phase 3 - Small Team Tactics

Goal: move from one chaser vs one target into small red-vs-white team behavior.

Recommended starting size:

- 2v2 first
- then 3v3

Avoid starting with 10v10 because debugging will become too hard too early.

Important design rule:

Roles should not be permanently assigned. The AI should choose temporary roles during the round based on state.

Example temporary roles:

- pressure
- cutoff
- search
- runner
- bait
- hide
- guard
- support

Tasks:

- add multiple drones per team
- keep teams as red and white
- add shared team state
- add team-level strategy output
- add temporary role assignment
- reuse the Phase 2B vertical controller for every drone
- add search/lost-target behavior per drone
- keep stamina, heat, and boost per drone
- avoid fixed permanent roles like "red_1 is always bait"

## Phase 4 - Round and Scoring Loop

Goal: make the simulator repeatable and measurable.

Tasks:

- round start/end system
- reset and spawn manager
- scorekeeping
- match timer
- configurable difficulty presets
- round result summary
- replay/log metrics
- debug HUD or compact telemetry overlay

Win condition direction:

- white wins by catch radius plus hold time
- red wins by surviving until timer ends
- optional red win by reaching an escape objective if map size supports it

For the current small map, survival/catch-hold is probably better than a large protected-area objective.

## Phase 5 - Better Perception and Obstacle Intelligence

Goal: make drones feel like they can see, remember, lose, search, predict, and use the arena.

Tasks:

- replace simple geometric blockers with real SimWorld/Unreal line traces if available
- add stronger field-of-view and occlusion logic
- add last-seen confidence
- improve predicted enemy path
- add search zones
- add simple obstacle-cover scoring
- add height-difference scoring for line-of-sight breaks
- add manual gate/window/bridge waypoints for arena features
- let drones choose obvious gates or wide tunnels when those routes are safer
- add commander-level strategy
- optionally add camera/image-based reasoning for high-level decisions

Arena guidance:

- prefer big readable gates/windows over small random holes
- use tall pillars for line-of-sight hiding
- use low walls for climb-over behavior
- use bridge/tunnel structures for over/under choices
- manually define 3-5 obvious gate points in code before attempting automatic mesh hole detection

Avoid for now:

- full voxel maps
- full 3D A* pathfinding
- automatic detection of small holes in arbitrary meshes
- high-speed flight through narrow holes

Good use of vision AI:

- decide whether a target is visible
- identify blocked routes
- choose safe route or search area

Bad use of vision AI:

- controlling every frame directly

## Phase 6 - Larger Red-vs-White Sandbox

Goal: expand into a larger tactical experiment platform.

Tasks:

- 5v5 or larger teams if performance allows
- multiple objectives
- dynamic role switching
- team communication
- territory control
- commander AI layer
- height-aware team tactics
- different drone behavior classes
- richer scoring and metrics

Possible objective types:

- survive
- catch and hold
- escort
- defend zone
- capture zone
- retrieve objective
- eliminate marked drone

## Recommended Immediate Next Work

1. Add Phase 2B basic vertical velocity and altitude limits.
2. Add simple climb/dive/level tactics for the one-vs-one baseline.
3. Keep live testing with compact watcher plus saved detail logs.
4. Start 2v2 shared team state after 3D movement works.
5. Add catch hold/survive timer once the project goal is clearer.
6. Save gate/window/bridge waypoint logic for Phase 5.
