# Latest Update

## 2026-06-16 Runtime Validation And Dashboard Next

Latest reviewed run: `logs/run_reports/run_report_20260616_230957.md`, generated from `logs/chase_watch/chase_detail_20260616_230642.log`.

What is good:

- Image VLM is still working:
  - `vlm_image_enabled=true`
  - `vlm_image_frame_seen=true`
  - `vlm_image_scene_seen=true`
  - `vlm_context_scene_seen=false`
- Image VLA is still working on both teams.
- The red multi-drone movement issue is fixed at the command layer. Team support now logs `cmd_speed={...}`, and the latest run showed nonzero movement commands for all five red drones after startup.
- The Live Role Planner now has partial success through Ollama `/api/chat`; successful plans are labeled `chat planner:`.
- Blue caught four of five red drones in the latest run.

What still needs fixing:

- The latest run did not reach game over; `red_1` survived.
- The red Live Role Planner still had fallback events. The new diagnostics showed one failure where `/api/chat` ended with `done_reason='length'`, empty message content, and hidden thinking, so the red prompt/output budget needs to be smaller and stricter.
- Blue endgame collapse still needs better final-runner capture quality.
- Red movement is now multi-drone, but red defense still needs stronger coordinated screens, decoys, baiting, and recovery lanes.
- The image VLM scene is useful but shallow; it should eventually identify target-specific visibility, occlusion, cover, and suggested assignments.

Decision:

The runtime has reached a good enough milestone to improve presentation and usability next. The next implementation target is an MVP local dashboard so the user can launch, control, monitor, and review matches from one browser page instead of opening many command prompts.

MVP dashboard should include:

- run normal 5v5 image-vision demo
- stop / reset / new round
- settings for common match options
- process health lights
- live log tail
- latest report viewer
- button to run `launch\review_latest_run.cmd`
- simple health checks for image VLM, Image VLA, Live Role Planner, `cmd_speed`, eliminations, and game-over

Runtime tuning after the dashboard:

1. Simplify red Live Role Planner prompt/output to avoid `done_reason='length'`.
2. Improve blue final-runner capture.
3. Add blue action cooldowns and target-priority memory.
4. Strengthen red screens, decoys, and recovery lanes.
5. Improve image VLM tactical scene semantics.

## 2026-06-15 Image VLM To VLA Milestone

The latest confirmed milestone is `logs/run_reports/run_report_20260615_162919.md`, generated from `logs/chase_watch/chase_detail_20260615_162647.log`.

What is good:

- The full 5v5 red-elimination match reached game over with all five red drones tagged.
- Image VLM is working end-to-end for this run:
  - `vlm_image_enabled=true`
  - `vlm_image_frame_seen=true`
  - `vlm_image_scene_seen=true`
  - `vlm_context_scene_seen=false`
- The bridge published camera frames and the observer produced image-scene evidence instead of falling back to context VLM.
- The coordinator accepted vision and the report saw vision-influenced planning.
- The VLA action layer accepted and used fresh VLM vision for both red and blue.
- Blue scoring was no longer a single-drone monopoly: `blue_1` caught two red drones and `blue_2` caught three.

What is still bad:

- The optional Live Role Planner can still print `live role planner fallback` when `gpt-oss:latest` returns empty or invalid JSON. That is not the same thing as image VLM or Image VLA failing.
- Blue VLA behavior is still repetitive. It needs target-priority memory, cooldowns, and cleaner pincer/search diversity.
- Red defender behavior is still weak. It needs actual coordinated screens, decoys, recovery lanes, and better survival logic.
- Swept Unreal movement still falls back to direct UnrealCV movement.
- The image VLM scene is usable, but still too shallow. It should produce richer facts about which drones are visible, which targets are occluded, where cover is, and what assignment each blue/red drone should prefer.
- Warning count is still high, so the system is not yet stable enough to call Phase 4 complete.

Conclusion:

This is a milestone, but not the finish line. The project has moved from "make image VLM connect" to "make the image-VLM-informed VLA behave intelligently."

Next step:

1. Improve blue VLA target-priority and intent diversity.
2. Improve red defender VLA coordination.
3. Harden or simplify the optional Ollama role planner so fallback noise does not hide real system health.
4. Improve image VLM prompts and parsing for richer tactical scene summaries.
5. Keep using `review_latest_run.cmd` after each match and judge progress by image-VLM evidence, VLA usage, catch distribution, repeated intents, red survival quality, and warning count.

