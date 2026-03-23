$env:SIMWORLD_EXE = "D:\Windows\Windows\SimWorld.exe"
$env:SIMWORLD_MAP_PATH = "/Game/Maps/empty.umap"
$env:SIMWORLD_AUTO_LAUNCH = "1"
$env:SIMWORLD_CONFIG = "config/light.yaml"
$env:SIMWORLD_GENERATE_WORLD = "1"

python scripts/prompt_agent.py

