# Change Log

## 2026-06-15

- Made image-VLM camera capture spectator-safe by default. The bridge and direct observer no longer reposition UnrealCV camera `0` unless `SIM_BRIDGE_CAMERA_STEER_ENABLED=1`, so the user can watch the match without the AI camera repeatedly stealing the view.
- Added a first practical image-VLA action bias in the team controller: fresh image VLM scenes now directly affect both red and blue movement goals, not only coordinator role text. Blue tightens pursuit when the runner is visible and splits image-search lanes when vision is blocked or uncertain; red widens screens, decoys, hides, and escape outlets when image VLM says the runner is visible or sight is broken.
- Updated VLA intent text from generic `VLA used vision` to `Image VLA used vision` when the action layer is using a fresh non-context VLM scene.
- Added Start, Stop, New Round, and Reset Only buttons to the Tk team panel, using the same reliable ROS control topics as the launch scripts so basic match control can happen from the panel instead of separate terminal commands.
- Hardened the Live Role Planner so red and blue coordinator requests are staggered, cached, and backed off more gently; malformed planner text can now be salvaged into safe roles instead of immediately counting as a planner failure.
- Fixed the latest Live Role Planner failure mode by preferring Ollama `/api/chat` for `gpt-oss:latest`; direct testing showed `/api/generate` could return empty or malformed planner output, while `/api/chat` returned clean role JSON for the same role-planning task.
- Changed red team movement from shared escape directions to visible five-drone swarm lanes, and added `cmd_speed={...}` telemetry to Team support logs so the next run can prove whether all five drones are being commanded at once.
- Reached the first image-VLM-to-VLA closed-loop milestone in `run_report_20260615_162919.md`: image VLM was enabled, bridge camera frames were seen, `vlm_image_scene_seen=true`, `vlm_context_scene_seen=false`, coordinator vision acceptance was seen, and VLA action layers used fresh VLM vision.
- Confirmed a complete 5v5 red-elimination run with all five red drones tagged and game over reached.
- Confirmed better scoring distribution than earlier single-catcher runs: `blue_1` caught two red drones and `blue_2` caught three.
- Added bridge-owned camera frame publishing on `/sim/camera_frame` so the visual observer can use the bridge's existing UnrealCV connection for image VLM.
- Updated the visual observer to prefer bridge camera frames, avoid a second UnrealCV connection by default, and keep image-VLM mode as the intended Phase 4 path.
- Added mission-goal memory for the VLM prompt through `overview\future_plan.md`.
- Added image-scene confidence repair so clear visual output with bad confidence can still become a low-authority usable hint.
- Hardened the team coordinator by reducing role-planner output budget, adding JSON repair behavior, and stopping planner scheduling after STOP.
- Recorded that remaining `live role planner fallback` lines are optional Live Role Planner fragility, not proof that image VLM or Image VLA failed.
- Updated overview docs to mark the milestone and shift the next work from VLM plumbing to VLA behavior quality: blue target-priority memory, intent cooldowns, richer red defense, better image-scene semantics, and swept-movement fallback investigation.

## 2026-06-11