## 2026-06-11 Vision Observer Follow-Up

The SimWorld camera examples use explicit UnrealCV camera commands before image capture, including camera discovery, camera resolution setup, and `lit` frame capture. The project observer already used the same raw UnrealCV command shape, but the latest run exposed a runtime weakness: after `Vision observer request: mode=vlm`, a slow or stuck VLM call could leave `/sim/vision_scene` unpublished.

Follow-up from `run_report_20260611_135402.md`:

- The missing vision scene was partly a launch-order bug. `team_support.cmd` was cleaning up `vision.visual_observer`, so a vision tab launched before `start.cmd` could be killed when team support restarted.
- Team support cleanup now only stops team coordinator/controller nodes. It stops old vision observers only when `SIM_VISION_AUTOSTART=1`, then starts fresh autostarted vision logs.
- The observer now publishes a warm fallback scene as soon as poses exist, before waiting for the larger VLM response. This should make `vision_scene_seen=true` in the next report even if Qwen3-VL is slow.
- The fallback scene confidence is now high enough for team coordinators to consume as a low-authority hint.

Follow-up from the same run's flawed chase behavior:

- Blue repeated `direct commit on red_1` about 300 times.
- The direct-commit threshold was too broad for a finishing behavior, so multiple white drones could abandon their roles and collapse onto red_1 while other active red drones stayed at the side.
- Blue now has a narrower VLA finish radius. Close drones do a true finish commit directly into tag range; other drones keep role/target assignments and pressure active red support drones.
- Team support logs now include `vla_action=1`, plus intents such as `VLA finish commit...` or `VLA assigned pressure...`, so the next run report can prove whether VLA-style action selection was active.

Runtime update:

- `launch\vision.cmd` now defaults to 320x240 camera frames.
- `SIM_VLM_TIMEOUT_SEC` defaults to `40` for live vision.
- `SIM_VISION_REQUEST_TIMEOUT_SEC` defaults to `45`.
- `SIM_VLM_NUM_PREDICT` defaults to `768` for live vision.
- The observer logs available UnrealCV cameras and camera size.
- The observer logs image-to-VLM response duration and frame size when a response returns.
- If the VLM exceeds the observer timeout, the observer publishes a fallback `/sim/vision_scene` instead of going silent.

What to check in the next run:

- `Vision observer camera ready: ...`
- `Vision observer response: duration=... frame_bytes=...`
- `Vision scene: ... source=vlm:qwen3-vl:latest ...`
- Or, if Qwen3-VL is too slow: `Vision observer timeout:` followed by `Vision scene: ... source=pose_fallback ...`

The main success condition is no longer just "VLM started." The next run should prove that a scene, VLM or fallback, is actually published and visible to team support.

## 2026-06-11 Run Review

This update is a review note before changing runtime code.

Latest observed behavior:

- The 5v5 runtime launched and the bridge connected to UnrealCV.
- Team support started for both red and blue.
- Pose data eventually became available for all drones after the first startup moments.
- The match did not look efficient. Blue/white repeatedly issued similar pressure/direct-commit intents, especially after most red drones were eliminated.
- The watcher repeatedly printed `TARGET no target move yet || CHASER no chaser commit yet`. This appears to be partly a watcher limitation: those old fields describe the original 1v1 target/chaser brains and do not reliably summarize team-support movement.
- In the latest bad-looking run, red_2, red_5, red_4, and red_3 were eliminated, but the final red_1 tag was not clearly completed in the bridge log snapshot that was reviewed.
- The bridge still reports `swept movement unavailable` and falls back to UnrealCV direct location moves. This is not fatal, but it means movement depends on software bounds/spacing instead of real Unreal swept collision.

Most likely issues:

- The team logic is still too repetitive after support drones are eliminated. Several blue/white drones can keep committing toward the same remaining red target instead of reforming into a cleaner pincer/search net.
- Some drones can look frozen or useless even when commands are being issued, because the current logs do not report per-drone actual movement efficiency.
- The compact watcher needs a team-mode health summary instead of relying on the older 1v1 target/chaser status lines.

