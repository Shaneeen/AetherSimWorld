@echo off

set SIM_TEAM_CONFIG_FILE=D:\SimWorld\scripts\DroneROS\team_match_config.cmd
if exist "%SIM_TEAM_CONFIG_FILE%" (
    del "%SIM_TEAM_CONFIG_FILE%"
    echo [team] Cleared saved team match config.
) else (
    echo [team] No saved team match config found.
)
