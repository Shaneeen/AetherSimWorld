@echo off
setlocal

set PYTHONHOME=
set PYTHONPATH=
set ROS_LOG_DIR=D:\SimWorld\logs\ros
set FASTDDS_BUILTIN_TRANSPORTS=UDPv4
set PATH=D:\pixi_ws\.pixi\envs\default;D:\pixi_ws\.pixi\envs\default\Library\bin;D:\pixi_ws\.pixi\envs\default\Scripts;C:\Windows\System32;C:\Windows;C:\Windows\System32\Wbem;C:\Windows\System32\WindowsPowerShell\v1.0

set SIMWORLD_USE_EXISTING_DRONES=1
set SIMWORLD_DRONE_AUTO_SPAWN=0

if "%SIMWORLD_DRONE_A_NAME%"=="" set SIMWORLD_DRONE_A_NAME=DroneA
if "%SIMWORLD_DRONE_B_NAME%"=="" set SIMWORLD_DRONE_B_NAME=DroneB
if "%SIM_OBSTACLE_COLLISION_ENABLED%"=="" set SIM_OBSTACLE_COLLISION_ENABLED=1
if "%SIM_OBSTACLE_NAME_PATTERNS%"=="" set SIM_OBSTACLE_NAME_PATTERNS=obstacle
if "%SIM_OBSTACLE_RADIUS_CM%"=="" set SIM_OBSTACLE_RADIUS_CM=170
if "%SIM_DRONE_COLLISION_RADIUS_CM%"=="" set SIM_DRONE_COLLISION_RADIUS_CM=70

if not exist D:\SimWorld\logs\ros mkdir D:\SimWorld\logs\ros

call D:\pixi_ws\ros2-windows\local_setup.bat
call D:\SimWorld\ros2_ws\install\local_setup.bat

echo [bridge] Obstacle collision: enabled=%SIM_OBSTACLE_COLLISION_ENABLED% patterns=%SIM_OBSTACLE_NAME_PATTERNS% obstacle_radius=%SIM_OBSTACLE_RADIUS_CM% drone_radius=%SIM_DRONE_COLLISION_RADIUS_CM%
D:\pixi_ws\.pixi\envs\default\python.exe D:\pixi_ws\ros2-windows\Scripts\ros2-script.py run simworld_drone_ros ue_bridge
