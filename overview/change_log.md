# Change Log

## 2026-05-20

- Added bridge-side obstacle/drone collision guards for the UnrealCV direct-location fallback, so drones cannot step through discovered obstacle actors when swept Unreal movement is unavailable.
- Added `run_bridge_existing.cmd` defaults for obstacle collision discovery (`SIM_OBSTACLE_NAME_PATTERNS=obstacle`, `SIM_OBSTACLE_RADIUS_CM=170`, `SIM_DRONE_COLLISION_RADIUS_CM=70`).
- Rebuilt the installed ROS package so the old `.cmd` chase flow picks up the 3D `cmd.linear.z` movement code.
- Added explicit altitude defaults to the old target/chaser brain `.cmd` launchers so up/down movement is visible in normal runs.
- Reverted the experimental `run_chase_sim.ps1` launcher changes and returned to the old chase start flow: run the existing bridge script, then run `start_chase.cmd`.
- Fixed `run_chase_sim.ps1` startup on the local Pixi/ROS setup by cleaning inherited Python environment variables, using the matching Pixi Python, loading source modules correctly, and writing per-node logs.
- Added direct `python -m` entry guards for the ROS bridge, target brain, and chaser brain.
- Added UnrealCV reconnect retry behavior to the ROS bridge so it can recover when Unreal starts after the chase launcher.

## 2026-05-19

- Added configurable tag pause behavior through `SIM_TAG_PAUSE_SEC` and `run_chase_sim.ps1 -TagPauseSec`: `-1` pauses forever after tag, `0` disables tag pause, positive values pause for that many seconds.
- Added basic Phase 2B 3D drone movement: target/chaser brains now publish vertical velocity through `cmd.linear.z`.
- Added configurable altitude limits with defaults of 100-700 cm and clamped bridge enforcement.
- Added target climb/dive/level altitude choices under evade/panic pressure.
- Added chaser altitude following so it pursues target height instead of only x/y position.
- Changed UE bridge movement to try swept Unreal actor movement before falling back to direct UnrealCV location updates, so level collision can block motion when the runtime supports Unreal Python execution.

## 2026-05-18

- Split `chase_watch` into a condensed terminal feed plus detailed saved logs under `logs/chase_watch/`.
- Further reduced terminal watcher noise by grouping cached tactics, left/right jukes, and left/right cutoffs while keeping full detail in saved logs.
- Added detail log retention so only the two newest chase detail logs are kept.
- Added target brain reset handling for `/sim/reset_chase` so new rounds clear stale stamina, memory, cached tactics, and unstuck timers.
- Added early exit from target `unstuck_reposition` when actual movement recovers.
- Marked Phase 2A as stable enough to move on after live log review.
- Added future roadmap for Phase 2B basic 3D movement, later obstacle/gate waypoint logic, and height-aware team tactics.
- Reordered the future roadmap so Phase 2B comes before team-vs-team work and added an easy summary table.
- Added target stuck-detection startup grace period so reset/start does not immediately force `unstuck_reposition`.
- Throttled unstuck status output so compact watch is readable during recovery.
- Added target proximity detection so nearby chasers override FOV loss and stale memory.
- Added final separation safety check so target escape/juke/burst headings cannot point back into a close chaser.
- Tightened target unstuck recovery again after logs showed repeated `actual 0.0 cm/s` without visible `unstucking`.
- Added explicit unstuck trigger/status output so watcher runs reveal whether recovery is active.
- Changed target `random_escape` so it is unpredictable but still biased away from the threat instead of allowing pure random flight toward the chaser.
- Made target edge behavior blend escape headings toward arena center when near boundaries.
- Made short evasive tactics expire faster so bad jukes/random escapes cannot dominate for several seconds.
- Tightened target stuck detection thresholds after live testing showed slow wall-pocket movement could avoid the detector.
- Added target anti-stuck detection based on actual pose movement versus commanded speed.
- Added `unstuck_reposition` behavior so the target tries to leave wall/corner pockets instead of wandering in place.
- Updated compact watcher to show target actual movement speed and unstuck state.
- Added close-range detection so drones do not unrealistically lose sight at very short range unless blocked by an obstacle.
- Changed target memory behavior so hidden/remembered chaser distance is treated as estimated instead of perfect live perception.
- Reset chaser heat timer on chase start so heat does not jump from idle time before the round.
- Made overheated chaser behavior prefer pressure over repeated intercept/finish commits.
- Changed burst tactic fallback so unavailable burst degrades into a juke instead of pretending full boost is available.
- Added target stamina and burst limits so panic/burst escape cannot run freely forever.
- Added chaser heat limits so intercept/cutoff/finish pressure has a cost.
- Updated compact watcher summaries so visibility distance refreshes during normal target/chaser updates instead of only on lost/regained events.
- Added `overview/` documentation folder.
- Documented current phase as Phase 2A.
- Documented current features, limitations, and future roadmap.
- Added simple line-of-sight support to the target and chaser brains.
- Disabled fake random occlusion by default.
- Added optional circular LOS blockers through `SIM_LOS_BLOCKERS`.
- Updated compact watcher to show visibility lost/regained events.
- Improved AI prompts so Ollama chooses higher-level strategies plus immediate tactics.
- Changed chaser behavior so it searches after losing sight instead of using perfect target knowledge.
- Updated launch scripts to use remote Ollama model `gpt-oss:latest` at `http://10.8.0.132:11434/api/generate`.

## Update Rule

Whenever a feature changes, update:
- `current_features.md` for what exists now.
- `current_phase.md` if project status changes.
- `future_plan.md` if the roadmap changes.
- this file with a short dated note.
