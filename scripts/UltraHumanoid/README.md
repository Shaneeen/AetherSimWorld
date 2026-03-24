# Ultra Humanoid

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
- build the light world from `config/light.yaml`
- start the ultra humanoid controller

## If SimWorld Is Already Open

Run the same command:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\UltraHumanoid\run_ultrahumanoid.ps1
```

It will reuse the existing `SimWorld.exe` window.

## Important Prompt

When you see:

```text
Loaded? [Enter/1]:
```

press `Enter` or type `1`, then press `Enter`.

## Commands

Examples:

```text
go to the nearest building
go to the nearest store
go to the visible store
go to the nearest tree
go to 1200 400
look
status
help
quit
```

## Files

- main entry: `scripts/UltraHumanoid/main.py`
- launcher: `scripts/UltraHumanoid/run_ultrahumanoid.ps1`
- common helpers: `scripts/UltraHumanoid/common.py`
- world model: `scripts/UltraHumanoid/Map/world_model.py`
- movement: `scripts/UltraHumanoid/Movement/navigation.py`
- vision: `scripts/UltraHumanoid/Vision/perception.py`
- controller: `scripts/UltraHumanoid/Robots/controller.py`
