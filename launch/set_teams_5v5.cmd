@echo off
setlocal

call "%~dp0env.cmd"

(
  echo set "SIM_TEAM_MATCH_CONFIGURED=1"
  echo set "SIM_RED_TEAM_SIZE=5"
  echo set "SIM_BLUE_TEAM_SIZE=5"
  echo set "SIM_TEAM_ROUND_MODE=tag"
  echo set "SIM_TEAM_CATCH_MODE=primary"
  echo set "SIM_TEAM_START_ACTIVE=1"
  echo set "SIM_TEAM_SUPPORT_AUTOSTART=1"
) > "%SIM_TEAM_CONFIG_FILE%"

echo [team] Saved 5v5 config: %SIM_TEAM_CONFIG_FILE%
type "%SIM_TEAM_CONFIG_FILE%"
