# Current Phase

## Phase 2B - Basic 3D Movement

The project is past the basic Phase 1 prototype and Phase 2A one-vs-one tactical upgrade. It now has a working red/blue drone chase loop with ROS control, SimWorld spawning, target/chaser brains, Ollama-assisted tactic choices, random fair resets, compact status watching, and initial 3D altitude control.

Status: Phase 2B started.

It is not yet full Phase 2 team-vs-team. The current work is the bridge between Phase 1 and Phase 2:

- Make the one-vs-one contest feel fairer and more believable.
- Replace fake visibility with simple line-of-sight logic.
- Make the chaser search when it loses sight instead of using perfect target knowledge.
- Make the target avoid weak left-right waiting behavior.
- Give the AI higher-level strategy choices, not just simple movement commands.

## What Phase 2A Means

Phase 2A is about improving the current one chaser vs one target setup before scaling to teams.

The aim is to prove:

- Red can evade intelligently.
- Blue can chase/search intelligently.
- Visibility and memory affect decisions.
- The AI can pick tactical strategies.
- The compact watcher can explain what is happening without reading full logs.

## Current Direction

The one-vs-one system remains the baseline test mode while vertical movement is added carefully.

Confirmed enough from Phase 2A:

- Simple LOS and memory affect decisions.
- Target stamina and chaser heat are visible in logs.
- Target no longer starts a new run with stale unstuck state.
- Target can recover from real low-movement/stuck moments.
- Compact watcher plus detailed saved logs are usable for debugging.

Remaining known issue:

- Map geometry can still create real low-speed/stuck moments later in long runs, but the detector now identifies them instead of hiding them.

Current Phase 2B work:

- vertical velocity control through `cmd.linear.z`
- min/max altitude limits, defaulting to Z 100-700 cm
- simple climb/dive/level target altitude tactics
- chaser altitude following
- swept bridge movement path so Unreal collision can block drones when supported

After Phase 2B:

- Phase 3: start small red-vs-white team behavior with 2v2 design and shared team state.
