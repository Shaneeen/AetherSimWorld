# Change Log

## 2026-05-10

- Reviewed the existing drone-vs-drone chase setup and identified the main areas to improve: movement control, chase logic, collision handling, watcher logs, and future team-vs-team support.
- Started documenting the current project structure and separating completed features from future improvements.
- Created the initial overview documentation structure for current features, current phase, future plan, and change log tracking.

## 2026-05-11

- Reviewed the target and chaser brain behaviour during normal chase runs.
- Improved the basic chase flow by checking how the target reacts when the chaser is nearby.
- Began identifying issues where the target would sometimes remain near walls or move in weak escape directions.

## 2026-05-12

- Added early improvements to target escape behaviour so the target avoids moving directly back toward the chaser during close-range encounters.
- Adjusted random escape behaviour so movement remains unpredictable but is still biased away from danger.
- Started refining wall and edge behaviour so the target can move back toward the arena centre when near boundaries.

## 2026-05-13

- Added target stuck-detection logic based on actual pose movement compared with commanded movement.
- Added an `unstuck_reposition` behaviour so the target can attempt to leave wall or corner pockets instead of remaining trapped.
- Updated compact watcher output to show target actual movement speed and unstuck state for easier debugging.

## 2026-05-14

- Added simple line-of-sight support for the target and chaser brains.
- Disabled fake random occlusion by default so visibility behaviour is more predictable during testing.
- Added optional circular LOS blockers through `SIM_LOS_BLOCKERS`.
- Updated compact watcher output to show visibility lost/regained events.

## 2026-05-15

- Improved chaser behaviour when line of sight is lost so it searches the last known target position instead of relying on perfect target knowledge.
- Improved Ollama prompts so AI decisions return higher-level strategies with immediate tactics.
- Updated launch scripts to use the remote Ollama model `gpt-oss:latest`.
- Added fallback handling when Ollama fails, times out, or returns unusable output.

## 2026-05-16

- Reviewed live chase logs and reduced noisy watcher output.
- Grouped repeated cached tactics, left/right jukes, and cutoff movements so the compact terminal feed is easier to read.
- Added detailed saved logs under `logs/chase_watch/`.
- Added log retention so only the two newest chase detail logs are kept.

## 2026-05-17

- Performed light testing on the chase watcher and target/chaser behaviour.
- Tuned target unstuck detection thresholds after testing showed that slow wall-pocket movement could avoid the detector.
- Added clearer watcher status output so future test runs show whether unstuck recovery is active.

## 2026-05-18

- Added target brain reset handling for `/sim/reset_chase` so new rounds clear stale stamina, memory, cached tactics, and unstuck timers.
- Added early exit from `unstuck_reposition` when actual movement recovers.
- Added target proximity detection so nearby chasers override FOV loss and stale memory.
- Added target stamina and burst limits so panic/burst escape cannot run freely forever.
- Added chaser heat limits so intercept, cutoff, and finish pressure have a cost.
- Marked Phase 2A as stable enough to move on after live log review.
- Added the future roadmap for Phase 2B basic 3D movement, later obstacle/gate waypoint logic, and height-aware team tactics.

## 2026-05-19

- Added configurable tag pause behaviour through `SIM_TAG_PAUSE_SEC` and `run_chase_sim.ps1 -TagPauseSec`.
- Added basic Phase 2B 3D drone movement, allowing target and chaser brains to publish vertical velocity through `cmd.linear.z`.
- Added configurable altitude limits with default bounds of 100-700 cm.
- Added bridge-side altitude clamping to enforce the configured flight height.
- Added target climb, dive, and level altitude choices under evade and panic pressure.
- Added chaser altitude-following behaviour so it pursues the target height instead of only moving in x/y.
- Updated UE bridge movement to try swept Unreal actor movement before falling back to direct UnrealCV location updates.

## 2026-05-20

- Added first live team support mode.
- Updated the bridge to load saved team sizes and map `DroneA`/`DroneB` to `red_1`/`blue_1`.
- Added support drone spawning up to 3v3.
- Added `team_drone_controller` and `run_team_support.cmd` so non-primary support drones can move with team role/formation behaviour.
- Updated start/stop signaling so team support starts and stops with the normal chase controls.
- Added team match setup tooling for red/blue drone counts and default/manual/AI model-based speed profiles.
- Saved team match setup to `scripts/DroneROS/team_match_config.cmd`.
- Updated target/chaser launch scripts to reuse selected red/blue speed profiles when a saved team config exists.
- Added `clear_team_match_config.cmd` to return to individual drone speed prompts.
- Restructured the ROS source package into `bridge`, `duel`, `control`, `watch`, and `team` folders with compatibility wrappers.
- Added a Phase 3 `team_coordinator` scaffold for future red-vs-blue role assignment.

## 2026-05-21

