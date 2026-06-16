@echo off
setlocal

call "%~dp0env.cmd"
if exist "%SIM_TEAM_CONFIG_FILE%" if /I not "%SIM_IGNORE_TEAM_CONFIG%"=="1" call "%SIM_TEAM_CONFIG_FILE%"

if "%SIM_VISION_ENABLED%"=="" set "SIM_VISION_ENABLED=1"
if "%SIM_VLM_ENABLED%"=="" set "SIM_VLM_ENABLED=1"
if "%SIM_VISION_IMAGE_VLM_ENABLED%"=="" set "SIM_VISION_IMAGE_VLM_ENABLED=0"

:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--image" (
    set "SIM_VISION_IMAGE_VLM_ENABLED=1"
    shift
    goto parse_args
)
if /I "%~1"=="-Image" (
    set "SIM_VISION_IMAGE_VLM_ENABLED=1"
    shift
    goto parse_args
)
if /I "%~1"=="image" (
    set "SIM_VISION_IMAGE_VLM_ENABLED=1"
    shift
    goto parse_args
)
if /I "%~1"=="--context" (
    set "SIM_VISION_IMAGE_VLM_ENABLED=0"
    shift
    goto parse_args
)
if "%SIM_VISION_OBSERVER%"=="" set "SIM_VISION_OBSERVER=%~1"
shift
goto parse_args

:args_done
if "%SIM_VISION_OBSERVER%"=="" set "SIM_VISION_OBSERVER=blue_1"
if "%SIM_VISION_CAMERA_ID%"=="" set "SIM_VISION_CAMERA_ID=0"
if "%SIM_VLM_MODEL%"=="" set "SIM_VLM_MODEL=qwen3-vl:latest"
if "%SIM_VLM_API_URL%"=="" set "SIM_VLM_API_URL=http://10.8.0.132:11434/api/generate"
if "%SIM_VLM_TIMEOUT_SEC%"=="" set "SIM_VLM_TIMEOUT_SEC=90"
if "%SIM_VISION_REQUEST_TIMEOUT_SEC%"=="" set "SIM_VISION_REQUEST_TIMEOUT_SEC=180"
if "%SIM_VISION_VLM_INTERVAL_SEC%"=="" set "SIM_VISION_VLM_INTERVAL_SEC=20"
if "%SIM_VISION_MIN_POSES_FOR_VLM%"=="" set "SIM_VISION_MIN_POSES_FOR_VLM=8"
if "%SIM_VISION_CAMERA_WIDTH%"=="" set "SIM_VISION_CAMERA_WIDTH=320"
if "%SIM_VISION_CAMERA_HEIGHT%"=="" set "SIM_VISION_CAMERA_HEIGHT=240"
if "%SIM_VLM_NUM_CTX%"=="" set "SIM_VLM_NUM_CTX=512"
if "%SIM_VLM_NUM_PREDICT%"=="" set "SIM_VLM_NUM_PREDICT=256"
if "%SIM_VISION_PREP_OLLAMA%"=="" set "SIM_VISION_PREP_OLLAMA=1"
if "%SIM_VISION_MISSION_GOAL_FILE%"=="" set "SIM_VISION_MISSION_GOAL_FILE=%SIMWORLD_ROOT%\overview\future_plan.md"

echo [vision] Visual observer
echo [vision] observer=%SIM_VISION_OBSERVER% model=%SIM_VLM_MODEL% url=%SIM_VLM_API_URL%
echo [vision] camera=%SIM_VISION_CAMERA_ID% size=%SIM_VISION_CAMERA_WIDTH%x%SIM_VISION_CAMERA_HEIGHT% timeout=%SIM_VLM_TIMEOUT_SEC%s interval=%SIM_VISION_VLM_INTERVAL_SEC%s image_vlm=%SIM_VISION_IMAGE_VLM_ENABLED%
if /I not "%SIM_VISION_PREP_OLLAMA%"=="0" if /I not "%SIM_VISION_PREP_OLLAMA%"=="false" (
    "%PYTHON_EXE%" -u -m simworld_drone_ros.vision.prepare_ollama
)
"%PYTHON_EXE%" -u -m simworld_drone_ros.vision.visual_observer
