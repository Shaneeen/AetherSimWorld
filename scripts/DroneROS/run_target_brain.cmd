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
set SIM_TEAM_CONFIG_FILE=D:\SimWorld\scripts\DroneROS\team_match_config.cmd
if exist "%SIM_TEAM_CONFIG_FILE%" if /I not "%SIM_IGNORE_TEAM_CONFIG%"=="1" call "%SIM_TEAM_CONFIG_FILE%"
if "%SIM_TEAM_MATCH_CONFIGURED%"=="1" (
    if not "%SIM_RED_CRUISE_SPEED%"=="" set SIM_TARGET_CRUISE_SPEED=%SIM_RED_CRUISE_SPEED%
    if not "%SIM_RED_EVADE_SPEED%"=="" set SIM_TARGET_EVADE_SPEED=%SIM_RED_EVADE_SPEED%
    if not "%SIM_RED_BURST_SPEED%"=="" set SIM_TARGET_BURST_SPEED=%SIM_RED_BURST_SPEED%
    if "%SIM_TARGET_BURST_SEC%"=="" set SIM_TARGET_BURST_SEC=2.4
    if "%SIM_TARGET_BURST_COOLDOWN_SEC%"=="" set SIM_TARGET_BURST_COOLDOWN_SEC=4.0
    if "%SIM_TARGET_STAMINA_REGEN_PER_SEC%"=="" set SIM_TARGET_STAMINA_REGEN_PER_SEC=11
    if "%SIM_TARGET_BURST_STAMINA_COST%"=="" set SIM_TARGET_BURST_STAMINA_COST=30
    if "%SIM_TARGET_BURST_STAMINA_DRAIN_PER_SEC%"=="" set SIM_TARGET_BURST_STAMINA_DRAIN_PER_SEC=9
    if "%SIM_TARGET_PANIC_RANGE_CM%"=="" set SIM_TARGET_PANIC_RANGE_CM=800
    if "%SIM_TARGET_ALERT_RANGE_CM%"=="" set SIM_TARGET_ALERT_RANGE_CM=2400
    set SIM_SKIP_BRAIN_SPEED_PROMPT=1
)
if "%SIM_TARGET_SPEED%"=="" set SIM_TARGET_SPEED=220
if "%SIM_TARGET_CRUISE_SPEED%"=="" set SIM_TARGET_CRUISE_SPEED=%SIM_TARGET_SPEED%
if "%SIM_TARGET_EVADE_SPEED%"=="" set /A SIM_TARGET_EVADE_SPEED=%SIM_TARGET_SPEED%+45
if "%SIM_TARGET_BURST_SPEED%"=="" set /A SIM_TARGET_BURST_SPEED=%SIM_TARGET_SPEED%+115
if "%SIMWORLD_DRONE_MIN_Z%"=="" set SIMWORLD_DRONE_MIN_Z=100
if "%SIMWORLD_DRONE_MAX_Z%"=="" set SIMWORLD_DRONE_MAX_Z=700
if "%SIM_TARGET_BOUND_X%"=="" set SIM_TARGET_BOUND_X=1350
if "%SIM_TARGET_BOUND_Y%"=="" set SIM_TARGET_BOUND_Y=1350
if "%SIM_ARENA_BOUNDARY_MARGIN_CM%"=="" set SIM_ARENA_BOUNDARY_MARGIN_CM=90
if "%SIM_TARGET_CRUISE_Z%"=="" set SIM_TARGET_CRUISE_Z=450
if "%SIM_TARGET_VERTICAL_SPEED%"=="" set SIM_TARGET_VERTICAL_SPEED=150
if "%SIM_TARGET_ALTITUDE_STEP%"=="" set SIM_TARGET_ALTITUDE_STEP=180
if "%SIM_TARGET_ALTITUDE_TACTIC_HOLD_SEC%"=="" set SIM_TARGET_ALTITUDE_TACTIC_HOLD_SEC=2.5
if "%SIM_TARGET_STUCK_SPEED_THRESHOLD_CM_S%"=="" set SIM_TARGET_STUCK_SPEED_THRESHOLD_CM_S=65
if "%SIM_TARGET_STUCK_AFTER_SEC%"=="" set SIM_TARGET_STUCK_AFTER_SEC=0.8
if "%SIM_TARGET_UNSTUCK_SEC%"=="" set SIM_TARGET_UNSTUCK_SEC=2.2
if "%SIM_TARGET_STUCK_START_GRACE_SEC%"=="" set SIM_TARGET_STUCK_START_GRACE_SEC=2.5
if "%SIM_SKIP_BRAIN_SPEED_PROMPT%"=="1" (
    echo [target] Using saved team speed config; skipping individual speed prompt.
    echo [target] Team mode uses DroneA as red_1; support drones are handled by run_team_support.cmd.
) else (
    set SIM_SPEED_ENV_FILE=%TEMP%\simworld_target_speeds_%RANDOM%.cmd
    powershell -NoProfile -ExecutionPolicy Bypass -File D:\SimWorld\scripts\DroneROS\configure_brain_speeds.ps1 -DefaultDrone target -OutputCmd "%SIM_SPEED_ENV_FILE%"
    if exist "%SIM_SPEED_ENV_FILE%" call "%SIM_SPEED_ENV_FILE%"
    if exist "%SIM_SPEED_ENV_FILE%" del "%SIM_SPEED_ENV_FILE%"
)
set PATH=D:\pixi_ws\.pixi\envs\default;D:\pixi_ws\.pixi\envs\default\Library\bin;D:\pixi_ws\.pixi\envs\default\Scripts;C:\Windows\System32;C:\Windows;C:\Windows\System32\Wbem;C:\Windows\System32\WindowsPowerShell\v1.0

if not exist D:\SimWorld\logs\ros mkdir D:\SimWorld\logs\ros

call D:\pixi_ws\ros2-windows\local_setup.bat
call D:\SimWorld\ros2_ws\install\local_setup.bat
set PYTHONPATH=D:\SimWorld\ros2_ws\src\simworld_drone_ros;%PYTHONPATH%

echo [target] Ollama model: %OLLAMA_MODEL%
echo [target] Ollama API: %OLLAMA_API_URL%
echo [target] Speeds: cruise=%SIM_TARGET_CRUISE_SPEED% evade=%SIM_TARGET_EVADE_SPEED% burst=%SIM_TARGET_BURST_SPEED%
echo [target] Altitude: range=%SIMWORLD_DRONE_MIN_Z%-%SIMWORLD_DRONE_MAX_Z% cruise=%SIM_TARGET_CRUISE_Z% vz=%SIM_TARGET_VERTICAL_SPEED% step=%SIM_TARGET_ALTITUDE_STEP% hold=%SIM_TARGET_ALTITUDE_TACTIC_HOLD_SEC%s
echo [target] Arena bounds: x=%SIM_TARGET_BOUND_X% y=%SIM_TARGET_BOUND_Y% margin=%SIM_ARENA_BOUNDARY_MARGIN_CM%
D:\pixi_ws\.pixi\envs\default\python.exe -m simworld_drone_ros.duel.target_brain
