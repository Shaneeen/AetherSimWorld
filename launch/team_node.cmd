@echo off
setlocal

set "SIM_TEAM=%~1"
set "SIM_TEAM_NODE=%~2"

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
