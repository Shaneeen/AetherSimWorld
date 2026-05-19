@echo off
setlocal

set WATCH_AFTER_START=1
if /I "%1"=="--no-watch" set WATCH_AFTER_START=0

set PYTHONHOME=
set PYTHONPATH=
set ROS_LOG_DIR=D:\SimWorld\logs\ros
set FASTDDS_BUILTIN_TRANSPORTS=UDPv4
set PATH=D:\pixi_ws\.pixi\envs\default;D:\pixi_ws\.pixi\envs\default\Library\bin;D:\pixi_ws\.pixi\envs\default\Scripts;C:\Windows\System32;C:\Windows;C:\Windows\System32\Wbem;C:\Windows\System32\WindowsPowerShell\v1.0

if not exist D:\SimWorld\logs\ros mkdir D:\SimWorld\logs\ros

call D:\pixi_ws\ros2-windows\local_setup.bat
call D:\SimWorld\ros2_ws\install\local_setup.bat

ros2 topic list | findstr /C:"/sim/reset_chase" >nul
if errorlevel 1 (
    echo [start] ERROR: /sim/reset_chase is not available.
    echo [start] Restart the UE bridge window so it loads the new reset code, then run start_chase again.
    exit /b 1
)

echo [start] Stopping any active chase...
D:\pixi_ws\.pixi\envs\default\python.exe D:\pixi_ws\ros2-windows\Scripts\ros2-script.py run simworld_drone_ros start_signal stop_all
timeout /t 1 /nobreak >nul

echo [start] Randomizing fair start positions...
ros2 topic pub --once /sim/reset_chase std_msgs/msg/String "{data: reset_chase}"
timeout /t 1 /nobreak >nul
ros2 topic pub --once /sim/reset_chase std_msgs/msg/String "{data: reset_chase}"
timeout /t 1 /nobreak >nul

echo [start] Starting chase...
D:\pixi_ws\.pixi\envs\default\python.exe D:\pixi_ws\ros2-windows\Scripts\ros2-script.py run simworld_drone_ros start_signal start_all

if "%WATCH_AFTER_START%"=="1" (
    echo.
    echo [watch] Compact chase feed. Press Ctrl+C to stop watching.
    D:\pixi_ws\.pixi\envs\default\python.exe -u -m simworld_drone_ros.chase_watch
)
