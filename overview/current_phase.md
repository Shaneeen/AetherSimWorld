# Current Phase

## Phase 1 / 2A / 2B / 3 Done Baseline

The project is past the basic chase prototype and the one-vs-one tactical upgrade. It now has a working red-vs-white drone chase loop with ROS control, SimWorld bridge movement, target/chaser brains, Ollama-assisted tactic choices, fair resets, compact status watching, 3D altitude movement, and live support-drone team behavior.

Status:

- Phase 1 is done: basic spawn/control/chase loop exists.
- Phase 2A is done: one-vs-one tactics, LOS, memory, stamina, heat, AI tactics, and compact logs exist.
- Phase 2B is done for current scope: altitude-aware duel behavior, bounded vertical velocity, climb/dive/level tactics, chaser altitude following, and simple blocker/arena guard behavior exist.
- Phase 3 is done for current scope: team support up to 5v5 exists with red/blue coordinators, scoped support controllers, dynamic roles, spacing, screen clearing, search lanes, and red-elimination support.
- Phase 4 is now active: the first image-VLM-to-VLA closed loop has been proven, and the next work is tactical quality, planner robustness, and better defender/attacker behavior.

The strongest baseline remains the normal duel brain setup for 1v1. The current 5v5 demo preset moves all ten drones through team support so `DroneA`/`DroneB` no longer sit on hold during team matches.

The current direction is to harden the practical VLA-style planner for each team, supervised by VLM scene perception and post-run VLM review. This is not raw velocity control from a model. The VLA proposes structured roles/goals/actions, and the existing controller validates and executes safe movement.

## Current Direction

Current work is not about reopening Phase 2B or Phase 3. The focus is now improving the VLM-supervised VLA swarm loop:

- richer image-VLM scene summaries from the bridge-owned camera stream
- separate red defender and blue attacker VLA-style planners
- team-private improvement notes so red and blue do not share strategy tuning
- less omniscient OPFOR/obstacle knowledge over time
- safe controller validation so VLA output cannot directly create unsafe movement
- readable logs proving whether VLM/VLA helped or failed

## Current Milestone

The 2026-06-15 16:29 run report (`logs/run_reports/run_report_20260615_162919.md`) is the first full image-VLM-to-VLA milestone.

The 2026-06-16 23:09 run report (`logs/run_reports/run_report_20260616_230957.md`) is the latest behavior-validation checkpoint. It did not reach game over, but it proved the red multi-drone movement fix: Team support reported nonzero `cmd_speed` for all five red drones after startup, so red is being commanded as a swarm rather than only one drone moving.

Good evidence:

- The run reached red-elimination game over: all five red drones were tagged.
- Image VLM was enabled and produced usable image-scene evidence:
  - `vlm_image_enabled=true`
  - `vlm_image_frame_seen=true`
  - `vlm_image_scene_seen=true`
  - `vlm_context_scene_seen=false`
- The coordinator accepted fresh vision and the report saw vision-influenced planning.
- The VLA action layer accepted and used VLM vision for both teams.
- Scoring was distributed across `blue_1` and `blue_2`, instead of only one blue drone doing all confirmed catches.
- Startup pose availability stabilized, with no lasting missing-pose issue.
- Later validation showed red support commanding all five red drones at once with nonzero `cmd_speed`.
- The Live Role Planner now sometimes succeeds through Ollama `/api/chat`, and successful plans are labeled with `chat planner:`.

Bad or incomplete evidence:

- Some `live role planner fallback` lines are still coming from the optional Ollama helper inside the Team Coordinator, not from image VLM. The deterministic Team Coordinator and Image VLA Action Controller continue running, but the optional Live Role Planner still sometimes returns empty or non-JSON output.
- The latest red planner fallback showed `done_reason='length'` with hidden thinking and empty message content, so the red planner prompt/output budget still needs simplification.
- Blue intent quality is still repetitive. The swarm can keep issuing similar pressure/collapse intents instead of showing cleaner target priority, pincer diversity, and cooldown behavior.
- Red movement is now visibly multi-drone, but red defense is still weak. It needs better screens, decoys, recovery lanes, and survival logic.
- The bridge still reports swept movement unavailable and falls back to direct UnrealCV location moves.
- Image VLM is now alive, but its scene summaries are still shallow: mostly visibility/search/confidence rather than rich occlusion, cover, and target-specific tactical facts.
- Warning count is still high enough that each run report should be checked before calling the system stable.

## Recently Restored / Confirmed

