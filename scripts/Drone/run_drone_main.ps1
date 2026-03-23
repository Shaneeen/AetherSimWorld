$env:SIMWORLD_EXE = "D:\Windows\Windows\SimWorld.exe"
$env:SIMWORLD_MAP_PATH = "/Game/Maps/empty.umap"
$env:SIMWORLD_AUTO_LAUNCH = "1"
$env:SIMWORLD_CONFIG = "config/light.yaml"
$env:SIMWORLD_GENERATE_WORLD = "1"

$preferredPython = "C:\Users\popla\miniconda3\envs\simworld\python.exe"
$pythonExe = if (Test-Path $preferredPython) {
    $preferredPython
} elseif ($env:CONDA_PREFIX) {
    Join-Path $env:CONDA_PREFIX "python.exe"
} else {
    "python"
}

& $pythonExe .\scripts\Drone\Drone_Main.py
