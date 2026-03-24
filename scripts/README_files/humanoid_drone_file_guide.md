# Humanoid And Drone Folder Guide

## Short Answer

- `scripts/humanoid` uses Ollama.
- `scripts/Drone` now also uses Ollama.

## What That Means

The two folders solve similar high-level problems, but they are built with different control styles.

The `humanoid` package is a prompt-driven controller. It accepts natural-language commands like "go to the nearest store" or "turn right and walk 5 steps". To do that, it sends text to a local Ollama model and asks the model to convert the sentence into a structured command. It also uses Ollama again when it needs to rank semantic navigation candidates, for example deciding which nearby object best matches a phrase like "the left tree" or "closest building".

The `Drone` package now also uses a prompt-driven parser. It sends user text to a local Ollama model and asks the model to convert the sentence into a structured drone command such as `takeoff`, `orbit`, `goto`, or `above_nearest_tree`. Its movement logic is still geometric and vision-based, but its text understanding is now language-model-based rather than regex-based.

## Humanoid Folder Overview

Folder: [scripts/humanoid](/abs/path/d:/SimWorld/scripts/humanoid)

This package is the refactored version of the old monolithic `prompt_agent.py`. It separates the humanoid controller into smaller modules so each part has a clearer responsibility.

### Architecture

- `main.py` is the runtime entrypoint for the humanoid agent.
- `common.py` holds shared constants, startup helpers, command parsing helpers, and Ollama integration.
- `map/` contains world lookup and semantic candidate selection logic.
- `movement/` contains movement, calibration, and coordinate navigation logic.
- `vision/` contains image captioning and vision dependency checks.
- `robots/` contains high-level command execution routing.
- `world.py` handles optional procedural world generation and scene overrides.

### How Humanoid Works

1. `main.py` starts SimWorld if needed, connects to UnrealCV, and spawns a humanoid.
2. It calibrates walk speed so motion timing better matches the live simulation.
3. It reads user input in a loop.
4. `common.py` first tries simple local parsing for shortcut phrases.
5. If local parsing does not match, `common.py` sends the text to Ollama.
6. `robots/humanoid_commands.py` dispatches the parsed action.
7. For semantic navigation, `map/humanoid_map.py` surveys visible or nearby objects and can use Ollama to rank which candidate best matches the request.
8. For image description, `vision/humanoid_vision.py` runs BLIP captioning locally.

### Humanoid File Details

#### [scripts/humanoid/main.py](/abs/path/d:/SimWorld/scripts/humanoid/main.py)

This is the main executable module for the humanoid system.

It is responsible for:
- starting or reconnecting to SimWorld
- setting UnrealCV resolution and connection details
- loading config
- clearing previously spawned humanoid helper actors
- optionally spawning the UE manager
- optionally generating a lightweight world
- spawning the humanoid actor itself
- calibrating walking speed
- running the interactive input loop
- choosing between local parsing and Ollama parsing
- dispatching the final command

Conceptually, this file is the "orchestrator". It does not contain most domain logic itself. Instead, it wires the subsystems together.

#### [scripts/humanoid/common.py](/abs/path/d:/SimWorld/scripts/humanoid/common.py)

This is the shared utility module for the humanoid package.

It contains:
- repo path and startup log handling
- default ports and executable paths
- movement and survey constants
- debug logging helpers
- numeric parsing and clamp helpers
- world-launch helpers
- server readiness checks
- local command parsing
- Ollama HTTP calls
- translation from Ollama JSON into internal command tuples
- shared walk-speed state

This file is important because it defines the "language boundary" between free-form user text and the structured commands the rest of the system executes.

This is also the file where Ollama is used directly.

#### [scripts/humanoid/map/humanoid_map.py](/abs/path/d:/SimWorld/scripts/humanoid/map/humanoid_map.py)

This file handles world inspection and semantic target selection.