- Continued testing the team-vs-team setup flow.
- Updated compact watcher output for team bridge/support readiness.
- Tuned chaser balance defaults from 240/270/170 cm/s to 260/300/200 cm/s.
- Exposed `SIM_CHASER_PRESSURE_SPEED_SCALE` at 0.78 so pressure mode is less sluggish.
- Raised default chase catch distance from 120 cm to 160 cm so visually close passes register more reliably.
- Guarded chaser `orbit_pincer` so Ollama cannot keep using it when the target is moving normally or outside orbit range.

## 2026-05-22

- Added bridge-side obstacle and drone collision guards for the UnrealCV direct-location fallback.
- Added software checks so drones cannot step through discovered obstacle actors when swept Unreal movement is unavailable.
- Added `run_bridge_existing.cmd` defaults for obstacle collision discovery.
- Broadened default software obstacle discovery names to include wall, building, barrier, blocker, and mesh.
- Added chaser `encircle_stalled:orbit_pincer` behaviour so a visible stalled or slow target at mid range can be circled and closed down instead of only direct-chased.
- Exposed tuning knobs for stalled-target orbit behaviour.

## 2026-05-23

- Split team support runtime by side.
- Updated `run_team_support.cmd` to start separate red/blue coordinators and separate red/blue support controllers.
- Scoped `team_drone_controller` by `SIM_TEAM` so each side only commands its own support drones.
- Fixed scoped team support pose awareness so each side watches both teams' poses while only commanding its own drones.
- Expanded red support roles to include screen, decoy, hide, and bait.
- Expanded blue support roles to include flanker, pressure screen, cutoff, and support.
- Added support intent logs so chase logs show why a support drone is moving.
- Changed team-mode catch detection to primary-only by default so support drones can screen or decoy without instantly ending the round.
- Added shared match rules code in `team/match_rules.py`.
- Added red-elimination round mode where caught red drones drop to the ground and the bridge resets once all red drones are caught.
- Added a short red-elimination grace window to avoid immediate removal during round setup.
- Added stale team process cleanup to `run_team_support.cmd` and `stop_chase.cmd`.

## 2026-05-24

- Performed lighter weekend testing on team support and red-elimination behaviour.
- Tuned support movement goals into wider team lanes so support drones do not clump too closely.
- Adjusted red screen, decoy, and outlet positions so they separate more clearly from the runner.
- Adjusted blue support positioning for pincer, screen-clear, and center-denial roles.
- Reduced target vertical bounce by lowering launcher altitude defaults and adding a short altitude tactic hold before random climb/dive choices can flip again.
- Added inactive manual drone parking so unused drones in smaller matches are moved away from the chase area.
- Updated launch instructions to keep the compact terminal flow as the main runnable path.

## 2026-05-25

- Added a bridge-side arena boundary guard for direct UnrealCV movement so drones stay inside the configured arena wall even when Unreal swept collision is unavailable.
- Updated target/chaser launch bounds to match the bridge arena guard.
- Made target wall-contact unstuck trigger more quickly when movement slows against the boundary.
- Fixed `stop_chase.cmd` cleanup to also kill stale installed ROS console entry points such as `chaser_brain.exe` and `chaser_brain-script.py`.
- Fixed red-elimination ground drops so eliminated drones can use `SIM_TEAM_ELIMINATION_GROUND_Z=0` instead of being clamped back to normal flight altitude.
- Fixed red-elimination team mode so the bridge no longer ignores primary duel-brain movement commands by default.
- Changed red-elimination scoring so support red drones are eliminated first, while `red_1` remains the live runner until it is the last active red.
- Added and then disabled direct-placement fallback by default with `SIMWORLD_DIRECT_ON_SWEEP_BLOCK=0` so real swept wall collision is not bypassed.
- Updated `stop_chase.cmd` to kill stale bridge, target brain, chaser brain, and team support Python processes.
- Changed target/chaser launch scripts to run source modules directly with `python -m` to avoid stale installed console entry points.
- Added bridge startup movement-config status output showing primary-command ignore, swept movement, direct fallback, round mode, and catch mode.
- Rebalanced white support pressure so support drones distribute across active red support targets.
- Added a blue support search role for blocked runner sight so support drones split into separate search lanes instead of stacking on one point.
- Added shared tactical geometry utilities for circular blocker LOS checks, route-around shoulder waypoints, and cover-point selection.
- Updated target/chaser duel brains to read tactical, collision, and LOS blockers.
- Updated team coordinators to watch live team poses and assign support roles based on pressure, screens, and blocked-sight state.
- Updated support controllers to route around configured blockers, use cover points for red support, clear active screens for blue support, and maintain safer enemy tag spacing.
- Replaced blocking `ros2 topic pub` calls in `start_chase.cmd` and `stop_chase.cmd` with the existing `start_signal` helper.
- Restored `start_chase.cmd` to the older direct stop/reset/start launch flow, while keeping bridge/brain checks as non-blocking diagnostics.
- Changed default team visuals back toward clear red-vs-white distinction.
- Fixed 4v4/5v5 reset placement so all active support drones receive formation positions.
- Raised default team-mode start distance so larger formations begin as two separated groups.
- Published real bridge odometry velocity for all drones so brains no longer see false `actual_speed=0.0`.
- Hardened team support shutdown so one side does not continue running alone after ROS context invalidation.
- Fixed a missed-start race where target/chaser brains could stay in `waiting_for_start` while team support moved.
- Changed start/stop control topics to reliable transient-local QoS and made `start_signal` repeat/linger longer so `start_all` is much harder to miss.
- Restored the saved team match config to 5v5 after the latest log showed the run had fallen back to 3v3 and parked extra drones as inactive.
- Reviewed the latest saved chase detail log.
- Marked Phase 2B and Phase 3 as completed for the current project scope.
- Marked Phases 4, 5, and 6 as not currently specified and waiting for further instructions.

