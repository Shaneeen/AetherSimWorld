# Ultra Humanoid

## What It Does

Ultra Humanoid is the main prompt-driven humanoid controller in this repo.

It starts a SimWorld humanoid, reads typed commands, turns those commands into structured actions, scans the simulator for nearby objects, chooses a matching target, and walks the humanoid to it. For the last part of the approach, it uses depth data so the agent stops near the visible surface of an object instead of just aiming at a center point.

In practice, this is the repo's merged humanoid path:
- native `Humanoid`, `Map`, `Communicator`, and UnrealCV integration from SimWorld
- local command parsing for common shortcuts
- Ollama-based parsing for broader natural language requests
- semantic target resolution from simulator object names, metadata, and world JSON
- direct coordinate navigation with heading correction
- depth-guided close approach

## Main Entry

- [main.py](/abs/path/d:/SimWorld/scripts/UltraHumanoid/main.py)

## Folder Layout

- [common.py](/abs/path/d:/SimWorld/scripts/UltraHumanoid/common.py)
  Startup helpers, environment handling, local command parsing, and Ollama parsing.

- [Map/world_model.py](/abs/path/d:/SimWorld/scripts/UltraHumanoid/Map/world_model.py)
  World scanning, metadata loading, category inference, semantic filtering, deduping, and target selection.

- [Vision/perception.py](/abs/path/d:/SimWorld/scripts/UltraHumanoid/Vision/perception.py)
  Depth and mask helpers used during the final approach.

- [Movement/navigation.py](/abs/path/d:/SimWorld/scripts/UltraHumanoid/Movement/navigation.py)
  Walk-speed calibration, heading correction, forward stepping, stuck recovery, and final stopping logic.

- [Robots/controller.py](/abs/path/d:/SimWorld/scripts/UltraHumanoid/Robots/controller.py)
  Runtime command execution, semantic visit loops, status output, and help text.

- [run_ultrahumanoid.ps1](/abs/path/d:/SimWorld/scripts/UltraHumanoid/run_ultrahumanoid.ps1)
  Convenience launcher that starts Ollama if needed and runs the script with common environment settings.

## Runtime Flow

The control loop is:

1. Start or reuse SimWorld if auto-launch is enabled.
2. Wait for UnrealCV to become available.
3. Optionally load the comparison world or generate the lightweight world.
4. Build a SimWorld map and spawn a humanoid at the origin.
5. Calibrate walk speed with a short forward step.
6. Read user input from the `ultra>` prompt.
7. Try the local parser first.
8. If the command is not a simple built-in command, send it to Ollama for JSON parsing.
9. Execute the resulting action.

## Supported Behaviors

Ultra Humanoid currently supports:

- `help`, `status`, `look`, and `quit`
- direct coordinate movement such as `go to 1200 400`
- semantic movement such as `go to the nearest tree`
- visible-only semantic movement such as `go to the visible store`
- farthest-target selection such as `go to the furthest tree`
- different-target selection such as `go to another tree`
- repeated semantic visits such as `walk to 3 different trees`
- multi-step sequences when Ollama returns a `sequence` action

## How Semantic Navigation Works

When you ask for something like `nearest building` or `visible store`, Ultra Humanoid:

1. Scans simulator objects around the humanoid.
2. Pulls object location data from UnrealCV.
3. Loads metadata from:
   - `data/description_map.json`
   - `data/ue_assets.json`
   - `data/bounding_boxes.json`
4. Loads the active world JSON when available.
5. Infers categories such as `building`, `store`, `tree`, or `trash`.
6. Scores candidates by query-term matches.
7. Applies selector rules such as `nearest`, `farthest`, or `different`.
8. Chooses one target and walks directly toward it.

The `different` and `another` logic also tracks the last semantic target so repeated commands can avoid picking the same object again.

## How Navigation Works

Navigation is direct, not just graph-node based.

The controller repeatedly:
- reads the humanoid pose
- computes angle error to the target
- rotates if the heading is off
- steps forward for a computed duration
- checks for low-progress situations and performs small recovery turns

The walk speed is calibrated at startup, so the duration of each forward step is based on measured movement instead of a fixed guess alone.

## How Depth Is Used

Depth is used mainly in the close-range phase.

When the humanoid is near the target and roughly facing it, Ultra Humanoid samples a center crop from the depth image and computes min, median, and mean depth values. If the observed front surface is close enough, the agent stops. If depth is unavailable or not yet useful, it falls back to a size-based standoff distance estimated from metadata and object bounds.

That makes the final stop behavior more practical than stopping only by distance to an object's center.

## Worlds And Startup

`main.py` supports a few startup modes:

- `SIMWORLD_COMPARISON_WORLD=1`
  Loads the comparison evaluation world.

- `SIMWORLD_GENERATE_WORLD=1`
  Builds the lightweight generated world.

- `SIMWORLD_AUTO_LAUNCH=1`
  Starts SimWorld automatically if the UnrealCV port is not already open.

The helper script sets up a common local run with generated-world defaults and starts `ollama serve` if Ollama is not already listening on port `11434`.

## Example Commands

- `go to the nearest building`
- `go to the nearest store`
- `go to the visible store`
- `go to the nearest tree`
- `go to the furthest tree`
- `go to another tree`
- `walk to 3 different trees`
- `go to 1200 400`
- `look`
- `status`
- `quit`

## Run

From `d:\SimWorld`:

```powershell
$env:OLLAMA_MODEL="phi3"
$env:SIMWORLD_COMPARISON_WORLD="1"
python scripts\UltraHumanoid\main.py
```

Generated lightweight world:

```powershell
$env:OLLAMA_MODEL="phi3"
$env:SIMWORLD_GENERATE_WORLD="1"
python scripts\UltraHumanoid\main.py$
```

Auto-launch SimWorld if needed:

```powershell
$env:SIMWORLD_AUTO_LAUNCH="1"
$env:OLLAMA_MODEL="phi3"
python scripts\UltraHumanoid\main.py
```

Or use:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\UltraHumanoid\run_ultrahumanoid.ps1
```

## Current Limits

Ultra Humanoid is useful and fairly complete for repo demos, but it is still a project bot rather than a polished autonomous system.

Current limits include:
- semantic matching is driven mostly by simulator metadata and naming, not RGB understanding
- obstacle avoidance is minimal
- visibility is approximated mainly from relative angle, not full scene understanding
- sequence execution is linear and simple
- success still depends on world layout and target naming quality

## Bottom Line

Ultra Humanoid is the repo's strongest humanoid path for natural-language navigation right now.

If the goal is to keep improving one humanoid stack, this is the right place to do it because it already combines prompt parsing, semantic target selection, direct navigation, and depth-aware stopping in one flow.