It contains:
- asset map loading from `data/description_map.json` and `data/ue_assets.json`
- object/category inference
- world object scanning with `look_around`
- filtering out simulator/internal actors
- query-term normalization and synonym expansion
- object-mask category extraction
- candidate scoring by visibility and screen position
- hybrid candidate collection
- survey result storage and printing
- directional option resolution like "left" or "right"
- candidate ranking through Ollama

In simple terms, this file answers:
- "What is around me?"
- "Which objects matter?"
- "Which one best matches the words the user said?"

This file also uses Ollama, but for ranking and choosing among possible world objects rather than for direct command parsing.

#### [scripts/humanoid/movement/humanoid_movement.py](/abs/path/d:/SimWorld/scripts/humanoid/movement/humanoid_movement.py)

This file contains humanoid movement and navigation behavior.

It handles:
- pose lookup
- walk-speed calibration
- turning decisions
- distance-to-duration conversion
- coordinate navigation loops
- stuck detection and recovery
- final approach behavior
- semantic navigation handoff to surveyed targets

This is the "motion controller" for the humanoid. Once another part of the system decides where to go, this file decides how to rotate, how far to walk, how long to move, and what to do if progress stalls.

#### [scripts/humanoid/vision/humanoid_vision.py](/abs/path/d:/SimWorld/scripts/humanoid/vision/humanoid_vision.py)

This file handles camera-captioning support for the humanoid.

It contains:
- lazy loading of a BLIP vision-caption model
- model unload logic
- current camera capture
- image conversion to PIL
- caption generation
- runtime dependency checks
- runtime status printing

This module does not use Ollama. It uses a local vision-captioning model from the Hugging Face / Transformers stack.

#### [scripts/humanoid/robots/humanoid_commands.py](/abs/path/d:/SimWorld/scripts/humanoid/robots/humanoid_commands.py)

This file is the high-level action dispatcher.

It maps parsed commands to concrete runtime behavior such as:
- walk
- turn
- stop
- where
- view
- caption
- explore
- look
- goto coordinates
- navigate to semantic query
- survey candidates
- show options
- go to option N
- go to directional option

It is best thought of as the "controller surface" of the humanoid system. Other modules figure out meaning, perception, and movement details; this file decides which subsystem to invoke.

#### [scripts/humanoid/world.py](/abs/path/d:/SimWorld/scripts/humanoid/world.py)

This file manages optional world generation and deterministic scene overrides for humanoid sessions.

It supports:
- loading a fixed world JSON
- generating a procedural world through city generation
- exporting that world to JSON
- applying manual tree-scatter overrides
- loading the generated world into Unreal

This module is separate because world-building is logically different from runtime control.

#### Package `__init__.py` Files

- [scripts/humanoid/__init__.py](/abs/path/d:/SimWorld/scripts/humanoid/__init__.py)
- [scripts/humanoid/map/__init__.py](/abs/path/d:/SimWorld/scripts/humanoid/map/__init__.py)
- [scripts/humanoid/movement/__init__.py](/abs/path/d:/SimWorld/scripts/humanoid/movement/__init__.py)
- [scripts/humanoid/robots/__init__.py](/abs/path/d:/SimWorld/scripts/humanoid/robots/__init__.py)
- [scripts/humanoid/vision/__init__.py](/abs/path/d:/SimWorld/scripts/humanoid/vision/__init__.py)

These are package marker files. Their main purpose is to make Python treat the directories as importable packages. They also provide a small descriptive docstring for each subpackage.

## Drone Folder Overview

Folder: [scripts/Drone](/abs/path/d:/SimWorld/scripts/Drone)

This package controls drone actors using Ollama-parsed natural-language commands, plus world setup, drone definitions, movement helpers, and camera-based obstacle checks.

### Architecture

- `Drone_Main.py` is the drone runtime entrypoint.
- `common.py` handles startup and connection helpers.
- `Map/` creates and clears the drone world.
- `Robots/` defines the drone actor classes.
- `Movement/` handles semantic movement such as flying above the nearest tree.
- `Vision/` handles follow-camera positioning and obstacle checks.

### How Drone Works

