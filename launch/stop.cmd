@echo off
setlocal

call "%~dp0env.cmd"

echo [stop] Publishing STOP...
"%PYTHON_EXE%" -u -m simworld_drone_ros.control.start_signal stop_all

echo [stop] Cleaning known SimWorld ROS Python processes...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'simworld_drone_ros\.(bridge\.ue_bridge|duel\.target_brain|duel\.chaser_brain|team\.(coordinator|drone_controller)|vision\.visual_observer|watch\.chase_watch)' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>nul

echo [stop] Cleaning stale team launcher windows...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match '(scripts\\DroneROS\\run_team_node\.cmd|launch\\team_node\.cmd)' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>nul

echo [stop] Done.
