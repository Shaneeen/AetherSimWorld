# Drone Sim Overview

This folder is the living project overview for the red-vs-white drone AI simulator.

Update these files whenever behavior, scripts, AI prompts, win conditions, or roadmap direction changes:

- `current_phase.md` - where the project is right now.
- `current_features.md` - what the simulator currently supports.
- `future_plan.md` - planned phases and milestones.
- `LaunchInstructions.md` - how to run the current setup.
- `change_log.md` - restored as a fresh current-tree change log after the old file was removed from Git history.

Current status: Phase 1, Phase 2A, Phase 2B, and Phase 3 are done for the current scope. The current priority is clean launches, reliable movement, and tuning the 5v5 demo behavior.

Important operational note: use `launch\stop.cmd` before a fresh run. It publishes `stop_all` and cleans known stale source-module, team launcher, and old installed ROS entry-point processes so duplicate brains do not keep publishing conflicting commands.

The current 5v5 preset is demo-oriented: all ten drones move through team support, chasers are faster than targets, target hits drop red drones to `z=0`, and the match ends once all five targets are tagged.
