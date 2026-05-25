# Current Phase

## Phase 1 / 2A / 2B / 3 Done Baseline

The project is past the basic chase prototype and the one-vs-one tactical upgrade. It now has a working red-vs-white drone chase loop with ROS control, SimWorld bridge movement, target/chaser brains, Ollama-assisted tactic choices, fair resets, compact status watching, 3D altitude movement, and live support-drone team behavior.

Status:

- Phase 1 is done: basic spawn/control/chase loop exists.
- Phase 2A is done: one-vs-one tactics, LOS, memory, stamina, heat, AI tactics, and compact logs exist.
- Phase 2B is done for current scope: altitude-aware duel behavior, bounded vertical velocity, climb/dive/level tactics, chaser altitude following, and simple blocker/arena guard behavior exist.
- Phase 3 is done for current scope: team support up to 5v5 exists with red/blue coordinators, scoped support controllers, dynamic roles, spacing, screen clearing, search lanes, and red-elimination support.
- Phases 4, 5, and 6 are not committed implementation phases yet. They are future scope.

The strongest baseline remains the primary red_1 vs blue_1 duel brains, with team support layered on top when a saved team config exists.

## Current Direction

Current work is not about reopening Phase 2B or Phase 3. The focus is stability and tuning:

- clean process lifecycle
- no stale duplicate brain nodes
- reliable source-module launch scripts
- direct UnrealCV movement guards when swept Unreal movement is unavailable
- better measured arena bounds and blocker configuration
- readable logs for team-vs-team tests

## Recently Restored / Confirmed

- Launch scripts run source modules with `python -m simworld_drone_ros...` instead of old installed ROS console entry points.
- `stop_chase.cmd` publishes `stop_all` and cleans stale source-module and old installed entry-point processes such as `chaser_brain.exe` and `chaser_brain-script.py`.
- The bridge can load saved team sizes and adopt existing manual drones up to 5v5.
- Red_1 and blue_1 use the duel brains; support drones use team roles.
- Red support can screen, decoy, hide, or bait.
- Blue support can flank, clear screens, cut off lanes, deny center, or split into search lanes.
- Red-elimination mode eliminates support reds first; red_1 is finished last by blue_1.
- Eliminated red drones drop to `SIM_TEAM_ELIMINATION_GROUND_Z`, default `0`, and are held out until reset.
- The bridge uses a software arena guard for direct UnrealCV movement:
  - `SIM_TARGET_BOUND_X=1350`
  - `SIM_TARGET_BOUND_Y=1350`
  - `SIM_ARENA_BOUNDARY_MARGIN_CM=90`
- Swept Unreal movement is still attempted when available, but current UnrealCV runs may fall back to direct location updates.

## Known Issues

- Direct UnrealCV movement cannot use real Unreal mesh collision. Software bounds, drone spacing, and configured blockers are the current workaround.
- Measured arena bounds may need tuning if the visible main wall does not match the `1350/1350/90` default.
- Red-elimination is functional, but there is no full match manager with scoreboard, timers, summaries, or replay metrics yet.
- Support drones do not yet have per-drone stamina/heat.
- Real Unreal raycast perception is not implemented yet.

## Next Practical Step

Run a clean test:

```powershell
.\scripts\DroneROS\stop_chase.cmd
```

Then restart bridge, target brain, chaser brain, and start the chase. If movement looks wrong, first check for duplicate brain processes, then check the bridge arena guard line and the watcher’s actual-speed output.
