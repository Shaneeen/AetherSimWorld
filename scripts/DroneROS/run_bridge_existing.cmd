@echo off
setlocal

set PYTHONHOME=
set PYTHONPATH=
set ROS_LOG_DIR=D:\SimWorld\logs\ros
set FASTDDS_BUILTIN_TRANSPORTS=UDPv4
set PATH=D:\pixi_ws\.pixi\envs\default;D:\pixi_ws\.pixi\envs\default\Library\bin;D:\pixi_ws\.pixi\envs\default\Scripts;C:\Windows\System32;C:\Windows;C:\Windows\System32\Wbem;C:\Windows\System32\WindowsPowerShell\v1.0

set SIMWORLD_USE_EXISTING_DRONES=1
set SIMWORLD_DRONE_AUTO_SPAWN=0
set SIMWORLD_TEAM_AUTO_SPAWN=0
if "%SIMWORLD_DRONE_SWEEP%"=="" set SIMWORLD_DRONE_SWEEP=1
set SIM_TEAM_CONFIG_FILE=D:\SimWorld\scripts\DroneROS\team_match_config.cmd
if exist "%SIM_TEAM_CONFIG_FILE%" if /I not "%SIM_IGNORE_TEAM_CONFIG%"=="1" call "%SIM_TEAM_CONFIG_FILE%"

if "%SIMWORLD_DRONE_A_NAME%"=="" set SIMWORLD_DRONE_A_NAME=DroneA
if "%SIMWORLD_DRONE_B_NAME%"=="" set SIMWORLD_DRONE_B_NAME=DroneB
if "%SIMWORLD_DIRECT_ON_SWEEP_BLOCK%"=="" set SIMWORLD_DIRECT_ON_SWEEP_BLOCK=0
if "%SIM_RED_TEAM_ASSET%"=="" set SIM_RED_TEAM_ASSET=/Game/CityDatabase/blueprints/BP_Box2.BP_Box2_C
if "%SIM_BLUE_TEAM_ASSET%"=="" set SIM_BLUE_TEAM_ASSET=/Game/CityDatabase/blueprints/BP_Box3.BP_Box3_C
if "%SIM_OBSTACLE_COLLISION_ENABLED%"=="" set SIM_OBSTACLE_COLLISION_ENABLED=1
if "%SIM_OBSTACLE_NAME_PATTERNS%"=="" set SIM_OBSTACLE_NAME_PATTERNS=obstacle,wall,building,barrier,blocker
if "%SIM_OBSTACLE_RADIUS_CM%"=="" set SIM_OBSTACLE_RADIUS_CM=170
if "%SIM_DRONE_COLLISION_RADIUS_CM%"=="" set SIM_DRONE_COLLISION_RADIUS_CM=70
if "%SIM_TARGET_BOUND_X%"=="" set SIM_TARGET_BOUND_X=1350
if "%SIM_TARGET_BOUND_Y%"=="" set SIM_TARGET_BOUND_Y=1350
if "%SIM_ARENA_BOUNDARY_COLLISION_ENABLED%"=="" set SIM_ARENA_BOUNDARY_COLLISION_ENABLED=1
if "%SIM_ARENA_BOUNDARY_MARGIN_CM%"=="" set SIM_ARENA_BOUNDARY_MARGIN_CM=90
if "%SIM_TACTICAL_CLEARANCE_CM%"=="" set SIM_TACTICAL_CLEARANCE_CM=180
if "%SIM_CATCH_DISTANCE%"=="" set SIM_CATCH_DISTANCE=160
if "%SIM_TEAM_CATCH_MODE%"=="" set SIM_TEAM_CATCH_MODE=primary
if "%SIM_TEAM_ROUND_MODE%"=="" set SIM_TEAM_ROUND_MODE=tag
if "%SIM_TEAM_ELIMINATION_GROUND_Z%"=="" set SIM_TEAM_ELIMINATION_GROUND_Z=0
if "%SIM_TEAM_ELIMINATION_GRACE_SEC%"=="" set SIM_TEAM_ELIMINATION_GRACE_SEC=3.0
if "%SIM_INACTIVE_DRONE_PARK_ENABLED%"=="" set SIM_INACTIVE_DRONE_PARK_ENABLED=1
if "%SIM_INACTIVE_DRONE_PARK_X%"=="" set SIM_INACTIVE_DRONE_PARK_X=2800
if "%SIM_INACTIVE_DRONE_PARK_Y%"=="" set SIM_INACTIVE_DRONE_PARK_Y=2800
if "%SIM_INACTIVE_DRONE_PARK_Z%"=="" set SIM_INACTIVE_DRONE_PARK_Z=150
if "%SIM_INACTIVE_DRONE_PARK_SPACING%"=="" set SIM_INACTIVE_DRONE_PARK_SPACING=160

if not exist D:\SimWorld\logs\ros mkdir D:\SimWorld\logs\ros

call D:\pixi_ws\ros2-windows\local_setup.bat
call D:\SimWorld\ros2_ws\install\local_setup.bat

echo [bridge] Obstacle collision: enabled=%SIM_OBSTACLE_COLLISION_ENABLED% patterns=%SIM_OBSTACLE_NAME_PATTERNS% obstacle_radius=%SIM_OBSTACLE_RADIUS_CM% drone_radius=%SIM_DRONE_COLLISION_RADIUS_CM%
echo [bridge] Arena boundary: enabled=%SIM_ARENA_BOUNDARY_COLLISION_ENABLED% bounds=(%SIM_TARGET_BOUND_X%,%SIM_TARGET_BOUND_Y%) margin=%SIM_ARENA_BOUNDARY_MARGIN_CM%
echo [bridge] Tactical blockers: clearance=%SIM_TACTICAL_CLEARANCE_CM% manual=%SIM_TACTICAL_BLOCKERS% collision=%SIM_COLLISION_BLOCKERS% los=%SIM_LOS_BLOCKERS%
echo [bridge] Catch distance: %SIM_CATCH_DISTANCE% cm team_mode=%SIM_TEAM_CATCH_MODE% round=%SIM_TEAM_ROUND_MODE%
if /I "%SIM_TEAM_ROUND_MODE%"=="red_elimination" echo [bridge] Elimination: ground_z=%SIM_TEAM_ELIMINATION_GROUND_Z% grace=%SIM_TEAM_ELIMINATION_GRACE_SEC%s
echo [bridge] Inactive drone parking: enabled=%SIM_INACTIVE_DRONE_PARK_ENABLED% area=(%SIM_INACTIVE_DRONE_PARK_X%,%SIM_INACTIVE_DRONE_PARK_Y%,%SIM_INACTIVE_DRONE_PARK_Z%)
if "%SIM_TEAM_MATCH_CONFIGURED%"=="1" echo [bridge] Team config: red=%SIM_RED_TEAM_SIZE% blue=%SIM_BLUE_TEAM_SIZE% using existing manual drone actors
set PYTHONPATH=D:\SimWorld\ros2_ws\src\simworld_drone_ros;%PYTHONPATH%
D:\pixi_ws\.pixi\envs\default\python.exe -m simworld_drone_ros.bridge.ue_bridge
