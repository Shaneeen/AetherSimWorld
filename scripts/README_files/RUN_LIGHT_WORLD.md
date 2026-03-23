# Run SimWorld Light World

## How To Start

```powershell
. "C:\Users\popla\miniconda3\shell\condabin\conda-hook.ps1"
conda activate simworld
cd D:\SimWorld
powershell -ExecutionPolicy Bypass -File .\scripts\run_prompt_agent_light.ps1
```

If SimWorld is already open, run only:

```powershell
cd D:\SimWorld
powershell -ExecutionPolicy Bypass -File .\scripts\run_prompt_agent_light.ps1
```

When asked:

```text
Loaded? [Enter/1]:
```

press `Enter` or type `1`, then press `Enter`.

## How To Quit, Exit And Change

To stop the prompt agent but keep the `.exe` open:

```text
quit
```

What happens:

- the Python script exits
- the generated world is cleared back to empty
- `SimWorld.exe` stays open
- you return to PowerShell

Then you can:

- edit `scripts/prompt_agent.py`
- edit another script
- rerun the launcher without restarting the `.exe`

Rerun with:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_prompt_agent_light.ps1
```

If the script is stuck and you want to interrupt it:

```powershell
Ctrl+C
```

That should also trigger cleanup before disconnecting.

## How To Setup

Open PowerShell, then run:

```powershell
. "C:\Users\popla\miniconda3\shell\condabin\conda-hook.ps1"
conda activate simworld
cd D:\SimWorld
```

Install dependencies:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_simworld_deps.ps1
```

If PowerShell blocks scripts, use:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

Then rerun the install or launcher command.

Notes:

- launcher script: `scripts/run_prompt_agent_light.ps1`
- dependency installer: `scripts/install_simworld_deps.ps1`
- config file: `config/light.yaml`
- startup log: `logs/prompt_agent_startup.log`
