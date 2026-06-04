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
if "%OLLAMA_TIMEOUT_SEC%"=="" set "OLLAMA_TIMEOUT_SEC=20"

call "%~dp0env.cmd"
if exist "%SIM_TEAM_CONFIG_FILE%" call "%SIM_TEAM_CONFIG_FILE%"

if "%SIM_TEAM_START_ACTIVE%"=="" set "SIM_TEAM_START_ACTIVE=1"
if "%SIM_TEAM%"=="" set "SIM_TEAM=blue"

if /I "%SIM_TEAM_NODE%"=="coordinator" (
    echo [team] %SIM_TEAM% coordinator
    "%PYTHON_EXE%" -u -m simworld_drone_ros.team.coordinator
) else (
    echo [team] %SIM_TEAM% support controller
    "%PYTHON_EXE%" -u -m simworld_drone_ros.team.drone_controller
)
