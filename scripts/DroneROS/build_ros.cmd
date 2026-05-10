@echo off
setlocal

set PYTHONHOME=
set PYTHONPATH=
set ROS_LOG_DIR=D:\SimWorld\logs\ros
set FASTDDS_BUILTIN_TRANSPORTS=UDPv4
set PATH=D:\pixi_ws\.pixi\envs\default;D:\pixi_ws\.pixi\envs\default\Library\bin;D:\pixi_ws\.pixi\envs\default\Scripts;C:\Windows\System32;C:\Windows;C:\Windows\System32\Wbem;C:\Windows\System32\WindowsPowerShell\v1.0

if not exist D:\SimWorld\logs\ros mkdir D:\SimWorld\logs\ros

call D:\pixi_ws\ros2-windows\local_setup.bat
cd /d D:\SimWorld\ros2_ws

D:\pixi_ws\.pixi\envs\default\python.exe -m colcon build --merge-install
