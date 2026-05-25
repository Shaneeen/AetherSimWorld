@echo off
setlocal

set WATCH_AFTER_START=1
if /I "%1"=="--no-watch" set WATCH_AFTER_START=0

set PYTHONHOME=
set PYTHONPATH=
set ROS_LOG_DIR=D:\SimWorld\logs\ros
set FASTDDS_BUILTIN_TRANSPORTS=UDPv4
set PATH=D:\pixi_ws\.pixi\envs\default;D:\pixi_ws\.pixi\envs\default\Library\bin;D:\pixi_ws\.pixi\envs\default\Scripts;C:\Windows\System32;C:\Windows;C:\Windows\System32\Wbem;C:\Windows\System32\WindowsPowerShell\v1.0
set SIM_TEAM_CONFIG_FILE=D:\SimWorld\scripts\DroneROS\team_match_config.cmd
if exist "%SIM_TEAM_CONFIG_FILE%" if /I not "%SIM_IGNORE_TEAM_CONFIG%"=="1" call "%SIM_TEAM_CONFIG_FILE%"

if not exist D:\SimWorld\logs\ros mkdir D:\SimWorld\logs\ros

call D:\pixi_ws\ros2-windows\local_setup.bat
call D:\SimWorld\ros2_ws\install\local_setup.bat
set PYTHONPATH=D:\SimWorld\ros2_ws\src\simworld_drone_ros;%PYTHONPATH%

set SIM_NODE_LIST=%TEMP%\simworld_nodes_%RANDOM%.txt

echo [start] ROS graph diagnostic, non-blocking:
ros2 node list > "%SIM_NODE_LIST%" 2>nul
findstr /R /C:"/ue_bridge$" "%SIM_NODE_LIST%" >nul
if errorlevel 1 echo [start]   note: /ue_bridge not visible from this shell; continuing anyway.
findstr /R /C:"/target_brain$" "%SIM_NODE_LIST%" >nul
if errorlevel 1 echo [start]   note: /target_brain not visible from this shell; make sure Terminal 2 is running.
findstr /R /C:"/chaser_brain$" "%SIM_NODE_LIST%" >nul
if errorlevel 1 echo [start]   note: /chaser_brain not visible from this shell; make sure Terminal 3 is running.
del "%SIM_NODE_LIST%" >nul 2>nul

echo [start] Stopping any active chase...
D:\pixi_ws\.pixi\envs\default\python.exe -m simworld_drone_ros.control.start_signal stop_all
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 1" >nul

echo [start] Randomizing fair start positions...
D:\pixi_ws\.pixi\envs\default\python.exe -m simworld_drone_ros.control.start_signal reset_chase
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 1" >nul

if "%SIM_TEAM_MATCH_CONFIGURED%"=="1" if /I not "%SIM_TEAM_SUPPORT_AUTOSTART%"=="0" (
    echo [start] Ensuring team support controllers are running for red=%SIM_RED_TEAM_SIZE% blue=%SIM_BLUE_TEAM_SIZE%...
    start "simworld_team_support" /B cmd /c "cd /d D:\SimWorld && set SIM_TEAM_START_ACTIVE=1&& scripts\DroneROS\run_team_support.cmd > D:\SimWorld\logs\ros\team_support_autostart.log 2>&1"
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 3" >nul
)

echo [start] Starting chase...
D:\pixi_ws\.pixi\envs\default\python.exe -m simworld_drone_ros.control.start_signal start_all

if "%WATCH_AFTER_START%"=="1" (
    echo.
    echo [watch] Compact chase feed. Press Ctrl+C to stop watching.
    D:\pixi_ws\.pixi\envs\default\python.exe -m simworld_drone_ros.watch.chase_watch
    if errorlevel 1 echo [watch] ERROR: chase watcher exited. Try scripts\DroneROS\watch_chase.cmd in a new terminal.
)
