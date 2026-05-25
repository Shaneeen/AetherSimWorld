@echo off
setlocal

set PYTHONHOME=
set PYTHONPATH=
set ROS_LOG_DIR=D:\SimWorld\logs\ros
set FASTDDS_BUILTIN_TRANSPORTS=UDPv4
set PATH=D:\pixi_ws\.pixi\envs\default;D:\pixi_ws\.pixi\envs\default\Library\bin;D:\pixi_ws\.pixi\envs\default\Scripts;C:\Windows\System32;C:\Windows;C:\Windows\System32\Wbem;C:\Windows\System32\WindowsPowerShell\v1.0

if not exist D:\SimWorld\logs\ros mkdir D:\SimWorld\logs\ros

call D:\pixi_ws\ros2-windows\local_setup.bat
call D:\SimWorld\ros2_ws\install\local_setup.bat
set PYTHONPATH=D:\SimWorld\ros2_ws\src\simworld_drone_ros;%PYTHONPATH%

echo [stop] Publishing non-blocking STOP to any live chase nodes...
D:\pixi_ws\.pixi\envs\default\python.exe -m simworld_drone_ros.control.start_signal stop_all

echo [stop] Cleaning up live chase Python processes...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'simworld_drone_ros\.(bridge\.ue_bridge|duel\.target_brain|duel\.chaser_brain|team\.(coordinator|drone_controller))' -or $_.CommandLine -match 'ros2-script\.py run simworld_drone_ros (ue_bridge|target_brain|chaser_brain)' -or $_.CommandLine -match 'install\\Lib\\simworld_drone_ros\\(target_brain|chaser_brain|ue_bridge)-script\.py' -or $_.CommandLine -match 'install\\lib\\simworld_drone_ros\\(target_brain|chaser_brain|ue_bridge)\.exe' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>nul

echo [stop] Done. Restart bridge, target brain, and chaser brain before start_chase.
