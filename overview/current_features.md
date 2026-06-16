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
  - `vision/`
- Layer names are defined in `overview\naming_convention.md`. Use that glossary when interpreting logs so `live role planner fallback` is not confused with image VLM or Image VLA failure.

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
- Team Coordinators watch live poses and assign dynamic roles.
- Team Coordinators can consume `/sim/vision_scene` JSON as a low-authority tactical hint when `SIM_TEAM_USE_VISION_HINTS=1`.
- The optional Live Role Planner inside the Team Coordinator can ask Ollama for per-drone role plans using `SIM_TEAM_USE_OLLAMA=1`.
- Team Coordinators stop scheduling new Ollama planning work after `/team/control` STOP so post-game shutdown does not keep producing misleading planner fallback lines.
- Team Action Controllers now log `vla_action=1` and use a first-pass VLA-style action layer: close blue drones perform direct finish commits, other blue drones pressure active red targets, and the blue swarm switches to endgame collapse when only one red drone remains.
- Red and blue VLA action layers can directly consume `/sim/vision_scene` and mark intents with `VLA used vision team=... source=vlm...` when fresh VLM scene evidence is used.
- Red and blue action layers now include a first practical image-VLA bias when the scene source is image VLM rather than context VLM:
  - blue tightens pincer/support pressure when the runner is visible
  - blue splits wider search lanes when image VLM reports blocked or uncertain sight
  - red widens screens/decoys and stretches hide/outlet behavior when image VLM says the runner is visible
  - red preserves broken-sight outlets when image VLM is uncertain
- Blue support drones can perform assigned-target VLA finish commits inside the configured direct-commit distance, so support drones can produce scoring pressure instead of only `blue_1`.
- Team Ollama uses the same default model and endpoint as the 1v1 brains:
  - `gpt-oss:latest`
  - `http://10.8.0.132:11434/api/generate`
- Team coordinator launch now warms the planner model and uses `OLLAMA_TIMEOUT_SEC=60` by default; if the watch log says `live role planner fallback`, the deterministic Team Coordinator and Image VLA Action Controller are still running, but the optional Ollama role planner did not return usable JSON.
- The Live Role Planner now prefers Ollama `/api/chat` (`SIM_TEAM_OLLAMA_USE_CHAT=1`) because `gpt-oss:latest` was observed returning empty or malformed planner text through `/api/generate` while `/api/chat` returned valid role JSON for the same task.
- The Live Role Planner is throttled and cached by default so it does not hammer Ollama during image-VLM runs:
  - `SIM_TEAM_OLLAMA_COOLDOWN_SEC=12`
  - `SIM_TEAM_OLLAMA_PLAN_CACHE_SEC=24`
  - `SIM_TEAM_OLLAMA_FAILURE_BACKOFF_SEC=18`
  - `SIM_TEAM_OLLAMA_MAX_BACKOFF_SEC=90`
- The Team Coordinator can salvage some malformed planner text into safe roles instead of treating every bad JSON response as a full planner failure.
- Support controllers command only their own side.
- The current 5v5 preset sets `SIM_TEAM_CONTROL_PRIMARIES=1`, so all ten drones move through team support.
- The current 5v5 preset sets `SIM_TEAM_IGNORE_DUEL_PRIMARY_CMDS=1`, so duel brain hold commands do not override team movement.
- Red support roles include:
  - `screen`
  - `decoy`
  - `hide`
  - `bait`
- Red movement now uses per-drone swarm lanes so all five red drones should visibly move together: `red_1` takes the main escape lane, `red_2`/`red_3` fan left and right, and `red_4`/`red_5` take wider split lanes.
- Team support status includes `cmd_speed={...}` so a run log can prove whether every controlled drone is receiving a nonzero movement command.
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

## Vision Perception

