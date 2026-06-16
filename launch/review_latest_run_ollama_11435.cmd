@echo off
setlocal
call "%~dp0ollama_11435_env.cmd"
echo [ollama-11435] Reviewing latest run with private Ollama endpoint: %SIM_VLM_BASE_URL%
call "%~dp0review_latest_run.cmd" %*

