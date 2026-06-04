# Current Features

## Simulation Setup

- SimWorld can run the normal two-drone duel or a saved team match using existing manual drone actors up to 5v5.
- ROS bridge publishes drone pose/odom and accepts velocity commands.
- Primary drones:
  - red_1 / `DroneA` can use the target brain in normal duel mode.
  - blue_1 / `DroneB` can use the chaser brain in normal duel mode.
  - in the current 5v5 preset, team support controls both primaries too.
- Team support drones:
  - red_2-red_5 default to `DroneA1`-`DroneA4`.
  - blue_2-blue_5 default to `DroneB1`-`DroneB4`.
  - unused manual drones are parked near `(2800, 2800, 150)`.
- The source package is split by responsibility:
  - `bridge/`
  - `duel/`
  - `team/`
  - `control/`
  - `watch/`

## Movement And Collision

- Drones move in x/y/z.
- Default flight altitude bounds:
  - minimum Z: `100 cm`
  - maximum Z: `700 cm`
- Override with:
  - `SIMWORLD_DRONE_MIN_Z`
  - `SIMWORLD_DRONE_MAX_Z`
- The bridge attempts swept Unreal movement when available.
- If swept movement is unavailable, direct UnrealCV location updates are used.
- Direct UnrealCV movement is guarded by software safety rules:
  - arena bounds default to `SIM_TARGET_BOUND_X=1350`, `SIM_TARGET_BOUND_Y=1350`
  - arena margin defaults to `SIM_ARENA_BOUNDARY_MARGIN_CM=90`
  - live drones avoid overlapping each other through `SIM_DRONE_COLLISION_RADIUS_CM`
  - manual circular blockers can be configured with `SIM_COLLISION_BLOCKERS`
- Direct placement after a swept block is disabled by default:
  - `SIMWORLD_DIRECT_ON_SWEEP_BLOCK=0`
- Bridge startup should print the loaded arena guard.

## Team Mode

- Team setup scripts can configure red/blue team sizes up to 5v5.
- `launch\team_support.cmd` starts separate red and blue coordinators/controllers.
- Coordinators watch live poses and assign dynamic roles.
- Coordinators can ask Ollama for per-drone role plans using `SIM_TEAM_USE_OLLAMA=1`.
- Team Ollama uses the same default model and endpoint as the 1v1 brains:
  - `gpt-oss:latest`
  - `http://10.8.0.132:11434/api/generate`
- Support controllers command only their own side.
- The current 5v5 preset sets `SIM_TEAM_CONTROL_PRIMARIES=1`, so all ten drones move through team support.
- The current 5v5 preset sets `SIM_TEAM_IGNORE_DUEL_PRIMARY_CMDS=1`, so duel brain hold commands do not override team movement.
- Red support roles include:
  - `screen`
  - `decoy`
  - `hide`
  - `bait`
- Blue support roles include:
  - `flanker`
  - `pressure_screen`
  - `cutoff`
  - `support`
  - `search`
- Blue support can split into search lanes when runner sight is blocked or uncertain.
- Blue support distributes pressure across active red support drones instead of stacking on one target.
- Support drones keep spacing from same-team drones.
- Support drones can use configured blockers for route/cover hints.

## Scoring And Rounds

- Normal team catch mode can use primary scoring:
  - `red_1` vs `blue_1`
- `SIM_TEAM_CATCH_MODE=any` makes nearest red/blue contact score.
- `SIM_TEAM_ROUND_MODE=red_elimination` runs elimination mode:
  - nearest active red/blue contact can tag a target when catch mode is `any`
  - eliminated red drones drop to `SIM_TEAM_ELIMINATION_GROUND_Z`, default `0`
  - eliminated red drones are excluded from live drone collision checks
  - the current 5v5 demo preset stops the game when all five targets are tagged
- The current 5v5 demo preset uses:
  - `SIM_CATCH_DISTANCE=220`
  - `SIM_RED_BURST_SPEED=300`
  - `SIM_BLUE_INTERCEPT_SPEED=525`
  - chaser intercept speed is about `1.75x` target burst speed

## Brains

Target brain can:

- flee, veer, juke, zigzag, burst, and random escape
- use memory when the chaser is not visible
- react to patrol/evade/panic states
- manage stamina and burst cooldown
- choose level/climb/dive altitude tactics
- detect low actual speed and run `unstuck_reposition`
- trigger unstuck faster near the arena wall

Chaser brain can:

- chase, intercept, pressure, cutoff left/right, search last seen, and finish near catch range
- follow target altitude
- use heat/overheat limits
- stop using perfect target knowledge when LOS is lost

Both brains can use Ollama, but fall back to local tactics if Ollama is unavailable or times out.

## Visibility And Tactical Blockers

- LOS is currently simple geometry, not real Unreal raycasts.
- Checks include:
  - range
  - FOV
  - close-range detection
  - optional `SIM_LOS_BLOCKERS`
  - optional `SIM_TACTICAL_BLOCKERS`
  - `SIM_COLLISION_BLOCKERS` reused as tactical blockers

Example:

```powershell
$env:SIM_TACTICAL_BLOCKERS="center_pillar,0,0,450,100,700"
```

## Watcher And Logs

- `launch\start.cmd` can auto-run the compact watcher.
- `launch\panel.cmd` opens the Drone Team Panel.
- The panel shows chasers on the top row and targets on the bottom row.
- The panel marks red drones as `TAGGED` when they drop to `z=0`.
- The panel pulses cards when actions, role changes, tags, or game-over events arrive.
- Watcher shows:
  - ready/start/stop
  - target movement phase
  - chaser commits
  - team role intent
  - visibility lost/regained
  - catch/elimination events
  - stamina/boost
  - heat/thermal state
  - actual speed and stuck state
- Detailed logs are saved under `logs/chase_watch/`.

## Process Cleanup

- Start/stop/reset commands use reliable control publishing, with repeated `start_all` delivery to reduce missed-start races.
- `launch\new_round.cmd` starts another round after game over without killing bridge/brain/panel processes.
- `launch\stop.cmd` publishes `stop_all`.
- It also cleans stale live/source-module nodes and old installed ROS entry points such as:
  - `target_brain.exe`
  - `chaser_brain.exe`
  - `ue_bridge.exe`
  - matching `*-script.py` processes
  - stale `team_node.cmd` launcher windows
- This matters because duplicate brains can publish conflicting commands and make drones look frozen or inconsistent.

## Current Limitations

- Direct UnrealCV movement cannot use real Unreal mesh collision.
- Software arena bounds and configured blockers are the current workaround.
- Full match scoring/timers/summaries are future scope.
- Support drones do not yet have per-drone stamina/heat.
- Real Unreal raycast perception is future scope.
- Automatic map measurement is future scope.
