@echo off

set PYTHONHOME=
set PYTHONPATH=
if "%OLLAMA_MODEL%"=="" set OLLAMA_MODEL=gpt-oss:latest
if "%OLLAMA_API_URL%"=="" set OLLAMA_API_URL=http://10.8.0.132:11434/api/generate
if "%OLLAMA_API_URLS%"=="" set OLLAMA_API_URLS=%OLLAMA_API_URL%

set SIM_TEAM_CONFIG_FILE=D:\SimWorld\scripts\DroneROS\team_match_config.cmd
set SIM_TEAM_ENV_FILE=%TEMP%\simworld_team_match_%RANDOM%.cmd
powershell -NoProfile -ExecutionPolicy Bypass -File D:\SimWorld\scripts\DroneROS\configure_team_match.ps1 -OutputCmd "%SIM_TEAM_ENV_FILE%"
if not exist "%SIM_TEAM_ENV_FILE%" (
    echo [team] No team config was written.
    exit /b 1
)
if exist "%SIM_TEAM_ENV_FILE%" copy /Y "%SIM_TEAM_ENV_FILE%" "%SIM_TEAM_CONFIG_FILE%" >nul
if exist "%SIM_TEAM_ENV_FILE%" call "%SIM_TEAM_ENV_FILE%"
if exist "%SIM_TEAM_ENV_FILE%" del "%SIM_TEAM_ENV_FILE%"

echo [team] Red drones: %SIM_RED_TEAM_SIZE%
echo [team] Blue drones: %SIM_BLUE_TEAM_SIZE%
echo [team] Round mode: %SIM_TEAM_ROUND_MODE%
echo [team] Red model: %SIM_RED_MODEL_REFERENCE%
echo [team] Red speeds: cruise=%SIM_RED_CRUISE_SPEED% evade=%SIM_RED_EVADE_SPEED% burst=%SIM_RED_BURST_SPEED%
echo [team] Blue model: %SIM_BLUE_MODEL_REFERENCE%
echo [team] Blue speeds: base=%SIM_BLUE_BASE_SPEED% intercept=%SIM_BLUE_INTERCEPT_SPEED% search=%SIM_BLUE_SEARCH_SPEED%
echo [team] Saved config: %SIM_TEAM_CONFIG_FILE%
echo [team] Team config will be reused by target/chaser launchers.
echo [team] Note: run_bridge_existing.cmd expects manual actors named DroneA, DroneA1..., DroneB, DroneB1...
