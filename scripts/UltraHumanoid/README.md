# Ultra Humanoid

## Overview

Ultra Humanoid is the prompt-driven humanoid controller for this repo.

It reads typed commands, parses them locally or through Ollama, scans the simulator for matching objects, resolves semantic targets like `nearest tree` or `visible store`, and walks directly toward them with depth-guided stopping near the visible surface.

Ultra Humanoid is now self-contained inside `scripts/UltraHumanoid` for its script-level logic. It no longer depends on `scripts/NativeAgents` or the older `scripts/humanoid` helpers. It still uses the core `simworld` package for the simulator agent, map, communicator, and world-generation infrastructure.

## Run

From `D:\SimWorld`:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\UltraHumanoid\run_ultrahumanoid.ps1
```

That launcher will:

- start `ollama serve` if Ollama is not already running
- start `SimWorld.exe` if SimWorld is not already running
- open the empty map
- wait for you to confirm the world is loaded
- connect to UnrealCV
- generate or load the configured world
- start the Ultra Humanoid controller

## If SimWorld Is Already Open

Run the same command:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\UltraHumanoid\run_ultrahumanoid.ps1
```

It will reuse the existing SimWorld session if UnrealCV is already available.

## Important Prompt

When you see:

```text
Loaded? [Enter/1]:
```

press `Enter` or type `1`, then press `Enter`.

## Startup Modes

The main script supports:

- `SIMWORLD_GENERATE_WORLD=1`
  Generate and load the lightweight procedural world.

- `SIMWORLD_COMPARISON_WORLD=1`
  Load the deterministic comparison world used for semantic target testing.

- `SIMWORLD_AUTO_LAUNCH=1`
  Launch SimWorld automatically if it is not already running.

- `SIMWORLD_FIXED_WORLD_JSON=...`
  Load a specific world JSON file instead of generating one.

## Commands

Examples:

```text
go to the nearest building
go to the nearest store
go to the visible store
go to the nearest tree
go to the furthest tree
go to another tree
walk to 3 different trees
go to 1200 400
look
status
help
quit
```

For simple commands, Ultra Humanoid uses a local parser first.
For broader natural-language requests, it asks Ollama to return structured JSON actions.

## How It Works

At a high level, the runtime does this:

1. Launch or connect to SimWorld.
2. Clear old humanoid/helper actors from previous runs.
3. Load the comparison world or generate the lightweight world if requested.
4. Build a map and spawn a SimWorld humanoid.
5. Calibrate walk speed.
6. Read commands from the `ultra>` prompt.
7. Resolve either coordinates or semantic targets.
8. Navigate directly toward the target.
9. Use depth data during the final approach to stop near the object surface.

## Files

- main entry: `scripts/UltraHumanoid/main.py`
- launcher: `scripts/UltraHumanoid/run_ultrahumanoid.ps1`
- startup and parsing helpers: `scripts/UltraHumanoid/common.py`
- self-contained world helpers: `scripts/UltraHumanoid/worlds.py`
- world scanning and target resolution: `scripts/UltraHumanoid/Map/world_model.py`
- movement and close approach: `scripts/UltraHumanoid/Movement/navigation.py`
- depth helpers: `scripts/UltraHumanoid/Vision/perception.py`
- command execution: `scripts/UltraHumanoid/Robots/controller.py`

## Notes

- Semantic selection is driven mostly by simulator object names, metadata, and world JSON.
- Final stopping uses depth when available, with size-based fallback logic.
- The code is designed to keep working even if the old script folders are removed, as long as the core `simworld` package remains present.
