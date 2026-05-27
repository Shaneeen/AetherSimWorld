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

echo [team] Support controllers for red=%SIM_RED_TEAM_SIZE% blue=%SIM_BLUE_TEAM_SIZE%
start "red_team_coordinator" /b "%ComSpec%" /c call "%~dp0team_node.cmd" red coordinator
start "blue_team_coordinator" /b "%ComSpec%" /c call "%~dp0team_node.cmd" blue coordinator
start "red_team_support" /b "%ComSpec%" /c call "%~dp0team_node.cmd" red support
start "blue_team_support" /b "%ComSpec%" /c call "%~dp0team_node.cmd" blue support
