# Future Plan

This roadmap is ordered by what should be built next. Phase 1, Phase 2A, Phase 2B, and Phase 3 are done for the current scope.

The next main goal is no longer just better launch flow or ordinary tuning. The main goal is to test whether VLM + VLA-style agents can improve drone swarm attack and defence.

## Main Research Target

Build a drone-swarm-vs-drone-swarm system where each team uses:

- a team-specific VLA-style planner for live tactical decisions
- a team-specific supervising VLM for post-run review and continuous improvement
- limited perception context instead of omniscient direct coordinates for obstacles and OPFOR drones
- validated action outputs so model decisions cannot directly publish unsafe velocity commands

The intended direction:

```text
camera frames + local/self state + limited memory
-> Vision Observer / image VLM scene interpretation
-> Team Coordinator roles
-> Team Action Controller with Image VLA bias
-> validated safe movement commands
-> run logs/outcome
-> Run Reviewer
-> next-run strategy memory / tactic tuning
```

This should be adversarial in the practical sense: red and blue should not share private improvement notes or plans. Each side should review its own wins/losses and tune its own attack/defence behavior.

The next presentation goal is to make this runnable from a local browser dashboard instead of many separate command prompts.

## Simple Roadmap

| Order | Phase | Name | Main Goal | Status |
| --- | --- | --- | --- | --- |
| 1 | Phase 1 | Basic chase prototype | Spawn/control two drones and run a chase | Done |
| 2 | Phase 2A | One-vs-one tactical upgrade | LOS, memory, AI tactics, stamina, heat, and compact logs | Done |
| 3 | Phase 2B | Duel 3D baseline | Altitude control, climb/dive tactics, and bounded vertical motion | Done |
| 4 | Phase 3 | Team-vs-team support | Red-vs-white support drones with coordinators and dynamic roles | Done |
| 5 | Phase 4 | VLA/VLM swarm intelligence | Team-specific VLA planners plus VLM supervisors for continuous improvement | Active |
| 6 | Phase 4D | MVP dashboard | Browser control/report dashboard to replace many terminal windows | Next |
| 7 | Phase 5 | Perception realism | Reduce omniscient coordinates, improve camera/vision/world uncertainty, add better obstacles | Next after dashboard/VLA tuning |
| 8 | Phase 6 | Competitive learning loop | Longer adversarial experiments, scoring, memory, and tactic evolution | Future |

## Phase 4 - VLA/VLM Swarm Intelligence

Status: next implementation target.

Goal: implement a VLA-style planner for each team so drone swarms can conduct attack and defence more efficiently, then use a supervising VLM to review performance and improve each team's planner between runs.

Important interpretation:

- VLA here means a practical Vision-Language-Action style layer for this SimWorld drone system.
- It should output structured tactical actions such as role, target intent, search zone, intercept lane, cover/hide intent, and speed mode.
- It should not output raw uncontrolled velocity directly.
- Existing deterministic controllers remain the safety layer that validates and executes movement.
- Naming convention: see `overview\naming_convention.md` for the difference between Duel Brain, Vision Observer, Team Coordinator, Live Role Planner, Team Action Controller, Image VLA Bias, Run Reviewer, and Strategy Memory.

## Phase 4A - Post-Run VLM Supervisor

Status: implement first.

Why first:

The latest run showed that the VLM observer can start and request a scene, but there is not yet proof that vision is improving team behavior. A post-run reviewer gives us useful learning data without destabilizing live movement.

Build:

