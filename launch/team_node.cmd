@echo off
setlocal

set "SIM_TEAM=%~1"
set "SIM_TEAM_NODE=%~2"

set "USE_OLLAMA=1"
if "%OLLAMA_MODEL%"=="" set "OLLAMA_MODEL=gpt-oss:latest"
if "%SIM_TEAM_OLLAMA_MODEL%"=="" set "SIM_TEAM_OLLAMA_MODEL=%OLLAMA_MODEL%"
if "%OLLAMA_API_URL%"=="" set "OLLAMA_API_URL=http://10.8.0.132:11434/api/generate"
if "%OLLAMA_API_URLS%"=="" set "OLLAMA_API_URLS=%OLLAMA_API_URL%"
if "%SIM_TEAM_OLLAMA_API_URL%"=="" set "SIM_TEAM_OLLAMA_API_URL=%OLLAMA_API_URL%"
if "%OLLAMA_TIMEOUT_SEC%"=="" set "OLLAMA_TIMEOUT_SEC=60"

call "%~dp0env.cmd"
if exist "%SIM_TEAM_CONFIG_FILE%" call "%SIM_TEAM_CONFIG_FILE%"

if "%SIM_TEAM_START_ACTIVE%"=="" set "SIM_TEAM_START_ACTIVE=1"
if "%SIM_TEAM%"=="" set "SIM_TEAM=blue"
if "%SIM_TEAM_PREP_OLLAMA%"=="" set "SIM_TEAM_PREP_OLLAMA=1"
if "%SIM_TEAM_OLLAMA_NUM_PREDICT%"=="" set "SIM_TEAM_OLLAMA_NUM_PREDICT=256"
if "%SIM_TEAM_OLLAMA_COOLDOWN_SEC%"=="" set "SIM_TEAM_OLLAMA_COOLDOWN_SEC=12"
if "%SIM_TEAM_OLLAMA_FAILURE_BACKOFF_SEC%"=="" set "SIM_TEAM_OLLAMA_FAILURE_BACKOFF_SEC=18"
if "%SIM_TEAM_OLLAMA_MAX_BACKOFF_SEC%"=="" set "SIM_TEAM_OLLAMA_MAX_BACKOFF_SEC=90"
if "%SIM_TEAM_OLLAMA_PLAN_CACHE_SEC%"=="" set "SIM_TEAM_OLLAMA_PLAN_CACHE_SEC=24"
if "%SIM_TEAM_OLLAMA_USE_CHAT%"=="" set "SIM_TEAM_OLLAMA_USE_CHAT=1"

if /I "%SIM_TEAM_NODE%"=="coordinator" (
    echo [team] %SIM_TEAM% coordinator
    if /I not "%SIM_TEAM_PREP_OLLAMA%"=="0" if /I not "%SIM_TEAM_PREP_OLLAMA%"=="false" (
        set "SIM_OLLAMA_PREP_MODEL=%SIM_TEAM_OLLAMA_MODEL%"
        "%PYTHON_EXE%" -u -m simworld_drone_ros.vision.prepare_ollama
    )
    "%PYTHON_EXE%" -u -m simworld_drone_ros.team.coordinator
) else (
    echo [team] %SIM_TEAM% support controller
    "%PYTHON_EXE%" -u -m simworld_drone_ros.team.drone_controller
)
