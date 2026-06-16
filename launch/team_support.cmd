@echo off
setlocal

call "%~dp0env.cmd"
if exist "%SIM_TEAM_CONFIG_FILE%" if /I not "%SIM_IGNORE_TEAM_CONFIG%"=="1" call "%SIM_TEAM_CONFIG_FILE%"

if not "%SIM_TEAM_MATCH_CONFIGURED%"=="1" (
    echo [team] No team config found. Run launch\set_teams_5v5.cmd first.
    exit /b 1
)

if "%SIM_TEAM_START_ACTIVE%"=="" set "SIM_TEAM_START_ACTIVE=1"
if "%SIM_TACTICAL_CLEARANCE_CM%"=="" set "SIM_TACTICAL_CLEARANCE_CM=180"
if "%SIM_TARGET_BOUND_X%"=="" set "SIM_TARGET_BOUND_X=1350"
if "%SIM_TARGET_BOUND_Y%"=="" set "SIM_TARGET_BOUND_Y=1350"

if not exist "%ROS_LOG_DIR%" mkdir "%ROS_LOG_DIR%"

echo [team] Cleaning existing team support nodes...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'simworld_drone_ros\.team\.(coordinator|drone_controller)' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>nul

echo [team] Support controllers for red=%SIM_RED_TEAM_SIZE% blue=%SIM_BLUE_TEAM_SIZE%
echo [team] Logs: %ROS_LOG_DIR%\team_*.log

if /I "%SIM_VISION_AUTOSTART%"=="1" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'simworld_drone_ros\.vision\.visual_observer' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>nul
    start "visual_observer_blue_1" /min "%ComSpec%" /c call "%~dp0vision.cmd" blue_1 ^> "%ROS_LOG_DIR%\vision_blue_1.log" 2^>^&1
    start "visual_observer_red_1" /min "%ComSpec%" /c call "%~dp0vision.cmd" red_1 ^> "%ROS_LOG_DIR%\vision_red_1.log" 2^>^&1
)

start "red_team_coordinator" /min "%ComSpec%" /c call "%~dp0team_node.cmd" red coordinator ^> "%ROS_LOG_DIR%\team_red_coordinator.log" 2^>^&1
start "blue_team_coordinator" /min "%ComSpec%" /c call "%~dp0team_node.cmd" blue coordinator ^> "%ROS_LOG_DIR%\team_blue_coordinator.log" 2^>^&1
start "red_team_support" /min "%ComSpec%" /c call "%~dp0team_node.cmd" red support ^> "%ROS_LOG_DIR%\team_red_support.log" 2^>^&1
start "blue_team_support" /min "%ComSpec%" /c call "%~dp0team_node.cmd" blue support ^> "%ROS_LOG_DIR%\team_blue_support.log" 2^>^&1