- `vision/visual_observer.py` is an opt-in VLM perception node.
- It publishes structured scene summaries on `/sim/vision_scene`.
- The preferred image path is now bridge-owned camera frames on `/sim/camera_frame`, published by the bridge's existing UnrealCV connection. This avoids the visual observer opening a second UnrealCV camera connection.
- Direct observer-side UnrealCV capture is off by default and can be re-enabled only when needed with `SIM_VISION_DIRECT_UNREALCV=1`.
- Bridge camera frame capture is spectator-safe by default: `SIM_BRIDGE_CAMERA_STEER_ENABLED=0` means image VLM captures the current UnrealCV camera frame without deliberately moving camera `0` around. Set `SIM_BRIDGE_CAMERA_STEER_ENABLED=1` only when a drone-follow camera is more important than freely watching the match.
- `launch\vision.cmd` starts the observer with:
  - `SIM_VISION_ENABLED=1`
  - `SIM_VLM_ENABLED=1`
  - default observer `blue_1`
  - default model `qwen3-vl:latest`
  - default endpoint `http://10.8.0.132:11434/api/generate`
  - default VLM timeout `SIM_VLM_TIMEOUT_SEC=90`
  - default observer timeout `SIM_VISION_REQUEST_TIMEOUT_SEC=180`
  - default camera size `SIM_VISION_CAMERA_WIDTH=320`, `SIM_VISION_CAMERA_HEIGHT=240`
  - default VLM interval `SIM_VISION_VLM_INTERVAL_SEC=20`
  - default output budget `SIM_VLM_NUM_PREDICT=256`
- Current recommended model is `qwen3-vl:latest`, matching the available Ollama tag on the configured server.
- Qwen2.5-VL 7B/Instruct remains a fallback if Qwen3-VL is unavailable on another machine.
- Larger Qwen2.5-VL 32B or Qwen3-VL variants are better later if GPU capacity allows.
- OpenVLA is future reference/fine-tuning scope, not the first runtime model for drone interception.
- `launch\vision_check.cmd` checks the configured VLM tag, vision capability, tiny generation, and optionally UnrealCV camera capture.
- `SIM_VISION_CHECK_IMAGE_VLM=1` extends the check to send a real UnrealCV camera frame to the VLM and verify image-to-JSON output.
- On 2026-06-04, `qwen3-vl:latest` was visible on the Ollama server and reported `vision` capability.
- Qwen3-VL may spend many tokens in the `thinking` field before returning JSON, so the vision node uses a larger output budget.
- On 2026-06-04, image VLM smoke testing succeeded: Qwen3-VL described the SimWorld camera frame as an indoor gray-walled scene with tiled floors and a central column, returning JSON in about 20 seconds. No drones were obvious in that camera frame.
- The observer positions an UnrealCV camera near the selected observer drone and captures `lit` frames.
- The observer now follows the SimWorld example pattern more closely by logging available UnrealCV cameras, setting camera resolution before capture, logging captured frame bytes, and timing image-to-VLM responses.
- Live image requests wait until enough drone poses exist and use compact JSON-only prompts so Qwen3-VL has a better chance of returning before timeout.
- Vision launch and vision checks automatically run `simworld_drone_ros.vision.prepare_ollama`, which unloads stale `magicoder:latest` by default and warms Qwen3-VL without stopping `gpt-oss:latest`.
- Live image VLM has been proven end-to-end in `logs\run_reports\run_report_20260615_162919.md`: image VLM was enabled, bridge camera frame bytes were seen, `vlm_image_scene_seen=true`, `vlm_context_scene_seen=false`, and team/VLA logs showed fresh VLM vision use.
- Context VLM remains a diagnostic/fallback mode, but the intended Phase 4 path is image VLM from bridge camera frames.
- Full image VLM can also be launched explicitly with `launch\vision.cmd blue_1 --image`, `launch\vision_image.cmd blue_1`, or `launch\run_demo.cmd -Set5v5 -ImageVision`.
- The VLM client accepts JSON from either Ollama `response` or `thinking`, because Qwen3-VL can place valid JSON in `thinking` even when `response` is empty.
- The VLM client includes the mission goal from `overview\future_plan.md` when launched through `launch\vision.cmd`, so scene interpretation is anchored to the final swarm-intelligence objective.
- If image VLM returns clear visual evidence with an unusably low confidence value, the scene is repaired into a low-authority usable hint instead of being discarded immediately.
- If a VLM request exceeds `SIM_VISION_REQUEST_TIMEOUT_SEC`, the observer publishes a fallback `/sim/vision_scene` so team planning can keep running and the logs clearly show the timeout.
- The observer also publishes one warm fallback scene as soon as poses exist, so `/sim/vision_scene` is visible while the larger VLM is still thinking.
- `launch\vision.cmd blue_1` and `launch\vision.cmd red_1` can run separate primary observers.
- `SIM_VISION_AUTOSTART=1` starts primary blue/red observers with team support.
- Manual vision observers launched before `launch\start.cmd` are no longer killed by `launch\team_support.cmd`; only autostart mode replaces old vision observers.
- All-ten per-drone VLM observers are not enabled by default because Qwen3-VL image calls are currently too slow for every drone at every tick.
- VLM output is normalized into JSON fields such as:
  - `runner_visible`
  - `visible_targets`
  - `visible_drones`
  - `occluders`
  - `nearest_cover`
  - `blocked_by`
  - `recommended_search_area`
  - `suggested_tactic`
  - `confidence`
