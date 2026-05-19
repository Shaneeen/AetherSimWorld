param(
    [double]$TargetSpeed = 220,
    [double]$MoveSec = 3,
    [double]$RestSec = 5,
    [double]$ChaserSpeed = 260,
    [double]$CatchDistance = 120,
    [string]$OllamaBaseUrl = "http://10.8.0.132:11434",
    [string]$OllamaModel = "gpt-oss:latest"
)

$ErrorActionPreference = "Stop"

$env:SIMWORLD_HOST = if ($env:SIMWORLD_HOST) { $env:SIMWORLD_HOST } else { "127.0.0.1" }
$env:SIMWORLD_PORT = if ($env:SIMWORLD_PORT) { $env:SIMWORLD_PORT } else { "9000" }
$env:SIM_TARGET_SPEED = "$TargetSpeed"
$env:SIM_TARGET_CRUISE_SPEED = "$TargetSpeed"
$env:SIM_TARGET_EVADE_SPEED = "$($TargetSpeed + 45)"
$env:SIM_TARGET_BURST_SPEED = "$($TargetSpeed + 115)"
$env:SIM_TARGET_MOVE_SEC = "$MoveSec"
$env:SIM_TARGET_REST_SEC = "$RestSec"
$env:SIM_CHASER_SPEED = "$ChaserSpeed"
$env:SIM_CATCH_DISTANCE = "$CatchDistance"

$ollamaRoot = $OllamaBaseUrl.TrimEnd("/")
$ollamaGenerateUrl = "$ollamaRoot/api/generate"
$env:USE_OLLAMA = "1"
$env:OLLAMA_MODEL = $OllamaModel
$env:SIM_TARGET_OLLAMA_MODEL = $OllamaModel
$env:SIM_CHASER_OLLAMA_MODEL = $OllamaModel
$env:OLLAMA_API_URL = $ollamaGenerateUrl
$env:OLLAMA_API_URLS = $ollamaGenerateUrl
$env:SIM_TARGET_OLLAMA_API_URL = $ollamaGenerateUrl
$env:SIM_CHASER_OLLAMA_API_URL = $ollamaGenerateUrl
$env:OLLAMA_OPENAI_URL = "$ollamaRoot/v1"
$env:OLLAMA_TIMEOUT_SEC = "20"
$env:SIM_TARGET_OLLAMA_NUM_PREDICT = "512"
$env:SIM_CHASER_OLLAMA_NUM_PREDICT = "512"
$env:SIM_LOS_ENABLED = "1"
$env:SIM_TARGET_FAKE_OCCLUSION_PROB = "0"
$env:SIM_CHASER_FAKE_OCCLUSION_PROB = "0"
$env:PYTHONPATH = "D:\SimWorld;" + $env:PYTHONPATH

$rosSetup = if ($env:ROS_SETUP_PS1) { $env:ROS_SETUP_PS1 } else { "C:\pixi_ws\ros2-windows\local_setup.ps1" }
if (-not (Test-Path $rosSetup)) {
    throw "ROS 2 setup script not found: $rosSetup"
}

. $rosSetup

Push-Location "D:\SimWorld\ros2_ws"
try {
    . .\install\local_setup.ps1

    $logDir = Join-Path $env:TEMP "simworld_chase_arm"
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    Remove-Item -Path (Join-Path $logDir "*.log") -Force -ErrorAction SilentlyContinue

    $targetLog = Join-Path $logDir "target_brain.out.log"
    $targetErr = Join-Path $logDir "target_brain.err.log"
    $chaserLog = Join-Path $logDir "chaser_brain.out.log"
    $chaserErr = Join-Path $logDir "chaser_brain.err.log"

    $target = Start-Process -FilePath "ros2" -ArgumentList "run", "simworld_drone_ros", "target_brain" -RedirectStandardOutput $targetLog -RedirectStandardError $targetErr -PassThru
    $chaser = Start-Process -FilePath "ros2" -ArgumentList "run", "simworld_drone_ros", "chaser_brain" -RedirectStandardOutput $chaserLog -RedirectStandardError $chaserErr -PassThru

    $deadline = (Get-Date).AddSeconds(15)
    $targetReady = $false
    $chaserReady = $false

    while ((Get-Date) -lt $deadline) {
        if (Test-Path $targetLog) {
            $targetText = Get-Content -Path $targetLog -Raw
            if ($targetText -match "Target brain ready") { $targetReady = $true }
        }
        if (Test-Path $chaserLog) {
            $chaserText = Get-Content -Path $chaserLog -Raw
            if ($chaserText -match "Chaser brain ready") { $chaserReady = $true }
        }
        if ($targetReady -and $chaserReady) { break }
        Start-Sleep -Milliseconds 250
    }

    Write-Host "Target Brain: $(if ($targetReady) { 'OK' } else { 'NOT READY' })"
    Write-Host "Chaser Brain: $(if ($chaserReady) { 'OK' } else { 'NOT READY' })"
    Write-Host "Ollama model: $env:OLLAMA_MODEL"
    Write-Host "Ollama API: $env:OLLAMA_API_URL"

    if (-not ($targetReady -and $chaserReady)) {
        Write-Host "Brains failed readiness check. Recent logs:"
        if (Test-Path $targetLog) { Write-Host "`n--- target_brain.out.log ---"; Get-Content $targetLog | Select-Object -Last 20 }
        if (Test-Path $targetErr) { Write-Host "`n--- target_brain.err.log ---"; Get-Content $targetErr | Select-Object -Last 20 }
        if (Test-Path $chaserLog) { Write-Host "`n--- chaser_brain.out.log ---"; Get-Content $chaserLog | Select-Object -Last 20 }
        if (Test-Path $chaserErr) { Write-Host "`n--- chaser_brain.err.log ---"; Get-Content $chaserErr | Select-Object -Last 20 }
        exit 1
    }

    Write-Host "Brains armed and waiting for START."
    Write-Host "Target PID: $($target.Id)"
    Write-Host "Chaser PID: $($chaser.Id)"
    Write-Host "Leave this window open. Use Terminal 3 to fire the start command."

    while ($true) {
        Start-Sleep -Seconds 2
        if ($target.HasExited -or $chaser.HasExited) {
            throw "One of the brain processes exited unexpectedly."
        }
    }
} finally {
    foreach ($proc in @($target, $chaser)) {
        if ($proc -and -not $proc.HasExited) {
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
    }
    Pop-Location
}
