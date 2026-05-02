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
if "%CATCH_DISTANCE%"=="" set CATCH_DISTANCE=40

echo [brains] Preparing environment...
cd /d C:\pixi_ws || goto :fail
set "PIXI_ENV=C:\pixi_ws\.pixi\envs\default"
if not exist "%PIXI_ENV%\python.exe" goto :fail
set "PATH=%PIXI_ENV%;%PIXI_ENV%\Scripts;%PIXI_ENV%\Library\bin;%PIXI_ENV%\DLLs;%PATH%"
call C:\pixi_ws\ros2-windows\local_setup.bat || goto :fail
call D:\SimWorld\ros2_ws\install\local_setup.bat || goto :fail

echo [brains] Starting target brain...
start "Target Brain" cmd /k "cd /d C:\pixi_ws && set PATH=%PIXI_ENV%;%PIXI_ENV%\Scripts;%PIXI_ENV%\Library\bin;%PIXI_ENV%\DLLs;%%PATH%% && call C:\pixi_ws\ros2-windows\local_setup.bat && call D:\SimWorld\ros2_ws\install\local_setup.bat && set SIM_TARGET_SPEED=%TARGET_SPEED% && set SIM_TARGET_MOVE_SEC=%MOVE_SEC% && set SIM_TARGET_REST_SEC=%REST_SEC% && ros2 run simworld_drone_ros target_brain"

echo [brains] Starting chaser brain...
start "Chaser Brain" cmd /k "cd /d C:\pixi_ws && set PATH=%PIXI_ENV%;%PIXI_ENV%\Scripts;%PIXI_ENV%\Library\bin;%PIXI_ENV%\DLLs;%%PATH%% && call C:\pixi_ws\ros2-windows\local_setup.bat && call D:\SimWorld\ros2_ws\install\local_setup.bat && set SIM_CHASER_SPEED=%CHASER_SPEED% && set SIM_CATCH_DISTANCE=%CATCH_DISTANCE% && ros2 run simworld_drone_ros chaser_brain"

echo [brains] Both brain windows launched.
goto :eof

:fail
echo [brains] Failed to launch brains.
exit /b 1
