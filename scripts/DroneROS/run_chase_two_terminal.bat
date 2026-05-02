@echo off
setlocal

set TARGET_SPEED=%1
if "%TARGET_SPEED%"=="" set TARGET_SPEED=220

set MOVE_SEC=%2
if "%MOVE_SEC%"=="" set MOVE_SEC=3

set REST_SEC=%3
if "%REST_SEC%"=="" set REST_SEC=5

set CHASER_SPEED=%4
if "%CHASER_SPEED%"=="" set CHASER_SPEED=260

set CATCH_DISTANCE=%5
if "%CATCH_DISTANCE%"=="" set CATCH_DISTANCE=120

echo [run] Preparing ROS environment...
cd /d C:\pixi_ws || goto :fail
call C:\pixi_ws\ros2-windows\local_setup.bat || goto :fail
call D:\SimWorld\ros2_ws\install\local_setup.bat || goto :fail

echo.
echo [run] Launch settings:
echo [run]   Target speed:   %TARGET_SPEED%
echo [run]   Move seconds:   %MOVE_SEC%
echo [run]   Rest seconds:   %REST_SEC%
echo [run]   Chaser speed:   %CHASER_SPEED%
echo [run]   Catch distance: %CATCH_DISTANCE%

echo.
echo [run] Starting target brain window...
start "Target Brain" cmd /k "cd /d C:\pixi_ws && call C:\pixi_ws\ros2-windows\local_setup.bat && call D:\SimWorld\ros2_ws\install\local_setup.bat && set SIM_TARGET_SPEED=%TARGET_SPEED% && set SIM_TARGET_MOVE_SEC=%MOVE_SEC% && set SIM_TARGET_REST_SEC=%REST_SEC% && echo [target] launching target_brain && ros2 run simworld_drone_ros target_brain"

echo [run] Starting chaser brain window...
start "Chaser Brain" cmd /k "cd /d C:\pixi_ws && call C:\pixi_ws\ros2-windows\local_setup.bat && call D:\SimWorld\ros2_ws\install\local_setup.bat && set SIM_CHASER_SPEED=%CHASER_SPEED% && set SIM_CATCH_DISTANCE=%CATCH_DISTANCE% && echo [chaser] launching chaser_brain && ros2 run simworld_drone_ros chaser_brain"

echo.
echo [run] Waiting for the brain nodes to appear...
timeout /t 6 /nobreak >nul

echo.
echo [run] Active ROS nodes:
ros2 node list

echo.
echo [run] /sim/control topic info before start:
ros2 topic info /sim/control -v

echo.
echo [run] Sending START...
ros2 topic pub --once /sim/control std_msgs/msg/String "{data: start}" || goto :fail

echo.
echo [run] START sent. Watch the Target Brain and Chaser Brain windows for live logs.
goto :eof

:fail
echo.
echo [run] Failed to start the chase.
exit /b 1