- `launch\review_latest_run.cmd`
- a Python report module under `simworld_drone_ros`
- markdown reports under `logs\run_reports\`
- newest-two report retention

Each report should state:

- what happened in the run
- whether bridge/team support/vision/VLM worked
- whether VLM produced usable observations
- whether each team behaved efficiently
- whether any drone looked idle, stuck, duplicated, or wasted
- whether blue stacked too many drones on one target
- whether red defended well through hiding, screening, decoying, or spacing
- who won/lost and why
- concrete changes for the next run

The supervising VLM should produce separate sections:

- red defender review
- blue attacker review
- neutral system health review
- recommended next-run VLA tuning

Retention:

```text
logs\run_reports\run_report_YYYYMMDD_HHMMSS.md
```

Keep only the latest two reports.

## Phase 4B - Team-Specific VLA Planner

Status: implement after report writer.

Goal: harden one VLA-style Team Coordinator plus Team Action Controller path per team.

Blue/white attacker VLA should learn to:

- locate likely red positions from vision summaries and memory
- avoid all drones stacking on the same target unless finishing a tag
- form intercept, cutoff, flank, and search patterns
- recover when the runner is lost
- assign drones to different pressure lanes
- tag efficiently without overcommitting

Red defender VLA should learn to:

- hide, decoy, screen, and bait
- break line of sight
- split support drones into useful defensive roles
- avoid drifting into easy tag range
- use cover/obstacles when perceived
- protect the runner or preserve survival time

The optional Live Role Planner output should be structured JSON, for example:

```json
{
  "team": "blue",
  "plan_confidence": 0.72,
  "drones": {
    "blue_1": {"role": "interceptor", "intent": "pressure_runner", "target_hint": "likely_runner", "lane": "center_cutoff", "speed": "intercept"},
    "blue_2": {"role": "flanker", "intent": "wide_left_search", "target_hint": "last_seen_red", "lane": "left", "speed": "search"}
  },
  "reason": "Runner is uncertain; split search while one interceptor holds pressure."
}
```

The runtime must validate this output before movement:

- allowed roles only
- allowed speed modes only
- no direct unsafe velocity from the model
- goals clamped to arena bounds
- fallback to deterministic Team Coordinator roles and Team Action Controller behavior if the output is invalid, stale, low-confidence, or timed out

## Phase 4C - Continuous Improvement Loop

Status: implement after the planner exists.

Goal: let each team improve between rounds based on its own VLM supervisor report.

The improvement loop should tune:

- team prompts
- role weights
- anti-stacking penalties
- search-vs-commit thresholds
- red hide/decoy/screen preferences
- blue flank/cutoff/intercept preferences

It should not claim magical self-training. The first version should be explicit prompt/context/tactic-weight tuning saved to local files.

Suggested files:

```text
logs\run_reports\run_report_YYYYMMDD_HHMMSS.md
logs\team_memory\red_vla_tuning.json
logs\team_memory\blue_vla_tuning.json
```

Keep the teams separate:

- red VLM supervisor sees red outcome, red logs, and neutral public match facts
- blue VLM supervisor sees blue outcome, blue logs, and neutral public match facts
- do not feed red's private improvement notes into blue
- do not feed blue's private improvement notes into red

## Phase 4D - MVP Dashboard

Status: next presentation milestone.

Goal: replace the many-command-prompt workflow with a local browser dashboard that can launch, control, monitor, and review the match.

The first useful version should include:

- one-button normal 5v5 image-vision launch
- stop, reset, and new-round controls
- settings for common run options:
  - 5v5 preset
  - image vision on/off
  - observer drone
  - catch radius
  - red/blue speed presets
- process health for bridge, target brain, chaser brain, team support, vision, and watcher
- live status/chase log tail
- latest report viewer
- button to run `launch\review_latest_run.cmd`
- simple health lights:
  - image VLM scene seen
  - Image VLA used vision
  - Live Role Planner healthy/fallback
  - all red/blue drones receiving nonzero `cmd_speed`
  - game-over seen

Recommended shape:

```text
local dashboard server
-> starts/stops launch scripts as subprocesses
-> publishes ROS control commands where needed
-> tails logs and reports
-> serves a browser UI at localhost
```

The dashboard should not replace the safe movement controller. It should only manage runtime processes, settings, logs, reports, and user controls.

## Phase 5 - Perception Realism

Status: next after VLA scaffold.

Goal: reduce omniscient direct knowledge so the VLA operates from vision-like and uncertain context.

Current system still has too much direct pose/coordinate knowledge. The future VLA should gradually move toward:

- local/self pose and velocity known
- teammate states known through team communication
- OPFOR known only through vision summaries, last-seen memory, or public events
- obstacle knowledge from camera/VLM/map memory, not perfect hard-coded coordinates
- uncertainty fields such as `visible`, `last_seen`, `confidence`, `occluded`, `unknown`

Potential tasks:

- improve camera placement and observer selection for each team
- publish vision summaries reliably and log every VLM response
- show vision summaries in panel and watcher
- add per-round metrics:
  - first sighting time
  - lost sight count
  - search recovery time
  - target stacking count
  - red survival time
  - tag time
- replace simple geometric blockers with real SimWorld/Unreal line traces if available
- add measured map presets for cover/blockers
- add search zones, gates, tunnels, and last-seen confidence

## Phase 6 - Competitive Learning Experiments

Status: future.

Goal: run repeatable adversarial experiments and compare whether VLM-supervised VLA improves over time.

Potential tasks:

- multi-round match manager
- scorekeeping and match timer
- report comparisons across rounds
- red/blue private strategy memory
- win/loss trend graphs
- difficulty presets
- larger teams if performance allows
- richer objectives beyond simple tagging

## Recommended Immediate Next Work

1. Build the MVP local dashboard so launch/control/report review can happen from one browser page.
2. Keep the existing launch scripts as the dashboard backend commands, rather than deleting the proven terminal flow.
3. Show latest run health from logs: image VLM, Image VLA, Live Role Planner, `cmd_speed`, eliminations, and game-over.
4. After the dashboard exists, continue runtime tuning:
   - simplify the red Live Role Planner prompt/output so `done_reason='length'` stops causing empty planner responses
   - add blue target-priority memory and action cooldowns
   - strengthen red screens, decoys, and recovery lanes
   - improve image VLM scene semantics
5. Later, add team-private strategy memory and multi-round experiment tracking.