1. `Drone_Main.py` starts or reconnects to SimWorld.
2. It builds a lightweight world via `DroneMap`.
3. It spawns the blue and red drone actors.
4. It reads user input in a loop.
5. `scripts/Drone/common.py` first handles a few local shortcut commands like `help` and `status`.
6. For normal flight requests, it sends the text to Ollama.
7. The parsed command is executed by the drone runtime.
8. Movement helpers and vision helpers are used when the task needs obstacle-aware navigation, especially around trees.

### Drone File Details

#### [scripts/Drone/Drone_Main.py](/abs/path/d:/SimWorld/scripts/Drone/Drone_Main.py)

This is the main entrypoint for the drone controller.

It is responsible for:
- startup logging
- importing UnrealCV and SimWorld pieces
- optional AirSim connection checks
- Ollama-based command parsing
- world setup through `DroneMap`
- drone spawning
- input loop and command execution
- shutdown and cleanup

This is the equivalent of the humanoid `main.py`, and it now uses Ollama for command parsing too.

#### [scripts/Drone/common.py](/abs/path/d:/SimWorld/scripts/Drone/common.py)

This file contains shared startup utilities and drone command parsing helpers for the package.

It provides:
- repo path setup
- startup logging
- SimWorld executable path lookup
- port-open checks
- auto-launch support
- user-ready wait loop
- server-ready wait loop
- debug logging helpers
- Ollama timeout helpers
- small local shortcut parsing
- Ollama HTTP command parsing for drone actions
- translation from Ollama JSON into internal drone command tuples

This is now the drone package's prompt-parsing boundary, similar in role to `scripts/humanoid/common.py`.

#### [scripts/Drone/Map/Drone_Map.py](/abs/path/d:/SimWorld/scripts/Drone/Map/Drone_Map.py)

This file builds the lightweight drone world.

It handles:
- loading `config/light.yaml`
- generating a city through `CityGenerator`
- exporting JSON world data
- removing existing generated trees
- scattering trees in a deterministic layout
- loading the final world into Unreal
- clearing the world on shutdown

This is the environment-preparation part of the drone stack.

#### [scripts/Drone/Movement/Drone_Movement.py](/abs/path/d:/SimWorld/scripts/Drone/Movement/Drone_Movement.py)

This file contains higher-level drone navigation helpers, especially tree-related behavior after the command has already been parsed.

It provides:
- actor XY position lookup
- tree-target discovery
- tree metadata loading
- nearest-tree search
- chunked movement toward a target
- obstacle-aware rerouting
- safe hover point computation around tree trunks/canopies
- group movement to hover above the nearest tree

This file is the drone equivalent of a tactical movement planner.

It does not use Ollama directly. Its target-selection logic is still based on geometry, object names, metadata, and simple sensor checks.

#### [scripts/Drone/Vision/Drone_Vision.py](/abs/path/d:/SimWorld/scripts/Drone/Vision/Drone_Vision.py)

This file contains drone camera helpers.

It provides:
- chase-camera placement behind the drone
- depth-window statistics
- forward obstacle detection from depth
- object-mask analysis
- rough tree-like obstruction detection from dominant mask colors

This file makes the drones "perception aware" enough to avoid obvious obstacles while moving.

#### [scripts/Drone/Robots/Drone_blue.py](/abs/path/d:/SimWorld/scripts/Drone/Robots/Drone_blue.py)

This file defines the main drone actor class.

It handles:
- actor naming
- spawn behavior
- location updates
- smooth movement interpolation
- relative moves
- up/down motion
- takeoff and landing
- hover
- orbiting around a point

This is the base behavior class for the actual drone object in the scene.

#### [scripts/Drone/Robots/Drone_red.py](/abs/path/d:/SimWorld/scripts/Drone/Robots/Drone_red.py)

This file defines a red variant of the base drone.

It mostly reuses `DroneBlue` behavior and just changes:
- blueprint/model path
- default color

This is basically a specialization rather than a completely separate drone system.

#### Package `__init__.py` Files

