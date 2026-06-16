@echo off
setlocal

call "%~dp0env.cmd"
if exist "%SIM_TEAM_CONFIG_FILE%" if /I not "%SIM_IGNORE_TEAM_CONFIG%"=="1" call "%SIM_TEAM_CONFIG_FILE%"

if "%SIM_VLM_MODEL%"=="" set "SIM_VLM_MODEL=qwen3-vl:latest"
if "%SIM_VISION_CHECK_TIMEOUT_SEC%"=="" set "SIM_VISION_CHECK_TIMEOUT_SEC=60"
if "%SIM_VISION_CAMERA_ID%"=="" set "SIM_VISION_CAMERA_ID=0"
if "%SIM_VISION_CAMERA_WIDTH%"=="" set "SIM_VISION_CAMERA_WIDTH=320"
if "%SIM_VISION_CAMERA_HEIGHT%"=="" set "SIM_VISION_CAMERA_HEIGHT=240"
if "%SIM_VLM_NUM_CTX%"=="" set "SIM_VLM_NUM_CTX=512"
if "%SIM_VLM_NUM_PREDICT%"=="" set "SIM_VLM_NUM_PREDICT=256"
if "%SIM_VISION_PREP_OLLAMA%"=="" set "SIM_VISION_PREP_OLLAMA=1"

echo [vision-check] Checking VLM and optional UnrealCV camera stack...
if /I not "%SIM_VISION_PREP_OLLAMA%"=="0" if /I not "%SIM_VISION_PREP_OLLAMA%"=="false" (
    "%PYTHON_EXE%" -u -m simworld_drone_ros.vision.prepare_ollama
)
"%PYTHON_EXE%" -u -m simworld_drone_ros.vision.check_vision_stack