- A pose/blocker fallback can publish testable `/sim/vision_scene` messages when `SIM_VISION_PUBLISH_FALLBACK=1`.
- Team coordinators ignore stale or low-confidence vision scenes:
  - `SIM_TEAM_VISION_MAX_AGE_SEC`, default `8`
  - `SIM_TEAM_VISION_MIN_CONFIDENCE`, default `0.45`
- Vision hints bias role choices only:
  - blue can split into `search`/`cutoff` sooner when vision reports blocked or uncertain runner sight
  - red can prefer `hide`/`decoy` support when vision reports cover or occlusion
- The VLM does not directly publish velocity commands.
- The intended next step is improving the VLA-style team planner's quality: target-priority memory, intent cooldowns, richer red defense, and better use of image-VLM target/cover/occlusion facts.

## Watcher And Logs

- `launch\start.cmd` can auto-run the compact watcher.
- `launch\panel.cmd` opens the Drone Team Panel.
- The panel includes Start, Stop, New Round, and Reset Only buttons that publish the same reliable control/reset topics used by the launch scripts.
- The panel shows chasers on the top row and targets on the bottom row.
- The panel marks red drones as `TAGGED` when they drop to `z=0`.
- The panel pulses cards when actions, role changes, tags, or game-over events arrive.
- Watcher shows:
  - ready/start/stop
  - target movement phase
  - chaser commits
  - team role intent
  - visibility lost/regained
  - VLM/vision scene summaries
  - catch/elimination events
  - stamina/boost
  - heat/thermal state
  - actual speed and stuck state
- Detailed logs are saved under `logs/chase_watch/`.
- `launch\review_latest_run.cmd` runs a VLM post-run reviewer.
- Run reports are written under `logs\run_reports\`.
- Only the newest two `run_report_*.md` files are kept.
- Reports include deterministic log metrics plus a VLM supervisor review for red defender, blue attacker, system health, and next-run VLA tuning.
- Reports now separate basic evidence from stronger evidence: VLM context scenes, VLM image scenes, coordinator acceptance of vision, and whether a plan visibly used a vision hint.
- Reports also record whether image VLM was enabled, whether camera frame bytes were captured, and the largest observed image frame size.
- `launch\review_latest_run.cmd` uses `gpt-oss:latest` by default for the post-run reviewer so Qwen3-VL can stay focused on image VLM work.
- Reports also check whether the VLA action layer accepted vision and whether blue movement intents actually included fresh VLM vision use.
- Reports split VLA vision evidence by team with red/blue accepted-vision and used-VLM-vision fields.
- Reports include red/blue coordinator logs directly and check coordinator plan evidence separately from action-controller VLA evidence.
- Reports flag when all confirmed catches came from one blue drone, because swarm-vs-swarm should show distributed support participation.
- Reports use the chase log start time when collecting ROS logs, so long runs do not falsely lose early bridge logs.
- The bridge clears stale red-elimination state if a new start command arrives after a dirty or missed reset.
- Team reset placement validates the nearest actual red/blue scoring pair distance, so support drones should not begin a round already inside catch range.
- The 2026-06-15 16:29 report is the first clean image-VLM-to-VLA milestone report: image scene evidence, coordinator acceptance, VLA usage, game over, and distributed blue catches were all present.

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
- The VLM observer is opt-in and depends on stable bridge camera frames plus a reachable multimodal Ollama model.
- Vision-to-action is currently VLA-style role/goal assistance, not a trained end-to-end VLA model.
- Image VLM scene quality is still shallow and should be improved before reducing deterministic pose/state support.
- The optional team Ollama role planner can still fail with empty or invalid JSON; that failure is separate from image VLM/VLA evidence.
- Blue VLA intent diversity and red defender tactics are still the main behavior bottlenecks.
- Automatic map measurement is future scope.