- Realigned `overview\future_plan.md` so the next main implementation target is VLM-supervised VLA swarm intelligence, not generic future perception work.
- Recorded the intended adversarial learning shape: separate red/blue VLA planners, separate supervising VLM reviewers, private team tuning notes, and safe controller validation.
- Added `launch\review_latest_run.cmd` and `simworld_drone_ros.analysis.run_report` to generate post-run VLM supervisor reports under `logs\run_reports\`, keeping only the newest two.
- Added `overview\latest_update.md` with the latest run diagnosis and the proposed VLM post-run report workflow for review before runtime implementation.
- Recorded that the latest VLM observer run started and made a VLM request with pose context, but did not yet prove a parsed scene was published or used meaningfully by team planning.
- Added the proposed `logs\run_reports\` markdown report feature to the overview roadmap, including newest-two retention.
- Added `launch\run_demo.ps1` and `launch\run_demo.cmd` as a staged launcher for opening bridge, target brain, chaser brain, panel, optional vision, and start/watch windows in order.
- Added manual staged-launch mode so each next terminal can wait for user confirmation when startup timing needs closer control.
- Added dry-run support to preview the staged launch commands without opening runtime windows.
- Added Windows Terminal tab mode through `launch\run_demo.cmd -Tabs` for a tidier staged launch.
- Fixed Windows Terminal tab argument quoting so tab titles with spaces are not misread as commands.
- Updated launch instructions with the easier staged launch flow while keeping the existing manual terminal flow as the fallback.
- Studied the local SimWorld UnrealCV camera examples and tightened the VLM observer path: live vision now sets 320x240 camera frames, logs UnrealCV camera discovery, logs VLM response timing, uses shorter live VLM timeouts, and publishes a fallback `/sim/vision_scene` if the large VLM is too slow.
- Reviewed `run_report_20260611_135402.md` and fixed two first-round blockers: `team_support.cmd` no longer kills manually launched visual observers, and blue support now uses a narrower VLA finish-commit radius plus active-target pressure instead of letting every white drone repeat `direct commit on red_1`.
- Updated the run reporter to record `vla_status`, warm fallback vision scenes, VLA finish commits, and VLA assigned-pressure evidence.
- Focused the live VLM path after `run_report_20260611_141138.md`: image prompts are now compact JSON-only requests, live VLM timeouts are longer, VLM requests wait for enough poses, image request cadence is throttled, and team coordinators log accepted vision scenes so real VLM usage is visible.
- Fixed the Qwen3-VL response parsing issue found after `run_report_20260611_143127.md`: Ollama can return valid JSON in the `thinking` field while `response` is empty, so the VLM client now parses either field.
- Added a fast VLM context-scene path, enabled by default, so `/sim/vision_scene` can use a real `source=vlm:qwen3-vl:latest:context` scene even when full image VLM is too slow; image VLM remains available through `SIM_VISION_IMAGE_VLM_ENABLED=1`.
- Updated blue VLA intents to log `VLA assigned pressure...` during normal pressure behavior so the run report can verify VLA pressure usage.
- Fixed the latest observed endgame failure where blue drones surrounded the final red drone without closing: when only one active red target remains, blue VLA now switches to `VLA endgame collapse...` direct pursuit for all controlled blue drones, and run reports detect this evidence.
- After `run_report_20260611_151145.md`, suppressed misleading old 1v1 live watcher summaries during team mode and made run reports distinguish context VLM scenes, image VLM scenes, coordinator vision acceptance, and plans that clearly used a vision hint.
- Added direct VLM-to-VLA evidence in the blue action controller: it now accepts `/sim/vision_scene`, logs `VLA accepted vision scene`, includes `VLA used vision source=vlm...` in blue action intents when fresh VLM evidence is present, and exposes both checks in run reports.
- Mirrored VLM-to-VLA evidence onto red: red and blue controllers now both log team-specific `VLA accepted vision scene` and `VLA used vision team=... source=vlm...` evidence, and run reports split red/blue VLA vision checks.
- Reviewed `run_report_20260611_154455.md` and fixed two bridge/accounting issues: run reports no longer drop early bridge logs on long runs, and the bridge now clears stale elimination state on a dirty `start_all` before a new red-elimination round begins.
- Fixed team reset placement so the bridge validates the nearest actual red/blue scoring pair distance, not only the two primary anchor drones; this prevents support drones from starting already inside catch range.
- Fixed blue active-target detection so low-altitude but still-active red drones are not mistaken for eliminated drones; only near-ground/eliminated red poses are ignored.
- Fixed the post-run reviewer after `run_report_20260611_160918.md` so an empty Qwen final response no longer exposes `thinking` text; reports now fall back to a deterministic markdown review.
- Fixed the team coordinator module so `python -m simworld_drone_ros.team.coordinator` actually starts the ROS node; this restores coordinator plans, coordinator vision acceptance, and coordinator-level VLM/VLA evidence.
- Updated run reports to include red/blue coordinator logs directly and flag whether coordinator plans, coordinator vision acceptance, and single-catcher scoring monopolies were seen.
- Tuned blue VLA support behavior so non-primary blue drones can perform assigned-target finish commits within the configured direct-commit distance, rather than leaving all scoring finishes to `blue_1`.
- Added explicit image-VLM launch paths: `vision.cmd --image`, `vision_image.cmd`, and `run_demo.cmd -ImageVision`, plus report fields for image-VLM enabled state and captured frame bytes.

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

## 2026-06-04

- Started Phase 5 as a VLM-assisted perception layer instead of jumping straight to a full trained VLA model.
- Added `simworld_drone_ros/vision/visual_observer.py`, which can position an UnrealCV camera near an observer drone, capture `lit` frames, and publish structured scene summaries to `/sim/vision_scene`.
- Added `simworld_drone_ros/vision/vlm_client.py` for Ollama multimodal generate calls, defaulting to `qwen2.5vl:7b`.
- Added `simworld_drone_ros/vision/scene_parser.py` to normalize VLM JSON and provide a pose/blocker fallback scene for testing.
- Updated team coordinators to subscribe to `/sim/vision_scene`, ignore stale or low-confidence scenes, include vision context in Ollama team prompts, and use vision only as a role-planning hint.
- Blue role planning can now split into `search`/`cutoff` sooner when vision reports blocked or uncertain runner sight.
- Red role planning can prefer `hide`/`decoy` support when vision reports cover or occlusion.
- Added `launch\vision.cmd` and optional `SIM_VISION_AUTOSTART=1` support in `launch\team_support.cmd`.
- Updated `launch\stop.cmd` so the visual observer is cleaned with the rest of the ROS runtime.
- Updated overview docs to describe the practical VLM-to-VLA-style path:
  `camera/image + pose/odom/state -> VLM scene JSON -> team coordinator -> safe controller velocity command`.
- Recorded the recommended first VLM path: use Qwen2.5-VL 7B/Instruct or the closest available Ollama tag first, move to larger Qwen2.5-VL/Qwen3-VL variants when hardware allows, and keep OpenVLA as future reference/fine-tuning scope rather than the first drone runtime model.
- Clarified the continuous-improvement target: VLM scene summaries plus match logs should improve each team's VLA-style planner through tactic weights, prompt/context updates, and validated role/goal plans between rounds, not raw velocity control or unsupported self-training claims.
- Switched the default VLM runtime model to `qwen3-vl:latest` after confirming that exact tag exists on the configured Ollama server and reports `vision` capability.
- Added `launch\vision_check.cmd` and `simworld_drone_ros/vision/check_vision_stack.py` to diagnose the VLM server, model tag, model capability, tiny generation, and optional UnrealCV camera capture.
- Found that `qwen3-vl:latest` tiny generate/chat checks timed out before the model appeared in `/api/ps`; the next operational fix is likely server-side model loading/VRAM/Ollama restart before full image perception can work.
- Fixed `launch\vision.cmd` startup crash caused by naming the background Python worker `self.executor`, which conflicts with ROS `rclpy.node.Node.executor`; the visual observer now uses `self.worker_executor`.
- Confirmed `launch\vision.cmd` now reaches `Vision observer ready`, connects to SimWorld through UnrealCV, and publishes fallback scene JSON when VLM output is not usable.
- Found that Qwen3-VL returned empty `response` when `num_predict` was too small because it spent tokens in the `thinking` field and stopped with `done_reason=length`.
- Increased VLM output budget defaults to `SIM_VLM_NUM_PREDICT=256`; a tiny Qwen3-VL generate test then returned `{"ok":true}` successfully.
- Added `SIM_VISION_CHECK_IMAGE_VLM=1` support to `launch\vision_check.cmd` so the stack can test UnrealCV camera capture plus actual image-to-VLM JSON output.
- Confirmed image VLM smoke test works: camera 0 returned a SimWorld frame, and Qwen3-VL described the gray indoor scene with tiled floors and a central column in JSON after about 20 seconds.
- Updated visual observer node naming so each observer uses a unique ROS node name such as `visual_observer_blue_1`.
- Updated `launch\vision.cmd` to accept an observer argument, such as `launch\vision.cmd blue_1` or `launch\vision.cmd red_1`.
- After `run_report_20260615_131529.md`, found that image VLM launched but the first worker was not clearly logged and timed out after the round had already ended; visual observer logging now always records each request, camera capture begin/ok with frame bytes, and image VLM request begin.
- Raised the live vision observer timeout default to `SIM_VISION_REQUEST_TIMEOUT_SEC=180` and kept `SIM_VLM_NUM_PREDICT=256` so the full run matches the successful image VLM smoke-test settings more closely.
- Switched `launch\review_latest_run.cmd` and the run report default reviewer to `gpt-oss:latest` so post-run markdown review does not compete with Qwen3-VL image vision by default.
- Added `simworld_drone_ros.vision.prepare_ollama` and wired it into `launch\vision.cmd` plus `launch\vision_check.cmd`; it automatically attempts to unload stale `magicoder:latest` and warm `qwen3-vl:latest` while leaving `gpt-oss:latest` available for team planning.
- Wired the same Ollama prep into team coordinator launch, raised team Ollama timeout from 20s to 60s, lowered team plan output budget to 128 tokens, and added `keep_alive` so `gpt-oss:latest` has a better chance of staying responsive during swarm role planning.
- Changed `launch\review_latest_run.cmd` so post-run review waits until Ollama finishes by default (`SIM_RUN_REPORT_TIMEOUT_SEC=0`) instead of timing out and immediately falling back to the deterministic review.
- Updated `SIM_VISION_AUTOSTART=1` behavior so team support starts primary blue/red visual observers, while all-ten per-drone VLM vision remains future scaling work.
