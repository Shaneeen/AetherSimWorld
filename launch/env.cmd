@echo off

set "SIMWORLD_ROOT=%~dp0.."
for %%I in ("%SIMWORLD_ROOT%") do set "SIMWORLD_ROOT=%%~fI"

set "PIXI_ROOT=C:\pixi_ws"
set "PYTHON_EXE=%PIXI_ROOT%\.pixi\envs\default\python.exe"
set "ROS_SETUP=%PIXI_ROOT%\ros2-windows\local_setup.bat"
set "WS_SETUP=%SIMWORLD_ROOT%\ros2_ws\install\local_setup.bat"
set "SIM_TEAM_CONFIG_FILE=%SIMWORLD_ROOT%\launch\team_match_config.cmd"

set PYTHONHOME=
set "ROS_LOG_DIR=%SIMWORLD_ROOT%\logs\ros"
set "SIM_CHASE_WATCH_LOG_DIR=%SIMWORLD_ROOT%\logs\chase_watch"
set "RMW_IMPLEMENTATION=rmw_cyclonedds_cpp"
set "FASTDDS_BUILTIN_TRANSPORTS=UDPv4"

if not exist "%ROS_LOG_DIR%" mkdir "%ROS_LOG_DIR%"
if not exist "%SIM_CHASE_WATCH_LOG_DIR%" mkdir "%SIM_CHASE_WATCH_LOG_DIR%"

set "PATH=%PIXI_ROOT%\ros2-windows\Scripts;%PIXI_ROOT%\ros2-windows\bin;%PIXI_ROOT%\.pixi\envs\default;%PIXI_ROOT%\.pixi\envs\default\Library\bin;%PIXI_ROOT%\.pixi\envs\default\Scripts;C:\Windows\System32;C:\Windows;C:\Windows\System32\Wbem;C:\Windows\System32\WindowsPowerShell\v1.0"
set "PYTHONPATH=%SIMWORLD_ROOT%\launch\ros2_dll_site;%PIXI_ROOT%\ros2-windows\Lib\site-packages;%SIMWORLD_ROOT%\ros2_ws\src\simworld_drone_ros;%SIMWORLD_ROOT%\ros2_ws\install\Lib\site-packages;%PYTHONPATH%"

if exist "%ROS_SETUP%" call "%ROS_SETUP%"
if exist "%WS_SETUP%" call "%WS_SETUP%"

set "PYTHONPATH=%SIMWORLD_ROOT%\launch\ros2_dll_site;%PIXI_ROOT%\ros2-windows\Lib\site-packages;%SIMWORLD_ROOT%\ros2_ws\src\simworld_drone_ros;%SIMWORLD_ROOT%\ros2_ws\install\Lib\site-packages;%PYTHONPATH%"
