@echo off
setlocal
call "%~dp0ollama_11435_env.cmd"
echo [ollama-11435] Running vision check with private Ollama endpoint: %SIM_VLM_BASE_URL%
call "%~dp0vision_check.cmd" %*

