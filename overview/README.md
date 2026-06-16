# Drone Sim Overview

This folder is the living project overview for the red-vs-white drone AI simulator.

Update these files whenever behavior, scripts, AI prompts, win conditions, or roadmap direction changes:

- `current_phase.md` - where the project is right now.
- `current_features.md` - what the simulator currently supports.
- `future_plan.md` - planned phases and milestones.
- `LaunchInstructions.md` - how to run the current setup.
- `latest_update.md` - newest run review and proposed next implementation step.
- `change_log.md` - restored as a fresh current-tree change log after the old file was removed from Git history.

Current status: Phase 1, Phase 2A, Phase 2B, and Phase 3 are done for the current scope. Phase 5 has started with an opt-in VLM perception layer that publishes `/sim/vision_scene` for team coordinators to use as a tactical hint. The current priority is clean launches, reliable movement, tuning the 5v5 demo behavior, and validating vision-assisted role decisions without handing raw velocity control to a model.

Important operational note: use `launch\stop.cmd` before a fresh run. It publishes `stop_all` and cleans known stale source-module, team launcher, and old installed ROS entry-point processes so duplicate brains do not keep publishing conflicting commands.

The current 5v5 preset is demo-oriented: all ten drones move through team support, chasers are faster than targets, target hits drop red drones to `z=0`, and the match ends once all five targets are tagged.

VLM/VLA direction: the project should continue with a practical staged pipeline first:

```text
camera/image + pose/odom/state -> VLM scene summary -> team role planner -> safe controller velocity command
```

This is VLA-style integration, not full OpenVLA-style fine-tuning yet.

Latest review note: see `latest_update.md`. The roadmap is now aligned around VLM-supervised VLA for drone swarm attack and defence. The proposed next step is a post-run supervising VLM report saved under `logs\run_reports\`, keeping only the newest two reports, then using those reports to tune separate red defender and blue attacker VLA planners.
