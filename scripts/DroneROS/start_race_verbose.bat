@echo off
setlocal

echo [start] Preparing ROS environment...
cd /d C:\pixi_ws || goto :fail
call C:\pixi_ws\ros2-windows\local_setup.bat || goto :fail
call D:\SimWorld\ros2_ws\install\local_setup.bat || goto :fail

echo.
echo [start] Active ROS nodes:
ros2 node list

echo.
echo [start] /sim/control topic info:
ros2 topic info /sim/control -v

echo.
echo [start] Publishing START on /sim/control...
ros2 topic pub --once /sim/control std_msgs/msg/String "{data: start}" || goto :fail

echo.
echo [start] START published.
goto :eof

:fail
echo.
echo [start] Failed to prepare or publish START.
exit /b 1