- [scripts/Drone/__init__.py](/abs/path/d:/SimWorld/scripts/Drone/__init__.py)
- [scripts/Drone/Map/__init__.py](/abs/path/d:/SimWorld/scripts/Drone/Map/__init__.py)
- [scripts/Drone/Movement/__init__.py](/abs/path/d:/SimWorld/scripts/Drone/Movement/__init__.py)
- [scripts/Drone/Robots/__init__.py](/abs/path/d:/SimWorld/scripts/Drone/Robots/__init__.py)
- [scripts/Drone/Vision/__init__.py](/abs/path/d:/SimWorld/scripts/Drone/Vision/__init__.py)

These package files exist mainly so Python can import the folder hierarchy cleanly.

## Key Difference Between The Two Systems

### Humanoid

- built for conversational control
- uses Ollama for command parsing
- uses Ollama for semantic candidate ranking
- supports richer phrases like "go to the nearest building on the left"
- has a dedicated vision-captioning path for describing the current scene

### Drone

- now also uses Ollama for command parsing
- focuses on flight-style actions like takeoff, orbit, goto, hover, and tree-overflight
- keeps its movement logic deterministic after parsing
- relies on geometry and camera/depth checks for obstacle-aware motion
- uses a follow camera and perception stats rather than captioning

## File Summary Table

| Folder | File | Purpose | Uses Ollama? | Notes |
| --- | --- | --- | --- | --- |
| `humanoid` | `main.py` | Main humanoid runtime loop and subsystem wiring | Indirectly | Starts session, reads input, dispatches commands |
| `humanoid` | `common.py` | Shared constants, startup helpers, local parsing, Ollama parsing | Yes | Core prompt-to-command bridge |
| `humanoid` | `world.py` | Procedural world loading and manual scene overrides | No | Optional world generation path |
| `humanoid` | `__init__.py` | Package marker | No | Import/package helper |
| `humanoid/map` | `humanoid_map.py` | World scan, semantic candidate filtering, ranking, survey state | Yes | Uses Ollama to rank likely target objects |
| `humanoid/map` | `__init__.py` | Package marker | No | Import/package helper |
| `humanoid/movement` | `humanoid_movement.py` | Pose, calibration, goto logic, recovery, semantic navigation execution | No | Motion controller |
| `humanoid/movement` | `__init__.py` | Package marker | No | Import/package helper |
| `humanoid/robots` | `humanoid_commands.py` | Command dispatcher for parsed humanoid actions | No | Connects parsed commands to behavior |
| `humanoid/robots` | `__init__.py` | Package marker | No | Import/package helper |
| `humanoid/vision` | `humanoid_vision.py` | BLIP captioning, dependency checks, runtime status | No | Uses local vision model, not Ollama |
| `humanoid/vision` | `__init__.py` | Package marker | No | Import/package helper |
| `Drone` | `Drone_Main.py` | Main drone runtime loop and command execution | Indirectly | Uses Ollama-parsed commands during the input loop |
| `Drone` | `common.py` | Startup, launch, debug, and Ollama drone parsing helpers | Yes | Core prompt-to-command bridge for drones |
| `Drone` | `__init__.py` | Package marker | No | Import/package helper |
| `Drone/Map` | `Drone_Map.py` | Drone world generation and tree layout | No | Sets up the drone scenario |
| `Drone/Map` | `__init__.py` | Package marker | No | Import/package helper |
| `Drone/Movement` | `Drone_Movement.py` | Tree targeting, chunked flight, obstacle-aware motion | No | Uses geometry and vision checks |
| `Drone/Movement` | `__init__.py` | Package marker | No | Import/package helper |
| `Drone/Robots` | `Drone_blue.py` | Base drone actor class and movement primitives | No | Main drone implementation |
| `Drone/Robots` | `Drone_red.py` | Red drone specialization | No | Thin subclass of blue drone |
| `Drone/Robots` | `__init__.py` | Package marker | No | Import/package helper |
| `Drone/Vision` | `Drone_Vision.py` | Follow camera, depth stats, object-mask obstruction checks | No | Perception support for drone navigation |
| `Drone/Vision` | `__init__.py` | Package marker | No | Import/package helper |
