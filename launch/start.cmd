@echo off
setlocal

set WATCH_AFTER_START=1
if /I "%1"=="--no-watch" set WATCH_AFTER_START=0

call "%~dp0env.cmd"
if exist "%SIM_TEAM_CONFIG_FILE%" if /I not "%SIM_IGNORE_TEAM_CONFIG%"=="1" call "%SIM_TEAM_CONFIG_FILE%"

echo [start] Stopping any active chase...
"%PYTHON_EXE%" -u -m simworld_drone_ros.control.start_signal stop_all
timeout /t 1 /nobreak >nul

echo [start] Randomizing fair start positions...
"%PYTHON_EXE%" -u -m simworld_drone_ros.control.start_signal reset_chase
timeout /t 1 /nobreak >nul

if "%SIM_TEAM_MATCH_CONFIGURED%"=="1" if /I not "%SIM_TEAM_SUPPORT_AUTOSTART%"=="0" (
    echo [start] Starting team support for red=%SIM_RED_TEAM_SIZE% blue=%SIM_BLUE_TEAM_SIZE%...
    call "%~dp0team_support.cmd"
    timeout /t 3 /nobreak >nul
)

echo [start] Starting chase...
"%PYTHON_EXE%" -u -m simworld_drone_ros.control.start_signal start_all

if "%WATCH_AFTER_START%"=="1" (
    echo.
    echo [watch] Compact chase feed. Press Ctrl+C to stop watching.
    "%PYTHON_EXE%" -u -m simworld_drone_ros.watch.chase_watch
)
