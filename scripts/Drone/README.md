# Drone Controller

## Run

From `D:\SimWorld`:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Drone\run_drone_main.ps1
```

That launcher will:

- start `ollama serve` if Ollama is not already running
- start `SimWorld.exe` if SimWorld is not already running
- open the empty map
- wait for you to confirm the world is loaded
- connect to UnrealCV
- build the light world from `config/light.yaml`
- start the drone controller

## If SimWorld Is Already Open

Run the same command:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Drone\run_drone_main.ps1
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
fly to the nearest tree
go above nearest tree
takeoff
land
up 200
down 200
hover 2
orbit 700
goto 100 200 900
move 100 0 0
status
quit
```

## Files

- main entry: `scripts/Drone/Drone_Main.py`
- launcher: `scripts/Drone/run_drone_main.ps1`
- world setup: `scripts/Drone/Map/Drone_Map.py`
- movement: `scripts/Drone/Movement/Drone_Movement.py`
- vision: `scripts/Drone/Vision/Drone_Vision.py`
- robots: `scripts/Drone/Robots/`
