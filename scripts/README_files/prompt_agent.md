prompt_agent.py
=================

What it does
------------
- Launches `SimWorld.exe` for you if auto-launch is enabled.
- Opens the empty Unreal map first: `/Game/Maps/empty.umap`.
- Waits for you to confirm the UE window is fully loaded before connecting.
- Connects to UnrealCV on `127.0.0.1:9000`.
- Loads `config/light.yaml`.
- Builds a lightweight world:
  - procedural roads
  - no generated buildings
  - no traffic
  - manually scattered trees added after road generation
- Spawns a `Humanoid` agent and starts the text-command loop.

Current startup flow
--------------------
When you run:

```powershell
python scripts\prompt_agent.py
```

or:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_prompt_agent_light.ps1
```

the script now does this:

1. logs startup details to `logs/prompt_agent_startup.log`
2. launches `D:\Windows\Windows\SimWorld.exe` if it is not already running
3. if SimWorld is already running, it reuses the same `.exe`
4. asks:

```text
Loaded? [Enter/1]:
```

5. waits for UnrealCV on port `9000`
6. connects to the running SimWorld window
7. clears previously generated prompt-agent actors
8. generates and loads the light world
9. spawns the humanoid

If the `.exe` is already open, rerunning the launcher will not restart it. It will just ask for confirmation again, reconnect, and rebuild the world.

Light-world behavior
--------------------
The light-world setup comes from:

- `config/light.yaml`
- `scripts/prompt_agent.py`

Current behavior:

- roads are generated procedurally
- buildings are disabled with `citygen.building.spawn_probability: 0.0`
- clutter generation is disabled
- trees are added manually after export so they are easier to control

The manual tree settings live in `config/light.yaml`:

```yaml
manual_scene:
  clear_on_exit: true
  scattered_trees:
    enabled: true
    count: 10
    min_radius_cm: 500
    max_radius_cm: 1500
```

What that means:

- `count`: how many trees to spawn
- `min_radius_cm`: nearest tree distance from the origin
- `max_radius_cm`: farthest tree distance from the origin

Example:

```yaml
min_radius_cm: 1000
max_radius_cm: 2000
```

means trees spawn between `1000 cm` and `2000 cm` away from the origin at random angles.

How to run
----------
Recommended:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_prompt_agent_light.ps1
```

Manual version:

```powershell
$env:SIMWORLD_EXE = "D:\Windows\Windows\SimWorld.exe"
$env:SIMWORLD_MAP_PATH = "/Game/Maps/empty.umap"
$env:SIMWORLD_AUTO_LAUNCH = "1"
$env:SIMWORLD_CONFIG = "config/light.yaml"
$env:SIMWORLD_GENERATE_WORLD = "1"
python scripts\prompt_agent.py
```

Quit / rerun behavior
---------------------
Typing:

```text
quit
```

will:

- exit the prompt-agent loop
- clear the generated world back to empty
- disconnect UnrealCV
- keep `SimWorld.exe` open

This is useful when you want to:

- edit `prompt_agent.py`
- edit another script
- rerun the launcher without restarting the `.exe`

After quitting, you can rerun:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_prompt_agent_light.ps1
```

and it will reuse the existing Unreal window.

Logging
-------
Startup logs are written to:

```text
logs/prompt_agent_startup.log
```

This helps diagnose missing imports, startup failures, and connection problems.

Notes
-----
- `Ctrl+C` is the most reliable way to interrupt from PowerShell.
- `Ctrl+Q` is not currently handled as a reliable Python-side hotkey in this setup.
- The cursor-lock behavior comes from the packaged Unreal application; that cannot be cleanly changed from this Python repo alone.

File location
-------------
See `scripts/prompt_agent.py` for the implementation and `config/light.yaml` for the current world settings.