## 2026-05-27

- Replaced the older `scripts\DroneROS` runtime path with a cleaner root-level `launch\` command folder.
- Added `launch\env.cmd` to centralize the Windows ROS/Pixi/Python environment and DLL fixes.
- Added simple root launch commands for set teams, clear teams, bridge, target, chaser, panel, team support, start, and stop.
- Fixed the ROS Windows `rclpy` DLL import issue through a `sitecustomize.py` DLL path helper under `launch\ros2_dll_site`.
- Updated launch instructions so the normal flow is now bridge, target, chaser, panel, and start/stop terminals.
- Added a Tk-based Drone Team Panel that shows chasers on the top row and targets on the bottom row with five slots each.
- The panel listens to poses, commands, role topics, and `/sim/status`, then displays compact per-drone action/status text.
- Added panel pulsing for new actions, role changes, command firing, eliminations, and game-over events.
- Added `TAGGED` display when a red/target drone is at `z=0`, even if the explicit elimination status line is missed.
- Reduced panel action/status font sizes and enabled wrapping so movement text is readable instead of clipped.
- Changed 5v5 mode so team support controls all ten drones, including `red_1`/`DroneA` and `blue_1`/`DroneB`.
- In 5v5 mode, duel primary commands are ignored so the team controller does not fight target/chaser brain hold commands.
- Changed 5v5 setup to red-elimination scoring with `SIM_TEAM_CATCH_MODE=any`.
- Changed elimination behavior so tagged target drones drop to `z=0`, stay down, and stop moving.
- Changed all-targets-down behavior from automatic reset to game over with `stop_all`.
- Tuned the 5v5 demo preset for easier visual tagging with `SIM_CATCH_DISTANCE=340`.
- Tuned the 5v5 demo speed preset so chaser intercept speed is `525` cm/s and target burst speed is `300` cm/s, about `1.75x`.
- Updated team support launch to start minimized logged support processes instead of unreliable invisible background children.
- Added stale `team_node.cmd` cleanup to `launch\stop.cmd`.
- Added team support status reporting for missing poses so frozen support drones can be diagnosed from logs and the panel.
- Added `launch\new_round.cmd` for starting another round after all targets are tagged without killing the bridge, brains, or panel.
- Updated team support launch to clean existing team support nodes before relaunching so repeated starts do not stack duplicate controllers.
- Removed visible x/y/z coordinate repainting from the Drone Team Panel and slowed its refresh to reduce UI overhead.
- Disabled per-move bridge rotation pushes by default with `SIMWORLD_PUSH_ROTATION=0` to reduce UnrealCV command traffic during 5v5 demos.
- Loosened 5v5 demo drone spacing/collision settings so support drones are less likely to block each other while commands are active.
- Hardened `/sim/reset_chase` delivery by using reliable transient-local QoS and repeated reset publishing.
- Added bridge-side reset debouncing so repeated reset messages only create one new randomized round.
- Added Ollama-backed 5v5 team coordination using the same `gpt-oss:latest` model and `10.8.0.132:11434` generate endpoint as the 1v1 brains.
- Team coordinators now request validated per-drone role plans from Ollama and fall back to deterministic live-state roles if Ollama is unavailable.
- Reduced 5v5 demo catch distance from `340` cm to `220` cm after logs showed tags registering at visually too-far distances around `316-336` cm.
- Expanded elimination logs with XY distance, Z delta, and active catch radius for easier tag-distance debugging.
- Reviewed the latest 5v5 chase log and found blue support drones were holding tag spacing from red drones, causing loitering and parallel movement instead of committed attacks.
- Changed blue team support movement so nearby active red drones trigger a direct commit chase, while red drones still keep evasive spacing.
- Added `SIM_BLUE_DIRECT_COMMIT_DISTANCE_CM=1200` to the 5v5 preset and ignored downed red drones during blue target search.
