param(
    [switch]$Set5v5,
    [switch]$StopFirst,
    [switch]$Vision,
    [switch]$ImageVision,
    [string]$Observer = "blue_1",
    [switch]$NoPanel,
    [switch]$NoStart,
    [switch]$NoWatch,
    [switch]$Manual,
    [switch]$DryRun,
    [switch]$Tabs,
    [int]$BridgeDelaySec = 6,
    [int]$BrainDelaySec = 3,
    [int]$PanelDelaySec = 2,
    [int]$VisionDelaySec = 2,
    [int]$StartDelaySec = 3
)

$ErrorActionPreference = "Stop"

$LaunchDir = Split-Path -Parent $PSCommandPath
$RootDir = Split-Path -Parent $LaunchDir

function Invoke-SetupStep {
    param(
        [string]$Name,
        [string]$ScriptPath
    )

    Write-Host "[$Name] running $ScriptPath"
    if ($DryRun) {
        Write-Host "[$Name] dry run: skipped"
        return
    }
    & $ScriptPath
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

function Wait-ForStage {
    param(
        [string]$Title,
        [int]$DelaySec
    )

    if ($DryRun) {
        return
    }

    if ($Manual) {
        Read-Host "Press Enter after '$Title' is ready"
        return
    }

    if ($DelaySec -gt 0) {
        Write-Host "Waiting $DelaySec seconds for '$Title' to start..."
        Start-Sleep -Seconds $DelaySec
    }
}

function Start-LaunchWindow {
    param(
        [string]$Title,
        [string]$Command,
        [int]$DelaySec
    )

    $mode = if ($Tabs) { "tab" } else { "window" }
    Write-Host "Starting '$Title' in a $mode`: $Command"
    $cmdLine = "title $Title && cd /d `"$RootDir`" && $Command"
    if ($DryRun) {
        if ($Tabs) {
            Write-Host "Dry run command: wt.exe -w 0 new-tab --title `"$Title`" --startingDirectory `"$RootDir`" cmd /k `"$Command`""
        } else {
            Write-Host "Dry run command: %ComSpec% /k $cmdLine"
        }
        return
    }
    if ($Tabs) {
        $wt = Get-Command wt.exe -ErrorAction SilentlyContinue
        if (-not $wt) {
            throw "Windows Terminal (wt.exe) was not found. Run without -Tabs to use separate cmd windows."
        }
        $escapedTitle = $Title.Replace('"', '\"')
        $escapedRoot = $RootDir.Replace('"', '\"')
        $escapedCommand = $Command.Replace('"', '\"')
        $wtArgs = "-w 0 new-tab --title `"$escapedTitle`" --startingDirectory `"$escapedRoot`" cmd /k `"$escapedCommand`""
        Start-Process -FilePath $wt.Source -ArgumentList $wtArgs
    } else {
        Start-Process -FilePath $env:ComSpec -ArgumentList "/k", $cmdLine
    }
    Wait-ForStage -Title $Title -DelaySec $DelaySec
}

Write-Host "[demo] AetherSimWorld staged launcher"
Write-Host "[demo] Root: $RootDir"
if ($DryRun) {
    Write-Host "[demo] Dry run: no windows or setup commands will be started."
}
if ($Tabs) {
    Write-Host "[demo] Tab mode: using Windows Terminal tabs instead of separate cmd windows."
}
Write-Host "[demo] Open Unreal and press Play before starting if UnrealCV/bridge access is needed."
Write-Host ""

if ($StopFirst) {
    Invoke-SetupStep -Name "stop" -ScriptPath (Join-Path $LaunchDir "stop.cmd")
}

if ($Set5v5) {
    Invoke-SetupStep -Name "set-5v5" -ScriptPath (Join-Path $LaunchDir "set_teams_5v5.cmd")
}

Start-LaunchWindow -Title "AetherSim bridge" -Command ".\launch\bridge.cmd" -DelaySec $BridgeDelaySec
Start-LaunchWindow -Title "AetherSim target brain" -Command ".\launch\target.cmd" -DelaySec $BrainDelaySec
Start-LaunchWindow -Title "AetherSim chaser brain" -Command ".\launch\chaser.cmd" -DelaySec $BrainDelaySec

if (-not $NoPanel) {
    Start-LaunchWindow -Title "AetherSim panel" -Command ".\launch\panel.cmd" -DelaySec $PanelDelaySec
}

if ($Vision -or $ImageVision) {
    $visionCommand = ".\launch\vision.cmd $Observer"
    if ($ImageVision) {
        $visionCommand = ".\launch\vision.cmd $Observer --image"
    }
    Start-LaunchWindow -Title "AetherSim vision $Observer" -Command $visionCommand -DelaySec $VisionDelaySec
}

if (-not $NoStart) {
    Wait-ForStage -Title "all runtime windows before chase start" -DelaySec $StartDelaySec
    $startCommand = ".\launch\start.cmd"
    if ($NoWatch) {
        $startCommand = ".\launch\start.cmd --no-watch"
    }
    Start-LaunchWindow -Title "AetherSim start watch" -Command $startCommand -DelaySec 0
}

Write-Host ""
Write-Host "[demo] Done launching staged windows."
Write-Host "[demo] Stop everything with: .\launch\stop.cmd"
Write-Host "[demo] New round only:       .\launch\new_round.cmd"
