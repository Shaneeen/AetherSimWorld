# Ultra Humanoid

## What It Is

Ultra Humanoid is the merged humanoid agent path for this project.

It combines:
- SimWorld native agent and map classes
- Ollama-based prompt parsing
- custom semantic target lookup
- direct coordinate navigation
- depth-guided final approach near objects

This is the current "best combined" humanoid path when you want:
- natural-language control
- semantic targets like `nearest building` or `visible store`
- cleaner architecture than the older custom script alone
- better final stopping than the native map-node planner alone

## Main Entry

- [main.py](/abs/path/d:/SimWorld/scripts/UltraHumanoid/main.py)

## Folder Layout

- [common.py](/abs/path/d:/SimWorld/scripts/UltraHumanoid/common.py)
  Runtime helpers, SimWorld startup helpers, local command parsing, and Ollama parsing.

- [Map/world_model.py](/abs/path/d:/SimWorld/scripts/UltraHumanoid/Map/world_model.py)
  World scanning, metadata lookup, semantic category inference, target ranking, and target-size estimates.

- [Vision/perception.py](/abs/path/d:/SimWorld/scripts/UltraHumanoid/Vision/perception.py)
  Depth helpers for the final approach stage.

- [Movement/navigation.py](/abs/path/d:/SimWorld/scripts/UltraHumanoid/Movement/navigation.py)
  Walk calibration, direct navigation, heading correction, and depth-based stop logic.

- [Robots/controller.py](/abs/path/d:/SimWorld/scripts/UltraHumanoid/Robots/controller.py)
  Command dispatch and user-facing runtime behavior.

## How It Works

The control loop is:

1. You type a command.
2. The agent tries a local parser first for common commands.
3. If needed, it sends the command to Ollama.
4. The agent resolves a semantic target from world data and metadata.
5. It walks toward that target directly instead of only going to a nearby map node.
6. When it gets close, it uses depth to decide when it is close enough to the object surface.

That last step is important.

Ultra Humanoid does not only stop by guessing a center-point radius anymore. It now uses depth as the main final-approach signal, with size-based distance kept as a fallback safety rule.

## What It Can Do

- Parse common navigation prompts locally or through Ollama.
- Go to coordinate targets.
- Go to semantic targets like:
  - `go to the nearest building`
  - `go to the nearest store`
  - `go to the visible store`
  - `go to the nearest tree`
- Scan nearby world objects and print what it sees from simulator metadata.
- Use SimWorld's native `Humanoid` and `Map` classes.
- Walk directly toward selected targets.
- Use depth in the final approach so it stops near the object surface instead of only aiming for the object center.
- Work in the custom comparison block world or the generated lightweight world.

## What It Cannot Do Yet

- It is not a full real-world robotics stack.
- It does not do true visual object detection from RGB alone.
- Most semantic understanding still comes from simulator object lists, names, and metadata.
- It does not yet do strong obstacle avoidance in cluttered scenes.
- It does not yet guarantee the perfect target choice for every ambiguous prompt.
- It does not yet do multi-step planning like:
  - `go to the store, then turn left and inspect the tree`
- It does not yet learn from previous runs automatically.
- It does not yet unify humanoid and drone into one shared agent framework.

## What It Is Especially Good For Right Now

- JJ-style prompt-agent demos
- comparing semantic target behavior against native SimWorld logic
- testing `nearest` versus `visible` target behavior
- evaluating whether depth-guided close approach feels better than graph-node stopping
- building the next main agent path for the project

## What Makes It Better Than The Earlier Two

Compared with the older custom humanoid:
- cleaner separation of concerns
- better reuse of SimWorld-native structures
- better final stopping behavior near target surfaces

Compared with the native experimental humanoid:
- better semantic target selection for your prompts
- direct approach toward the actual target marker or object
- less dependence on stopping at an unrelated nearby map node

## Commands

Supported commands include:

- `go to the nearest building`
- `go to the nearest store`
- `go to the visible store`
- `go to the nearest tree`
- `go to 1200 400`
- `look`
- `status`
- `help`
- `quit`

## Run

From `d:\SimWorld`:

```powershell
$env:OLLAMA_MODEL="phi3"
$env:SIMWORLD_COMPARISON_WORLD="1"
python scripts\UltraHumanoid\main.py
```

If you want the lightweight generated world instead:

```powershell
$env:OLLAMA_MODEL="phi3"
$env:SIMWORLD_GENERATE_WORLD="1"
python scripts\UltraHumanoid\main.py
```

If SimWorld is not already running:

```powershell
$env:SIMWORLD_AUTO_LAUNCH="1"
$env:OLLAMA_MODEL="phi3"
python scripts\UltraHumanoid\main.py
```

## Ollama Notes

Ultra Humanoid uses Ollama for prompt parsing when the command is not handled by the local shortcut parser.

Make sure Ollama is running:

```powershell
ollama serve
```

And make sure the model exists:

```powershell
ollama pull phi3
```

## How Depth Is Used

Depth is mainly used in the final approach phase.

The agent:
- navigates toward the target using world coordinates
- keeps turning to face the target
- when it is near enough, checks the center depth region
- stops when the visible front surface is close enough

This is better than stopping only by target-center distance because objects have real width and depth in the world.

## Best Testing World

For controlled evaluation, use the comparison block world.

That world gives you:
- small markers instead of oversized buildings
- a clear spawn area near the origin
- spaced-out semantic targets
- easier debugging for `nearest` and `visible` prompts

Related file:
- [comparison_world.py](/abs/path/d:/SimWorld/scripts/NativeAgents/comparison_world.py)

## Current Honest Status

Ultra Humanoid is the best humanoid architecture in this repo right now, but it is still a project bot, not a finished product bot.

It is already useful for:
- prompt-driven navigation demos
- target-comparison experiments
- developing the next version of the main agent

But it still needs more tuning if you want it to feel consistently strong in every world:
- better obstacle handling
- stronger visible-target scoring
- better final success criteria
- more robust close-range depth reasoning

## Recommendation

If you are moving forward with one humanoid path, this should be the one to keep improving.

The older custom humanoid is still useful as a reference.
The native experimental humanoid is still useful for architecture study.
But Ultra Humanoid is the best place to merge the strengths of both.
