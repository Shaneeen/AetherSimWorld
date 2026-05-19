@echo off
setlocal

set PYTHONHOME=
set PYTHONPATH=
set ROS_LOG_DIR=D:\SimWorld\logs\ros
set FASTDDS_BUILTIN_TRANSPORTS=UDPv4
set USE_OLLAMA=1
set OLLAMA_MODEL=gpt-oss:latest
set SIM_TARGET_OLLAMA_MODEL=gpt-oss:latest
set OLLAMA_API_URL=http://10.8.0.132:11434/api/generate
set OLLAMA_API_URLS=http://10.8.0.132:11434/api/generate
set SIM_TARGET_OLLAMA_API_URL=http://10.8.0.132:11434/api/generate
set OLLAMA_OPENAI_URL=http://10.8.0.132:11434/v1
set OLLAMA_TIMEOUT_SEC=20
set SIM_TARGET_OLLAMA_NUM_PREDICT=512
set SIM_LOS_ENABLED=1
set SIM_TARGET_FAKE_OCCLUSION_PROB=0
if "%SIM_TARGET_SPEED%"=="" set SIM_TARGET_SPEED=220
if "%SIM_TARGET_CRUISE_SPEED%"=="" set SIM_TARGET_CRUISE_SPEED=%SIM_TARGET_SPEED%
if "%SIM_TARGET_EVADE_SPEED%"=="" set /A SIM_TARGET_EVADE_SPEED=%SIM_TARGET_SPEED%+45
if "%SIM_TARGET_BURST_SPEED%"=="" set /A SIM_TARGET_BURST_SPEED=%SIM_TARGET_SPEED%+115
if "%SIMWORLD_DRONE_MIN_Z%"=="" set SIMWORLD_DRONE_MIN_Z=100
if "%SIMWORLD_DRONE_MAX_Z%"=="" set SIMWORLD_DRONE_MAX_Z=700
if "%SIM_TARGET_CRUISE_Z%"=="" set SIM_TARGET_CRUISE_Z=450
if "%SIM_TARGET_VERTICAL_SPEED%"=="" set SIM_TARGET_VERTICAL_SPEED=220
if "%SIM_TARGET_ALTITUDE_STEP%"=="" set SIM_TARGET_ALTITUDE_STEP=220
set PATH=D:\pixi_ws\.pixi\envs\default;D:\pixi_ws\.pixi\envs\default\Library\bin;D:\pixi_ws\.pixi\envs\default\Scripts;C:\Windows\System32;C:\Windows;C:\Windows\System32\Wbem;C:\Windows\System32\WindowsPowerShell\v1.0

if not exist D:\SimWorld\logs\ros mkdir D:\SimWorld\logs\ros

call D:\pixi_ws\ros2-windows\local_setup.bat
call D:\SimWorld\ros2_ws\install\local_setup.bat

echo [target] Ollama model: %OLLAMA_MODEL%
echo [target] Ollama API: %OLLAMA_API_URL%
echo [target] Speeds: cruise=%SIM_TARGET_CRUISE_SPEED% evade=%SIM_TARGET_EVADE_SPEED% burst=%SIM_TARGET_BURST_SPEED%
echo [target] Altitude: range=%SIMWORLD_DRONE_MIN_Z%-%SIMWORLD_DRONE_MAX_Z% cruise=%SIM_TARGET_CRUISE_Z% vz=%SIM_TARGET_VERTICAL_SPEED% step=%SIM_TARGET_ALTITUDE_STEP%
D:\pixi_ws\.pixi\envs\default\python.exe D:\pixi_ws\ros2-windows\Scripts\ros2-script.py run simworld_drone_ros target_brain
