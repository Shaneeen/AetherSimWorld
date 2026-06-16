@echo off
setlocal

call "%~dp0env.cmd"

if "%SIM_RUN_REPORT_MODEL%"=="" set "SIM_RUN_REPORT_MODEL=gpt-oss:latest"
if "%SIM_RUN_REPORT_API_URL%"=="" set "SIM_RUN_REPORT_API_URL=http://10.8.0.132:11434/api/generate"
if "%SIM_RUN_REPORT_TIMEOUT_SEC%"=="" set "SIM_RUN_REPORT_TIMEOUT_SEC=0"

echo [run-report] Reviewing latest SimWorld run...
echo [run-report] Model: %SIM_RUN_REPORT_MODEL%
if "%SIM_RUN_REPORT_TIMEOUT_SEC%"=="0" (
    echo [run-report] Timeout: wait until complete
) else (
    echo [run-report] Timeout: %SIM_RUN_REPORT_TIMEOUT_SEC%s
)
"%PYTHON_EXE%" -u -m simworld_drone_ros.analysis.run_report
