$ErrorActionPreference = "Stop"

$env:PYTHONPATH = "D:\SimWorld;" + $env:PYTHONPATH

$rosSetup = if ($env:ROS_SETUP_PS1) { $env:ROS_SETUP_PS1 } else { "C:\pixi_ws\ros2-windows\local_setup.ps1" }
if (-not (Test-Path $rosSetup)) {
    throw "ROS 2 setup script not found: $rosSetup"
}

. $rosSetup

Push-Location "D:\SimWorld\ros2_ws"
try {
    . .\install\local_setup.ps1
    & ros2 topic pub --once /sim/control std_msgs/msg/String "{data: start}"
} finally {
    Pop-Location
}
