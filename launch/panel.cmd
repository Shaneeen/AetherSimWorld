@echo off
setlocal

call "%~dp0env.cmd"
if exist "%SIM_TEAM_CONFIG_FILE%" if /I not "%SIM_IGNORE_TEAM_CONFIG%"=="1" call "%SIM_TEAM_CONFIG_FILE%"

echo [panel] SimWorld drone team panel
echo [panel] Top row is chaser/blue, bottom row is target/red.
"%PYTHON_EXE%" -u -m simworld_drone_ros.panel.team_panel
