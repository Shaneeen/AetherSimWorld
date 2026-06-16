@echo off
rem Shared private Ollama endpoint for the AetherSim VLM/VLA stack.
rem Use this from wrapper scripts so every spawned cmd window inherits the same server.

set "SIM_VLM_BASE_URL=http://10.8.0.132:11435"
set "SIM_VLM_API_URL=http://10.8.0.132:11435/api/generate"
set "OLLAMA_API_URL=http://10.8.0.132:11435/api/generate"
set "OLLAMA_API_URLS=http://10.8.0.132:11435/api/generate"
set "SIM_TEAM_OLLAMA_API_URL=http://10.8.0.132:11435/api/generate"
set "SIM_TEAM_OLLAMA_API_URLS=http://10.8.0.132:11435/api/generate"
set "SIM_RUN_REPORT_API_URL=http://10.8.0.132:11435/api/generate"

set "SIM_VISION_PREP_OLLAMA=1"
set "SIM_TEAM_PREP_OLLAMA=1"
set "SIM_VISION_UNLOAD_MODELS=magicoder:latest"