- Launch scripts run source modules with `python -m simworld_drone_ros...` instead of old installed ROS console entry points.
- `launch\stop.cmd` publishes `stop_all` and cleans stale source-module, team launcher, and old installed entry-point processes such as `chaser_brain.exe` and `chaser_brain-script.py`.
- The bridge can load saved team sizes and adopt existing manual drones up to 5v5.
- In 5v5, red_1 and blue_1 are also team-controlled so all ten drones move.
- Red support can screen, decoy, hide, or bait, and now uses per-drone swarm lanes instead of shared escape directions.
- Blue support can flank, clear screens, cut off lanes, deny center, or split into search lanes.
- Red-elimination mode can tag any active target when `SIM_TEAM_CATCH_MODE=any`.
- Eliminated red drones drop to `SIM_TEAM_ELIMINATION_GROUND_Z`, default `0`, and are held out until reset.
- The current 5v5 preset stops the game once all five red targets are down.
- The current 5v5 preset uses a demo-friendly `SIM_CATCH_DISTANCE=220` and a chaser intercept speed about `1.75x` the target burst speed.
- `launch\panel.cmd` opens a chaser/target team panel with action pulses and `TAGGED` display for targets at `z=0`.
- The bridge uses a software arena guard for direct UnrealCV movement:
  - `SIM_TARGET_BOUND_X=1350`
  - `SIM_TARGET_BOUND_Y=1350`
  - `SIM_ARENA_BOUNDARY_MARGIN_CM=90`
- Swept Unreal movement is still attempted when available, but current UnrealCV runs may fall back to direct location updates.
- The bridge can publish camera frames on `/sim/camera_frame`, and the visual observer can consume those bridge-owned frames for image VLM instead of opening a second UnrealCV connection.
- Image VLM now remembers the mission goal from `overview\future_plan.md` through the launch environment.

## Known Issues

- Direct UnrealCV movement cannot use real Unreal mesh collision. Software bounds, drone spacing, and configured blockers are the current workaround.
- Measured arena bounds may need tuning if the visible main wall does not match the `1350/1350/90` default.
- Red-elimination is functional, but there is no full scoreboard, timer, summary, or replay metrics layer yet.
- Support drones do not yet have per-drone stamina/heat.
- Real Unreal raycast perception is not implemented yet.
- VLM perception depends on stable bridge camera frames and a reachable multimodal Ollama model.
- Current vision integration is VLA-style role assistance, not trained direct vision-to-action control.
- Image VLM has now been proven end-to-end in the 2026-06-15 16:29 run, but the semantic scene quality still needs improvement.
- The visual observer now prefers bridge-owned `/sim/camera_frame` frames and only uses direct UnrealCV capture if explicitly enabled.
- The latest failed vision evidence was also caused by launch cleanup: `team_support.cmd` could kill a manually started visual observer. Team support no longer kills manual vision observers unless `SIM_VISION_AUTOSTART=1` is replacing them.
- Blue attack now has a first-pass VLA action layer: close drones finish directly, while non-finishing drones stay assigned across active red targets instead of repeatedly collapsing onto `red_1`.
- Team-mode watcher output still includes old 1v1 status lines such as `TARGET no target move yet || CHASER no chaser commit yet`, which can be misleading during 5v5 team-support runs.
- Blue/white repetition is improved but not solved; the next tuning target is target-priority memory, action cooldowns, and less repeated intent text.
- Team coordinator Ollama fallback is still possible when `gpt-oss:latest` returns empty or invalid JSON. This should be treated as role-planner fragility, not proof that image VLM failed.

## Next Practical Step

The project is at an image-VLM-to-VLA runtime milestone, not a finished swarm-intelligence product milestone. The next practical step is presentation and operability: build an MVP local dashboard so the match can be launched, controlled, reviewed, and explained without opening many terminal windows.

MVP dashboard goals:

1. Start the normal 5v5 image-vision demo from one browser page.
2. Stop, reset, and start a new round from the page.
3. Show process health for bridge, team support, vision, watcher, and planner.
4. Tail the latest status/chase log.
5. Run `launch\review_latest_run.cmd` from a button.
6. Open the latest markdown report in the browser.
7. Surface key health lights: image VLM, Image VLA, Live Role Planner, red/blue command speeds, and game-over state.

Behavior quality remains the next runtime tuning track after the dashboard MVP:

1. Add target-priority memory, intent cooldowns, and action diversity to blue VLA so drones stop repeating the same collapse/pressure pattern.
2. Strengthen red defender VLA with actual screen/decoy/recovery-lane behavior instead of mostly individual escape outlets.
3. Harden the team Ollama role planner so empty or non-JSON responses are repaired or ignored without noisy post-game fallback lines.
4. Improve image VLM prompts and parsing so scene output includes target-specific visibility, cover, occlusion, and suggested assignments.
5. Investigate swept movement fallback separately; direct UnrealCV movement works, but it is not the final collision/physics behavior.

For the next validation run:

```powershell
.\launch\stop.cmd
```

Then restart with the image-vision path and run a full match. In the report, the key health checks are now:

- `vlm_image_scene_seen=true`
- `vlm_context_scene_seen=false`
- `coordinator_accepted_vision_seen=true`
- `vla_used_vlm_vision_seen=true`
- catches split across more than one blue drone
- fewer repeated team intents
- no team Ollama fallback spam after STOP

After the run, use the post-run reviewer:

```powershell
.\launch\review_latest_run.cmd
```

It reads the latest run logs, writes `logs\run_reports\run_report_YYYYMMDD_HHMMSS.md`, keeps only the newest two reports, and summarizes what happened, what broke, whether image VLM was meaningful, and what each team's VLA should improve next.
