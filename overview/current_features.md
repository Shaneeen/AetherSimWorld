# Current Features

## Simulation Setup

- SimWorld can spawn and control two drones.
- ROS bridge publishes drone pose and accepts velocity commands.
- ROS bridge enforces drone altitude bounds before applying movement:
  - default minimum Z: 100 cm
  - default maximum Z: 700 cm
  - override with `SIMWORLD_DRONE_MIN_Z` and `SIMWORLD_DRONE_MAX_Z`
- ROS bridge tries swept Unreal movement for drone position updates so placed wall/obstacle/drone collision can block motion when Unreal Python execution is available.
- ROS bridge also has a fallback software collision guard for direct UnrealCV location moves:
  - discovers obstacle-like actors by name, default pattern `obstacle`
  - supports manual circular blockers with `SIM_COLLISION_BLOCKERS=x,y,radius[,min_z,max_z];...`
  - prevents DroneA and DroneB from stepping through each other using `SIM_DRONE_COLLISION_RADIUS_CM`
- Separate brain nodes control each drone:
  - target brain for the red/evading drone
  - chaser brain for the blue/white/chasing drone
- Chase can be started and stopped with command scripts.
- Start command can randomize fair starting positions before the chase begins.
- Target brain resets its runtime memory, stamina, cached tactic, and stuck state when the chase is reset or restarted.
- Tag pause is configurable with `SIM_TAG_PAUSE_SEC` or `run_chase_sim.ps1 -TagPauseSec`:
  - `-1` pauses both drones forever after a tag
  - `0` disables tag pause
  - any positive value pauses both drones for that many seconds

## AI / Ollama

- Both target and chaser can use Ollama.
- Default model is `gpt-oss:latest`.
- Default remote API is `http://10.8.0.132:11434/api/generate`.
- Both brains have fallback logic when Ollama fails, times out, or returns unusable output.
- Ollama output is parsed more flexibly than before:
  - direct `strategy:tactic`
  - JSON with `strategy` and `tactic`
  - short text that includes an allowed tactic
- AI failures back off before retrying so the sim keeps running.

## Target Brain

The target drone can:

- move in x/y/z using vertical velocity commands
- choose simple altitude tactics:
  - `level_escape`
  - `climb_escape`
  - `dive_escape`
- flee directly away from the chaser
- veer left or right
- juke left or right
- zigzag
- burst escape
- choose random escape headings
- bias random escape away from the threat and back toward arena center near boundaries
- safety-check final escape headings so close-range moves cannot intentionally point back into the chaser
- use memory when the chaser is not currently visible
- react to threat states:
  - patrol
  - evade
  - panic
- manage stamina for burst escape:
  - burst costs stamina
  - burst drains stamina while active
  - stamina regenerates outside burst
  - exhausted target speed is reduced slightly
- detect when commanded movement is not producing real pose movement
- run an `unstuck_reposition` maneuver to leave wall/corner pockets
- cancel `unstuck_reposition` early once real movement resumes

Target AI strategies include:

- `keep_distance`
- `break_line_of_sight`
- `reverse_when_overcommitted`
- `wide_arc_escape`
- `tempo_change`
- `force_overshoot`

## Chaser Brain

The chaser drone can:

- move in x/y/z and follow the target's altitude within the configured Z bounds
- chase directly
- intercept
- cutoff left
- cutoff right
- apply pressure
- search last seen position
- commit to finish/catch behavior near the target
- stop using perfect target knowledge when line of sight is lost
- manage heat for high-effort pursuit:
  - intercept/cutoff/finish behavior builds heat
  - pressure/search behavior cools heat
  - overheated chase speed is reduced

Chaser AI strategies include:

- `herd_to_boundary`
- `shadow_until_close`
- `fake_left_cut_right`
- `predict_and_camp`
- `deny_center`
- `spiral_search`

## Visibility / Line of Sight

Current LOS is simple geometry, not full Unreal raycast vision yet.

It checks:

- visible range
- field of view
- close-range detection override
- target proximity/radar-style detection for nearby threats
- optional circular blockers from `SIM_LOS_BLOCKERS`

Useful environment variables:

- `SIM_LOS_ENABLED=1`
- `SIM_TARGET_FOV_DEG=220`
- `SIM_CHASER_FOV_DEG=200`
- `SIM_LOS_BLOCKERS=x,y,radius;x,y,radius`

Example blocker:

```powershell
$env:SIM_LOS_BLOCKERS="0,0,450"
```

This creates a circular fake obstacle at map center with radius 450 cm.

## Watcher / Compact Logs

The compact watcher reads `/sim/status` and shows shorter merged updates.
It also saves a detailed raw/event log under `logs/chase_watch/` and keeps only the two newest detail logs.
The terminal feed groups noisy repeated states like `[cached]`, left/right jukes, and left/right cutoffs so normal motion does not spam the screen.

It can show:

- brain ready state
- chase start and stop
- reset/start distance
- AI chosen strategy and tactic
- AI fallback errors
- target movement phase
- chaser commits
- catch zone reached
- visibility lost/regained events
- current target stamina/boost state
- current target actual movement speed and unstuck state
- current chaser heat/thermal state
- estimated distance when the target is acting from memory instead of live sight
- detailed raw `/sim/status` messages in saved log files

Expected examples:

```text
TARGET: tempo_change -> burst_escape, panic, sees chaser, distance 430 cm
CHASER: commits spiral_search -> search_last_seen, no sight (fov), distance 900 cm, heat 24.0 (cool)
CHASER: lost sight of target (fov), distance_cm=900.0
TARGET: AI fallback - Ollama endpoints failed
CAUGHT: at 105.4 cm
```

## Important Current Limitations

- LOS is not yet based on real SimWorld obstacle raycasts.
- 3D movement is basic altitude control, not full 3D pathfinding.
- Swept collision depends on Unreal Python being available through the running UnrealCV session; otherwise the bridge falls back to direct location updates.
- There is no full round manager yet.
- Scoring is not a proper match system yet.
- Team-vs-team behavior is not implemented yet.
- Roles are not dynamic across teams yet because the sim is still one-vs-one.
