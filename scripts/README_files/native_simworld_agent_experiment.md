# Native SimWorld Agent Experiment

## Why This Exists

Your current `scripts/humanoid` and `scripts/Drone` controllers work, but they mostly treat SimWorld as a backend.

This experiment is a separate path that tries to reuse more of what SimWorld already provides:
- `simworld.agent.Humanoid`
- `simworld.map.Map`
- `simworld.local_planner.LocalPlanner`
- `simworld.local_planner.action_space`
- `simworld.local_planner.prompt`
- `simworld.llm.BaseLLM`

## What I Added

- [scripts/NativeAgents/ollama_a2a.py](/abs/path/d:/SimWorld/scripts/NativeAgents/ollama_a2a.py)
  An Ollama/OpenAI-compatible adapter that fits the `generate_instructions(...)` style expected by SimWorld planner code.

- [scripts/NativeAgents/native_local_planner.py](/abs/path/d:/SimWorld/scripts/NativeAgents/native_local_planner.py)
  A small subclass of SimWorld's `LocalPlanner` that keeps the humanoid pose synced from the simulator while reusing the planner logic.

- [scripts/NativeAgents/native_semantics.py](/abs/path/d:/SimWorld/scripts/NativeAgents/native_semantics.py)
  A semantic helper layer that scans nearby world objects, infers rough categories such as building/store/tree, and resolves nearest or visible matches.

- [scripts/NativeAgents/native_command_interpreter.py](/abs/path/d:/SimWorld/scripts/NativeAgents/native_command_interpreter.py)
  A small interpreter that routes user input into either semantic-goal resolution or native planner execution.

- [scripts/NativeAgents/native_humanoid_runner.py](/abs/path/d:/SimWorld/scripts/NativeAgents/native_humanoid_runner.py)
  A standalone experimental runner that wires together native SimWorld objects for testing.

## What This Reuses

This experiment reuses the native SimWorld stack more directly than your current script controllers.

It uses:
- native agent model
- native map graph
- native high-level action schema
- native planner prompts
- native planner execution flow
- a small native semantic-target layer for nearest/visible object tests

## What It Does Not Replace

It does not replace:
- [scripts/humanoid/main.py](/abs/path/d:/SimWorld/scripts/humanoid/main.py)
- [scripts/Drone/Drone_Main.py](/abs/path/d:/SimWorld/scripts/Drone/Drone_Main.py)

Those remain your main working script-layer controllers.

This is only a testbed to see whether a more SimWorld-native architecture is a better fit for JJ's expectations.

## How To Run

Example:

```powershell
python scripts/NativeAgents/native_humanoid_runner.py
```

Recommended environment:

```powershell
$env:OLLAMA_MODEL="phi3"
$env:OLLAMA_OPENAI_URL="http://localhost:11434/v1"
$env:SIMWORLD_GENERATE_WORLD="1"
python scripts/NativeAgents/native_humanoid_runner.py
```

## Example Commands

You can now test:

```text
go to the nearest building
go to the nearest store
go to the nearest tree
go to the visible store
look
status
go to [0, 0]
```

## Current Limitation

This native experiment is strongest for:
- plan parsing
- map-based navigation to graph points
- nearest/visible semantic object resolution for a few useful categories

It is weaker than your custom `scripts/humanoid` path for:
- semantic object targeting
- look-around ranking
- hybrid visible candidate logic
- richer custom behaviors
- obstacle avoidance from robust depth reasoning

So the native path is useful for testing reuse, but it is not yet a full replacement for the more advanced custom prompt-agent scripts.
