@echo off
setlocal

call "%~dp0env.cmd"
if exist "%SIM_TEAM_CONFIG_FILE%" del "%SIM_TEAM_CONFIG_FILE%"
echo [team] Cleared team config.
