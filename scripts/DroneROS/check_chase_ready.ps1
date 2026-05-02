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
$env:PYTHONPATH = "D:\SimWorld;" + $env:PYTHONPATH

$rosSetup = if ($env:ROS_SETUP_PS1) { $env:ROS_SETUP_PS1 } else { "C:\pixi_ws\ros2-windows\local_setup.ps1" }
if (-not (Test-Path $rosSetup)) {
    throw "ROS 2 setup script not found: $rosSetup"
}

. $rosSetup

Push-Location "D:\SimWorld\ros2_ws"
try {
    . .\install\local_setup.ps1

    $pythonExe = if ($env:PYTHON_EXE) {
        $env:PYTHON_EXE
    } elseif (Test-Path "C:\pixi_ws\ros2-windows\python.exe") {
        "C:\pixi_ws\ros2-windows\python.exe"
    } else {
        (Get-Command python).Source
    }
    $logDir = Join-Path $env:TEMP "simworld_chase_ready"
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    Remove-Item -Path (Join-Path $logDir "*.log") -Force -ErrorAction SilentlyContinue

    $bridgeLog = Join-Path $logDir "ue_bridge.out.log"
    $bridgeErr = Join-Path $logDir "ue_bridge.err.log"
    $targetLog = Join-Path $logDir "target_brain.out.log"
    $targetErr = Join-Path $logDir "target_brain.err.log"
    $chaserLog = Join-Path $logDir "chaser_brain.out.log"
    $chaserErr = Join-Path $logDir "chaser_brain.err.log"

    $bridge = Start-Process -FilePath $pythonExe -ArgumentList "-m", "simworld_drone_ros.ue_bridge" -RedirectStandardOutput $bridgeLog -RedirectStandardError $bridgeErr -PassThru
    Start-Sleep -Seconds 2
    $target = Start-Process -FilePath $pythonExe -ArgumentList "-m", "simworld_drone_ros.target_brain" -RedirectStandardOutput $targetLog -RedirectStandardError $targetErr -PassThru
    $chaser = Start-Process -FilePath $pythonExe -ArgumentList "-m", "simworld_drone_ros.chaser_brain" -RedirectStandardOutput $chaserLog -RedirectStandardError $chaserErr -PassThru

    $deadline = (Get-Date).AddSeconds(15)
    $bridgeReady = $false
    $targetReady = $false
    $chaserReady = $false

    while ((Get-Date) -lt $deadline) {
        if (Test-Path $bridgeLog) {
            $bridgeText = Get-Content -Path $bridgeLog -Raw
            if ($bridgeText -match "UE bridge ready") { $bridgeReady = $true }
        }
        if (Test-Path $targetLog) {
            $targetText = Get-Content -Path $targetLog -Raw
            if ($targetText -match "Target brain ready") { $targetReady = $true }
        }
        if (Test-Path $chaserLog) {
            $chaserText = Get-Content -Path $chaserLog -Raw
            if ($chaserText -match "Chaser brain ready") { $chaserReady = $true }
        }
        if ($bridgeReady -and $targetReady -and $chaserReady) { break }
        Start-Sleep -Milliseconds 250
    }

    Write-Host "UnrealCV / Bridge: $(if ($bridgeReady) { 'OK' } else { 'NOT READY' })"
    Write-Host "Target Brain:      $(if ($targetReady) { 'OK' } else { 'NOT READY' })"
    Write-Host "Chaser Brain:      $(if ($chaserReady) { 'OK' } else { 'NOT READY' })"

    if ($bridgeReady -and $targetReady -and $chaserReady) {
        Write-Host "System ready to run chase."
    } else {
        Write-Host "System not ready. Recent logs:"
        if (Test-Path $bridgeLog) { Write-Host "`n--- ue_bridge.out.log ---"; Get-Content $bridgeLog | Select-Object -Last 20 }
        if (Test-Path $bridgeErr) { Write-Host "`n--- ue_bridge.err.log ---"; Get-Content $bridgeErr | Select-Object -Last 20 }
        if (Test-Path $targetLog) { Write-Host "`n--- target_brain.out.log ---"; Get-Content $targetLog | Select-Object -Last 20 }
        if (Test-Path $targetErr) { Write-Host "`n--- target_brain.err.log ---"; Get-Content $targetErr | Select-Object -Last 20 }
        if (Test-Path $chaserLog) { Write-Host "`n--- chaser_brain.out.log ---"; Get-Content $chaserLog | Select-Object -Last 20 }
        if (Test-Path $chaserErr) { Write-Host "`n--- chaser_brain.err.log ---"; Get-Content $chaserErr | Select-Object -Last 20 }
        exit 1
    }
} finally {
    foreach ($proc in @($bridge, $target, $chaser)) {
        if ($proc -and -not $proc.HasExited) {
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
    }
    Pop-Location
}
