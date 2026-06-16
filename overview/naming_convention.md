# Naming Convention

This file defines the plain-language names for the current AI/control layers. Use these names in docs, logs, reports, and future code where practical.

## Simple Mental Model

```text
Camera / poses
-> Vision Observer
-> Scene Summary
-> Team Coordinator
-> Team Action Controller
-> Drone velocity commands
-> Run Report / Strategy Memory
```

## Runtime Layers

### Duel Brain

Meaning:

- The old one-vs-one `target_brain` and `chaser_brain`.
- Handles classic red_1 vs blue_1 chase behavior.
- Can ask Ollama for a tactic, but falls back to local rules.

Use this name for:

- `Target brain ...`
- `Chaser brain ...`
- 1v1 movement/tactic logs

Do not use this name for:

- 5v5 team movement
- image VLM interpretation
- post-run review

### Vision Observer

Meaning:

- The node that captures or receives camera frames.
- Sends those frames to the VLM.
- Publishes `/sim/vision_scene`.

Main output:

```text
Vision scene: observer=blue_1 source=vlm:qwen3-vl:latest ...
```

Short name:

- Vision Observer

Model name:

- Image VLM, usually `qwen3-vl:latest`

### Scene Summary

Meaning:

- The structured JSON produced by the Vision Observer.
- It says what the camera thinks is visible or uncertain.

Examples:

- `runner_visible`
- `blocked_by`
- `recommended_search_area`
- `suggested_tactic`
- `confidence`

Important:

- A scene summary is not a movement command.
- It is evidence for the planner/controller.

### Team Coordinator

Meaning:

- The team-level role assigner.
- Publishes roles such as `interceptor`, `screen`, `decoy`, `hide`, `cutoff`, and `search`.
- Uses live geometry and can use fresh vision scenes as hints.

Main output:

```text
Team coordinator plan: team=blue, roles=..., reason=...
```

This should be called:

- Team Coordinator

Not:

- the brain
- the VLM
- the controller

### Live Role Planner

Meaning:

- The optional Ollama-powered helper inside the Team Coordinator.
- Uses `gpt-oss:latest` by default.
- Tries to return strict JSON role plans.

Important:

- This is the flaky layer that may print fallback.
- If it fails, the Team Coordinator still uses deterministic roles.
- If it fails, Image VLM and Image VLA may still be working.

Preferred log wording:

```text
PLANNER: live role planner fallback - ...
```

Avoid wording:

```text
AI fallback
```

because it sounds like the whole AI system failed.

### Team Action Controller

Meaning:

- The safe real-time movement controller for team drones.
- Converts roles and scene hints into bounded velocity commands.
- This is the layer that actually moves drones in 5v5.

Main output:

```text
Team support active: scope=blue, roles=..., intent=...
```

This should be called:

- Team Action Controller
- safe controller

Not:

- raw VLA model
- VLM

### Image VLA Bias

Meaning:

- The current practical VLA-style behavior.
- Fresh image VLM scene summaries directly bias the Team Action Controller's goals.

Examples:

- Blue tightens pincer/support pressure when image VLM sees the runner.
- Blue splits search lanes when image VLM reports blocked or uncertain sight.
- Red widens screens and decoys when image VLM sees the runner.
- Red preserves broken-sight outlets when vision is uncertain.

Main output:

```text
Image VLA used vision team=blue source=vlm:qwen3-vl:latest ...
```

Important:

- This is not a trained OpenVLA model.
- It is a safe, structured Vision-Language-Action style layer.
- It does not publish raw velocity directly.

### Run Reviewer

Meaning:

- The post-run report generator.
- Reads chase logs and writes markdown reports.
- Can use VLM/Ollama for review, but reports fall back to deterministic summaries if needed.

Main command:

```powershell
.\launch\review_latest_run.cmd
```

Main output:

```text
logs\run_reports\run_report_YYYYMMDD_HHMMSS.md
```

### Strategy Memory

Meaning:

- Future per-team saved improvement notes/tuning.
- Not fully implemented yet.

Planned files:

```text
logs\team_memory\red_vla_tuning.json
logs\team_memory\blue_vla_tuning.json
```

Important:

- This is where post-run improvements should eventually become next-run behavior.
- Red and blue memory should stay separate.

## Failure Wording

Use precise failure names:

- `image VLM fallback`: the vision model/image path failed or timed out.
- `pose fallback`: no usable image scene; using geometry fallback.
- `live role planner fallback`: optional Ollama role JSON failed.
- `duel Ollama fallback`: old 1v1 brain tactic model failed.
- `safe controller fallback`: movement stayed with deterministic controller rules.

Avoid broad wording:

- `AI failed`
- `VLA failed`
- `brain failed`

Those are too vague and make debugging harder.

## What Matters Most In Reports

For image VLM/VLA health, check:

- `vlm_image_scene_seen=true`
- `vlm_context_scene_seen=false`
- `coordinator_accepted_vision_seen=true`
- `vla_used_vlm_vision_seen=true`
- `Image VLA used vision...` in chase detail logs

For live role planner health, check:

- `Team coordinator cached Ollama plan...`
- no repeated `live role planner fallback`

For match quality, check:

- catches distributed across multiple blue drones
- fewer repeated identical intents
- red survival time improves
- red uses screens/decoys/hide lanes effectively
- target/chaser do not get stuck for long periods
