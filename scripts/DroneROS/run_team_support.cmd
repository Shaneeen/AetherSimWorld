@echo off
setlocal

set PYTHONHOME=
set PYTHONPATH=
set ROS_LOG_DIR=D:\SimWorld\logs\ros
set FASTDDS_BUILTIN_TRANSPORTS=UDPv4
set PATH=D:\pixi_ws\.pixi\envs\default;D:\pixi_ws\.pixi\envs\default\Library\bin;D:\pixi_ws\.pixi\envs\default\Scripts;C:\Windows\System32;C:\Windows;C:\Windows\System32\Wbem;C:\Windows\System32\WindowsPowerShell\v1.0

set SIM_TEAM_CONFIG_FILE=D:\SimWorld\scripts\DroneROS\team_match_config.cmd
if exist "%SIM_TEAM_CONFIG_FILE%" if /I not "%SIM_IGNORE_TEAM_CONFIG%"=="1" call "%SIM_TEAM_CONFIG_FILE%"

if not "%SIM_TEAM_MATCH_CONFIGURED%"=="1" (
    echo [team] No saved team config found. Run scripts\DroneROS\configure_team_match.cmd first.
    exit /b 1
)

if not exist D:\SimWorld\logs\ros mkdir D:\SimWorld\logs\ros
if "%SIM_TACTICAL_CLEARANCE_CM%"=="" set SIM_TACTICAL_CLEARANCE_CM=180
if "%SIM_TARGET_BOUND_X%"=="" set SIM_TARGET_BOUND_X=1350
if "%SIM_TARGET_BOUND_Y%"=="" set SIM_TARGET_BOUND_Y=1350

call D:\pixi_ws\ros2-windows\local_setup.bat
call D:\SimWorld\ros2_ws\install\local_setup.bat

echo [team] Support controllers for red=%SIM_RED_TEAM_SIZE% blue=%SIM_BLUE_TEAM_SIZE%
echo [team] Arena bounds: x=%SIM_TARGET_BOUND_X% y=%SIM_TARGET_BOUND_Y%
echo [team] Tactical blockers: clearance=%SIM_TACTICAL_CLEARANCE_CM% manual=%SIM_TACTICAL_BLOCKERS% collision=%SIM_COLLISION_BLOCKERS% los=%SIM_LOS_BLOCKERS%
echo [team] Starting separate red and blue team coordinators.
echo [team] Starting separate red and blue support controllers.
echo [team] Primary drones still use target/chaser brains; support drones execute team roles.
set PYTHONPATH=D:\SimWorld\ros2_ws\src\simworld_drone_ros;%PYTHONPATH%

echo [team] Cleaning up stale team support processes from previous runs...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'simworld_drone_ros\.team\.(coordinator|drone_controller)' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>nul

if /I not "%SIM_TEAM_RUN_COORDINATORS%"=="0" (
    start "red_team_coordinator" /B cmd /c "set SIM_TEAM=red&& D:\pixi_ws\.pixi\envs\default\python.exe -m simworld_drone_ros.team.coordinator"
    start "blue_team_coordinator" /B cmd /c "set SIM_TEAM=blue&& D:\pixi_ws\.pixi\envs\default\python.exe -m simworld_drone_ros.team.coordinator"
)

start "red_team_support" /B cmd /c "set SIM_TEAM=red&& D:\pixi_ws\.pixi\envs\default\python.exe -m simworld_drone_ros.team.drone_controller"
start "blue_team_support" /B cmd /c "set SIM_TEAM=blue&& D:\pixi_ws\.pixi\envs\default\python.exe -m simworld_drone_ros.team.drone_controller"
