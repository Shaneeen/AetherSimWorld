param(
    [double]$TargetSpeed = 220,
    [double]$MoveSec = 3,
    [double]$RestSec = 5,
    [double]$ChaserSpeed = 260,
    [double]$CatchDistance = 120
)

$ErrorActionPreference = "Stop"

$env:SIMWORLD_HOST = if ($env:SIMWORLD_HOST) { $env:SIMWORLD_HOST } else { "127.0.0.1" }
$env:SIMWORLD_PORT = if ($env:SIMWORLD_PORT) { $env:SIMWORLD_PORT } else { "9000" }
$env:SIMWORLD_DRONE_ASSET = if ($env:SIMWORLD_DRONE_ASSET) { $env:SIMWORLD_DRONE_ASSET } else { "/Game/CityDatabase/blueprints/BP_Box3.BP_Box3_C" }
$env:SIMWORLD_DRONE_A_NAME = if ($env:SIMWORLD_DRONE_A_NAME) { $env:SIMWORLD_DRONE_A_NAME } else { "DroneA" }
$env:SIMWORLD_DRONE_B_NAME = if ($env:SIMWORLD_DRONE_B_NAME) { $env:SIMWORLD_DRONE_B_NAME } else { "DroneB" }
$env:SIMWORLD_DRONE_A_X = if ($env:SIMWORLD_DRONE_A_X) { $env:SIMWORLD_DRONE_A_X } else { "600" }
$env:SIMWORLD_DRONE_B_X = if ($env:SIMWORLD_DRONE_B_X) { $env:SIMWORLD_DRONE_B_X } else { "-600" }
$env:SIMWORLD_DRONE_Y = if ($env:SIMWORLD_DRONE_Y) { $env:SIMWORLD_DRONE_Y } else { "0" }
$env:SIMWORLD_DRONE_Z = if ($env:SIMWORLD_DRONE_Z) { $env:SIMWORLD_DRONE_Z } else { "600" }
$env:SIM_TARGET_SPEED = "$TargetSpeed"
$env:SIM_TARGET_MOVE_SEC = "$MoveSec"
$env:SIM_TARGET_REST_SEC = "$RestSec"
$env:SIM_CHASER_SPEED = "$ChaserSpeed"
$env:SIM_CATCH_DISTANCE = "$CatchDistance"
$env:PYTHONPATH = "D:\SimWorld;" + $env:PYTHONPATH

$rosSetup = if ($env:ROS_SETUP_PS1) { $env:ROS_SETUP_PS1 } else { "C:\dev\ros2_jazzy\local_setup.ps1" }
if (-not (Test-Path $rosSetup)) {
    throw "ROS 2 setup script not found: $rosSetup"
}

. $rosSetup

Push-Location "D:\SimWorld\ros2_ws"
try {
    . .\install\local_setup.ps1

    $pythonExe = if ($env:PYTHON_EXE) { $env:PYTHON_EXE } else { "python" }

    Write-Host "Starting chase simulation..."
    Write-Host "TargetSpeed=$TargetSpeed MoveSec=$MoveSec RestSec=$RestSec ChaserSpeed=$ChaserSpeed CatchDistance=$CatchDistance"

    $bridge = Start-Process -FilePath $pythonExe -ArgumentList "-m", "simworld_drone_ros.ue_bridge" -PassThru
    Start-Sleep -Seconds 2
    $target = Start-Process -FilePath $pythonExe -ArgumentList "-m", "simworld_drone_ros.target_brain" -PassThru
    $chaser = Start-Process -FilePath $pythonExe -ArgumentList "-m", "simworld_drone_ros.chaser_brain" -PassThru

    Write-Host "Bridge PID: $($bridge.Id)"
    Write-Host "Target PID: $($target.Id)"
    Write-Host "Chaser PID: $($chaser.Id)"
    Write-Host "Press Ctrl+C in this window to stop the chase."

    while ($true) {
        Start-Sleep -Seconds 2
        if ($bridge.HasExited -or $target.HasExited -or $chaser.HasExited) {
            throw "One of the chase processes exited unexpectedly."
        }
    }
} finally {
    foreach ($proc in @($bridge, $target, $chaser)) {
        if ($proc -and -not $proc.HasExited) {
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
    }
    Pop-Location
}
