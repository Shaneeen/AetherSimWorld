# Ultra Humanoid

Ultra Humanoid is the merged humanoid agent for this repo.

It combines:
- SimWorld native agent and map classes
- Ollama-based prompt parsing
- custom semantic world reasoning
- direct target navigation
- depth-guided stopping near objects

## Main File

- [main.py](/abs/path/d:/SimWorld/scripts/UltraHumanoid/main.py)

## What It Can Do

- understand prompt-like movement commands
- go to semantic targets such as nearby buildings, stores, and trees
- go to coordinates
- inspect nearby objects with `look`
- report position and yaw with `status`
- approach targets directly instead of only stopping at a map node
- use depth near the end so it stops close to a building or marker surface

## What It Cannot Do Yet

- full obstacle avoidance in complex clutter
- pure RGB-only semantic perception
- long multi-step mission planning
- guaranteed perfect target resolution for every ambiguous prompt

## Run

```powershell
$env:OLLAMA_MODEL="phi3"
$env:SIMWORLD_COMPARISON_WORLD="1"
python scripts\UltraHumanoid\main.py
```

## Useful Commands

- `go to the nearest building`
- `go to the nearest store`
- `go to the visible store`
- `go to the nearest tree`
- `go to 1200 400`
- `look`
- `status`
- `help`
- `quit`

## Main Modules

- [common.py](/abs/path/d:/SimWorld/scripts/UltraHumanoid/common.py)
- [Map/world_model.py](/abs/path/d:/SimWorld/scripts/UltraHumanoid/Map/world_model.py)
- [Vision/perception.py](/abs/path/d:/SimWorld/scripts/UltraHumanoid/Vision/perception.py)
- [Movement/navigation.py](/abs/path/d:/SimWorld/scripts/UltraHumanoid/Movement/navigation.py)
- [Robots/controller.py](/abs/path/d:/SimWorld/scripts/UltraHumanoid/Robots/controller.py)

## Notes

This is the best humanoid path to keep improving if you want one combined agent that is closer to what JJ wants for the project.

The fuller guide is here:
- [ultra_humanoid.md](/abs/path/d:/SimWorld/scripts/README_files/ultra_humanoid.md)