## Historical VLM Usage Status

This section records the older 2026-06-11 state. It has been superseded by the 2026-06-15 image-VLM milestone above.

Older evidence from the 2026-06-11 vision log:

```text
Vision observer ready: enabled=1 vlm=1 observer=red_1 camera=0 dt=2.5s blockers=0 model=qwen3-vl:latest
Vision observer request: mode=vlm observer=red_1 poses=10 blockers=0
```

At that time, this proved:

- `qwen3-vl:latest` was enabled.
- The visual observer started.
- The observer had pose context for all 10 drones.
- A VLM request was made.

At that time, the older run was missing:

- a logged VLM response
- a logged parsed `/sim/vision_scene`
- a clear team-support line showing that a fresh vision scene changed role choice

Conclusion:

The older VLM path was alive but not yet meaningfully improving the run. The current state is different: the 2026-06-15 16:29 report proves image-VLM scene publication, coordinator acceptance, and VLA use. The remaining work is tactical quality and robustness, not basic image-VLM connectivity.

## Corrected Main Direction

The next implementation target should be the VLM-supervised VLA system, not just ordinary VLM perception.

The project goal is:

```text
Use VLM supervisors to continuously improve each team's VLA-style planner for drone swarm attack and defence.
```

This means:

- blue/white gets an attacker VLA planner
- red gets a defender VLA planner
- each team gets its own VLM supervisor/reviewer
- each VLM supervisor produces private improvement notes for its own team
- the teams should not share private plans or tuning notes
- the VLA should gradually depend less on direct OPFOR/obstacle coordinates and more on vision summaries, uncertainty, memory, and local state
- the safe controller remains responsible for validated movement

## Proposed First Change: VLM Run Report

Before trying to make the VLA influence live movement, add a post-run report writer.

Goal:

Use the larger VLM as a supervising reviewer after each run, not as a direct controller. It should read the latest run logs and write a short markdown report under `logs\run_reports\`.

Report should include:

- what happened in the run
- whether launch/bridge/team support/vision worked
- whether VLM was started, returned a scene, and was used meaningfully
- whether any drone appeared stuck, idle, duplicated, or inefficient
- whether blue/white stacked too many drones on one red target
- whether red got useful decoy/screen/hide behavior
- what broke or looked suspicious
- concrete next-run tuning suggestions
- red defender VLA improvement suggestions
- blue attacker VLA improvement suggestions

Retention:

- Keep only the newest two reports.
- Delete older reports automatically.

Suggested file names:

```text
logs\run_reports\run_report_YYYYMMDD_HHMMSS.md
```

Suggested command:

```powershell
.\launch\review_latest_run.cmd
```

Optional later behavior:

- `launch\start.cmd` can call the reviewer after the watcher exits.
- `launch\run_demo.cmd` can get a `-ReviewAfter` option.

Important safety rule:

The report writer should not change drone behavior during the match. It should only observe logs after a run and suggest improvements. Runtime movement should stay with the existing safe controllers until the report quality is reliable.

## Proposed Report Inputs

The report generator should gather:

- newest `logs\chase_watch\chase_detail_*.log`
- newest bridge `python_*.log` containing `ue_bridge`
- newest target/chaser brain logs
- newest red/blue team support logs
- newest vision observer log, if present
- optional `vision_check` result if available

Useful metrics to compute before sending to the VLM:

- match duration
- eliminated drones and timestamps
- remaining active drones at end
- startup missing-pose duration
- repeated identical team intents
- per-drone target stacking from intent strings
- VLM ready/request/response/publish evidence
- bridge fallback mode and major warnings
- explicit errors, tracebacks, or failed connections

## Proposed Implementation Order

1. Add `simworld_drone_ros/vision/run_report.py` or a neutral `simworld_drone_ros/analysis/run_report.py`.
2. Add `launch\review_latest_run.cmd`.
3. Generate a deterministic local summary first from logs.
4. Send that compact summary to the VLM for human-readable recommendations.
5. Save the markdown report and keep only the latest two.
6. After the reports look useful, decide whether to feed report findings into next-round tactic weights.

This keeps the current system safe while moving toward the original idea:

```text
run logs + VLM review -> better next-run tactics and tuning
```
