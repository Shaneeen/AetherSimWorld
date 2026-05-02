@echo off
setlocal

echo [split-start] Preparing ROS environment...
cd /d C:\pixi_ws || goto :fail
call C:\pixi_ws\ros2-windows\local_setup.bat || goto :fail
call D:\SimWorld\ros2_ws\install\local_setup.bat || goto :fail

echo.
echo [split-start] Active ROS nodes:
ros2 node list

echo.
echo [split-start] Sending START_A (1/2)...
ros2 topic pub --once /sim/control std_msgs/msg/String "{data: start_a}" || goto :fail

echo [split-start] Waiting 1 second...
timeout /t 1 /nobreak >nul

echo [split-start] Sending START_A (2/2)...
ros2 topic pub --once /sim/control std_msgs/msg/String "{data: start_a}" || goto :fail

echo [split-start] Waiting 2 seconds before START_B...
timeout /t 2 /nobreak >nul

echo [split-start] Sending START_B (1/2)...
ros2 topic pub --once /sim/control std_msgs/msg/String "{data: start_b}" || goto :fail

echo [split-start] Waiting 1 second...
timeout /t 1 /nobreak >nul

echo [split-start] Sending START_B (2/2)...
ros2 topic pub --once /sim/control std_msgs/msg/String "{data: start_b}" || goto :fail

echo.
echo [split-start] Start sequence sent.
goto :eof

:fail
echo.
echo [split-start] Failed to publish split start sequence.
exit /b 1
