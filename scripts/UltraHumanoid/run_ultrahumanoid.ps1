$env:SIMWORLD_EXE = "D:\Windows\Windows\SimWorld.exe"
$env:SIMWORLD_MAP_PATH = "/Game/Maps/empty.umap"
$env:SIMWORLD_AUTO_LAUNCH = "1"
$env:SIMWORLD_CONFIG = "config/light.yaml"
$env:SIMWORLD_GENERATE_WORLD = "1"
$env:USE_OLLAMA = "1"
$env:OLLAMA_MODEL = if ($env:OLLAMA_MODEL) { $env:OLLAMA_MODEL } else { "phi3" }

function Test-TcpPort {
    param(
        [string]$HostName,
        [int]$Port
    )
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $iar = $client.BeginConnect($HostName, $Port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne(1000, $false)
        if (-not $ok) {
            $client.Close()
            return $false
        }
        $client.EndConnect($iar)
        $client.Close()
        return $true
    } catch {
        return $false
    }
}

if (-not (Test-TcpPort -HostName "127.0.0.1" -Port 11434)) {
    Write-Host "Ollama is not running on 127.0.0.1:11434. Starting ollama serve..."
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        if (Test-TcpPort -HostName "127.0.0.1" -Port 11434) {
            $ready = $true
            break
        }
    }
    if (-not $ready) {
        throw "Ollama did not start on 127.0.0.1:11434"
    }
}

$preferredPython = "C:\Users\popla\miniconda3\envs\simworld\python.exe"
$pythonExe = if (Test-Path $preferredPython) {
    $preferredPython
} elseif ($env:CONDA_PREFIX) {
    Join-Path $env:CONDA_PREFIX "python.exe"
} else {
    "python"
}

& $pythonExe .\scripts\UltraHumanoid\main.py
