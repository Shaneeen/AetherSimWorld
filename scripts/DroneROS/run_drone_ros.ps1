$env:SIMWORLD_HOST = if ($env:SIMWORLD_HOST) { $env:SIMWORLD_HOST } else { "127.0.0.1" }
$env:SIMWORLD_PORT = if ($env:SIMWORLD_PORT) { $env:SIMWORLD_PORT } else { "9000" }
$env:SIMWORLD_DRONE_ASSET = if ($env:SIMWORLD_DRONE_ASSET) { $env:SIMWORLD_DRONE_ASSET } else { "/Game/TrafficSystem/Pedestrian/Base_User_Agent.Base_User_Agent_C" }
$env:SIMWORLD_DRONE_NAME = if ($env:SIMWORLD_DRONE_NAME) { $env:SIMWORLD_DRONE_NAME } else { "ROS_SM_Drone_0" }
$env:SIMWORLD_DRONE_AUTO_SPAWN = if ($env:SIMWORLD_DRONE_AUTO_SPAWN) { $env:SIMWORLD_DRONE_AUTO_SPAWN } else { "1" }
$env:SIMWORLD_DRONE_X = if ($env:SIMWORLD_DRONE_X) { $env:SIMWORLD_DRONE_X } else { "0" }
$env:SIMWORLD_DRONE_Y = if ($env:SIMWORLD_DRONE_Y) { $env:SIMWORLD_DRONE_Y } else { "0" }
$env:SIMWORLD_DRONE_Z = if ($env:SIMWORLD_DRONE_Z) { $env:SIMWORLD_DRONE_Z } else { "600" }
$env:SIMWORLD_DRONE_YAW = if ($env:SIMWORLD_DRONE_YAW) { $env:SIMWORLD_DRONE_YAW } else { "0" }
$env:PYTHONPATH = "D:\SimWorld;" + $env:PYTHONPATH

$rosSetup = if ($env:ROS_SETUP_PS1) {
    $env:ROS_SETUP_PS1
} else {
    "C:\dev\ros2_jazzy\local_setup.ps1"
}

if (-not (Test-Path $rosSetup)) {
    throw "ROS 2 setup script not found: $rosSetup"
}

. $rosSetup

Push-Location "D:\SimWorld\ros2_ws"
try {
    colcon build --symlink-install
    . .\install\local_setup.ps1

    $bridge = Start-Process -FilePath "ros2" -ArgumentList "run", "simworld_drone_ros", "ue_bridge" -PassThru
    Start-Sleep -Seconds 2
    $brain = Start-Process -FilePath "ros2" -ArgumentList "run", "simworld_drone_ros", "brain" -PassThru

    Write-Host "Bridge PID: $($bridge.Id)"
    Write-Host "Brain PID:  $($brain.Id)"
    Write-Host "Press Ctrl+C to stop the launcher."
    while ($true) {
        Start-Sleep -Seconds 2
        if ($bridge.HasExited -or $brain.HasExited) {
            break
        }
    }
} finally {
    Pop-Location
}
