# Humanoid Comparison Runner

## Purpose

This runner compares:
- your custom humanoid controller
- the NativeAgents humanoid controller

in the same SimWorld world, using the same prompts and the same start position.

By default it now uses a deterministic comparison world with:
- multiple named buildings
- a visible store-like building near spawn
- trees and a trash bin

This avoids the earlier problem where `config/light.yaml` generated a scene with trees but almost no useful buildings for semantic tests.

## File

- [scripts/NativeAgents/compare_humanoid_agents.py](/abs/path/d:/SimWorld/scripts/NativeAgents/compare_humanoid_agents.py)

## What It Tests

Right now it is focused on semantic navigation prompts such as:
- `go to the nearest building`
- `go to the nearest store`
- `go to the nearest tree`

For each prompt, it runs:
1. custom humanoid
2. native humanoid

and records:
- selected target
- elapsed time
- final position
- remaining distance to target
- your manual accuracy judgment

## How To Run

```powershell
$env:OLLAMA_MODEL="phi3"
$env:OLLAMA_OPENAI_URL="http://localhost:11434/v1"
$env:SIMWORLD_COMPARISON_WORLD="1"
python scripts\NativeAgents\compare_humanoid_agents.py
```

## Optional Prompt Override

You can override the prompt set with:

```powershell
$env:COMPARE_PROMPTS="go to the nearest building|go to the nearest store|go to the visible store"
python scripts\NativeAgents\compare_humanoid_agents.py
```

## Output

Results are saved to:

```text
logs/humanoid_comparison_<timestamp>.json
```

## Manual Accuracy Input

After each controller finishes each prompt, the runner will ask you for:

```text
Accuracy [correct/partial/wrong]:
Notes:
```

Those values are saved into the JSON log under:

```text
manual_accuracy.label
manual_accuracy.notes
manual_accuracy.timestamp
```

## Notes

- The custom humanoid uses your richer custom semantic navigation path.
- The native humanoid uses the NativeAgents semantic helper plus the SimWorld-native planner path.
- This comparison is useful for testing behavior before deciding which architecture to invest in further.
- If you really want to fall back to the old procedural world instead, set `SIMWORLD_COMPARISON_WORLD=0` and `SIMWORLD_GENERATE_WORLD=1`.
