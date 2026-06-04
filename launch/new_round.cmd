@echo off
setlocal

call "%~dp0env.cmd"
if exist "%SIM_TEAM_CONFIG_FILE%" if /I not "%SIM_IGNORE_TEAM_CONFIG%"=="1" call "%SIM_TEAM_CONFIG_FILE%"

echo [round] Starting a new round without closing bridge/brains...
echo [round] Make sure bridge.cmd is still running in its own terminal.

echo [round] Stopping current motion...
"%PYTHON_EXE%" -u -m simworld_drone_ros.control.start_signal stop_all
timeout /t 1 /nobreak >nul

echo [round] Resetting tagged drones and randomizing positions...
"%PYTHON_EXE%" -u -m simworld_drone_ros.control.start_signal reset_chase
timeout /t 1 /nobreak >nul

echo [round] Starting chase...
"%PYTHON_EXE%" -u -m simworld_drone_ros.control.start_signal start_all

echo [round] Done.
