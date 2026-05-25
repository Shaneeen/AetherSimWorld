param(
    [ValidateSet("target", "chaser")]
    [string]$DefaultDrone = "target",
    [string]$OutputCmd = ""
)

$ErrorActionPreference = "Stop"

function Get-EnvValue {
    param([string]$Name, [string]$Fallback)
    $value = [Environment]::GetEnvironmentVariable($Name, "Process")
    if ([string]::IsNullOrWhiteSpace($value)) {
        return $Fallback
    }
    return $value
}

function Current-Speeds {
    param([string]$Drone)
    if ($Drone -eq "target") {
        return @{
            cruise = [double](Get-EnvValue "SIM_TARGET_CRUISE_SPEED" "220")
            evade = [double](Get-EnvValue "SIM_TARGET_EVADE_SPEED" "265")
            burst = [double](Get-EnvValue "SIM_TARGET_BURST_SPEED" "335")
        }
    }
    return @{
        base = [double](Get-EnvValue "SIM_CHASER_SPEED" "260")
        intercept = [double](Get-EnvValue "SIM_CHASER_INTERCEPT_SPEED" "300")
        search = [double](Get-EnvValue "SIM_CHASER_SEARCH_SPEED" "200")
    }
}

function Write-SpeedCmd {
    param([string]$Drone, [hashtable]$Speeds, [string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) {
        return
    }

    if ($Drone -eq "target") {
        @(
            "set SIM_TARGET_CRUISE_SPEED=$($Speeds.cruise)"
            "set SIM_TARGET_EVADE_SPEED=$($Speeds.evade)"
            "set SIM_TARGET_BURST_SPEED=$($Speeds.burst)"
        ) | Set-Content -Path $Path -Encoding ASCII
        return
    }

    @(
        "set SIM_CHASER_SPEED=$($Speeds.base)"
        "set SIM_CHASER_INTERCEPT_SPEED=$($Speeds.intercept)"
        "set SIM_CHASER_SEARCH_SPEED=$($Speeds.search)"
    ) | Set-Content -Path $Path -Encoding ASCII
}

function Clamp-Number {
    param([object]$Value, [double]$Min, [double]$Max, [double]$Fallback)
    try {
        $number = [double]$Value
    } catch {
        return $Fallback
    }
    if ($number -lt $Min) { return $Min }
    if ($number -gt $Max) { return $Max }
    return [math]::Round($number, 1)
}

function Invoke-SpeedAi {
    param([string]$Drone, [hashtable]$Current, [string]$ModelName)

    $apiUrl = Get-EnvValue "OLLAMA_API_URL" "http://127.0.0.1:11434/api/generate"
    $model = Get-EnvValue "OLLAMA_MODEL" "gpt-oss:latest"
    $currentJson = $Current | ConvertTo-Json -Compress
    $prompt = @"
You tune drone chase simulation speeds in cm/s.
Return only compact JSON, no markdown.
Drone to tune: $Drone
User drone model/reference: $ModelName
Current speeds: $currentJson
Goal: balanced competition where the target can escape with smart jukes and bursts, but the chaser can catch with good intercepts.
For target use keys: cruise, evade, burst.
For chaser use keys: base, intercept, search.
Use the model/reference only as inspiration for relative performance. Keep values plausible and close enough to the current defaults that the chase remains playable.
"@

    $body = @{
        model = $model
        prompt = $prompt
        stream = $false
        options = @{
            temperature = 0.2
            num_predict = 120
        }
    } | ConvertTo-Json -Depth 5

    $response = Invoke-RestMethod -Uri $apiUrl -Method Post -ContentType "application/json" -Body $body -TimeoutSec 20
    $text = [string]$response.response
    $jsonText = ([regex]::Match($text, "\{[\s\S]*\}")).Value
    if ([string]::IsNullOrWhiteSpace($jsonText)) {
        throw "AI did not return JSON speeds."
    }
    return $jsonText | ConvertFrom-Json
}

function Normalize-Speeds {
    param([string]$Drone, [object]$Proposal, [hashtable]$Current)

    if ($Drone -eq "target") {
        $cruise = Clamp-Number $Proposal.cruise 160 320 $Current.cruise
        $evade = Clamp-Number $Proposal.evade $cruise 380 $Current.evade
        $burst = Clamp-Number $Proposal.burst $evade 450 $Current.burst
        return @{ cruise = $cruise; evade = $evade; burst = $burst }
    }

    $search = Clamp-Number $Proposal.search 120 320 $Current.search
    $base = Clamp-Number $Proposal.base 180 360 $Current.base
    $intercept = Clamp-Number $Proposal.intercept $base 430 $Current.intercept
    return @{ base = $base; intercept = $intercept; search = $search }
}

function Describe-Speeds {
    param([string]$Drone, [hashtable]$Speeds)
    if ($Drone -eq "target") {
        return "target cruise=$($Speeds.cruise) evade=$($Speeds.evade) burst=$($Speeds.burst) cm/s"
    }
    return "chaser base=$($Speeds.base) intercept=$($Speeds.intercept) search=$($Speeds.search) cm/s"
}

function Read-ManualSpeeds {
    param([string]$Drone, [hashtable]$Current)

    if ($Drone -eq "target") {
        Write-Host "[speed setup] Manual target speeds. Press Enter on any value to keep its current default."
        $cruiseInput = Read-Host "[speed setup] Cruise speed cm/s [$($Current.cruise)]"
        $evadeInput = Read-Host "[speed setup] Evade speed cm/s [$($Current.evade)]"
        $burstInput = Read-Host "[speed setup] Burst speed cm/s [$($Current.burst)]"
        $proposal = [pscustomobject]@{
            cruise = if ([string]::IsNullOrWhiteSpace($cruiseInput)) { $Current.cruise } else { $cruiseInput }
            evade = if ([string]::IsNullOrWhiteSpace($evadeInput)) { $Current.evade } else { $evadeInput }
            burst = if ([string]::IsNullOrWhiteSpace($burstInput)) { $Current.burst } else { $burstInput }
        }
        return Normalize-Speeds $Drone $proposal $Current
    }

    Write-Host "[speed setup] Manual chaser speeds. Press Enter on any value to keep its current default."
    $baseInput = Read-Host "[speed setup] Base speed cm/s [$($Current.base)]"
    $interceptInput = Read-Host "[speed setup] Intercept speed cm/s [$($Current.intercept)]"
    $searchInput = Read-Host "[speed setup] Search speed cm/s [$($Current.search)]"
    $proposal = [pscustomobject]@{
        base = if ([string]::IsNullOrWhiteSpace($baseInput)) { $Current.base } else { $baseInput }
        intercept = if ([string]::IsNullOrWhiteSpace($interceptInput)) { $Current.intercept } else { $interceptInput }
        search = if ([string]::IsNullOrWhiteSpace($searchInput)) { $Current.search } else { $searchInput }
    }
    return Normalize-Speeds $Drone $proposal $Current
}

$current = Current-Speeds $DefaultDrone
Write-Host ""
Write-Host "[speed setup] Current default: $(Describe-Speeds $DefaultDrone $current)"
$answer = Read-Host "[speed setup] Press Enter for defaults, type edit for manual speeds, or type a drone model for AI tuning"
if ([string]::IsNullOrWhiteSpace($answer)) {
    Write-Host "[speed setup] Keeping default speeds."
    exit 0
}

$answer = $answer.Trim()
$current = Current-Speeds $DefaultDrone
if ($answer -ieq "edit") {
    $speeds = Read-ManualSpeeds $DefaultDrone $current
} else {
    Write-Host "[speed setup] Asking AI to tune $DefaultDrone speeds using model/reference '$answer'..."
    try {
        $proposal = Invoke-SpeedAi $DefaultDrone $current $answer
        $speeds = Normalize-Speeds $DefaultDrone $proposal $current
    } catch {
        Write-Host "[speed setup] AI tuning failed: $($_.Exception.Message)"
        Write-Host "[speed setup] Keeping default speeds."
        exit 0
    }
}

Write-Host "[speed setup] Proposed: $(Describe-Speeds $DefaultDrone $speeds)"
$accept = Read-Host "[speed setup] Use these speeds? Press Enter/Y to accept, N to keep defaults"
if ($accept -match "^[Nn]") {
    Write-Host "[speed setup] Keeping default speeds."
    exit 0
}

Write-SpeedCmd $DefaultDrone $speeds $OutputCmd
Write-Host "[speed setup] Accepted $(Describe-Speeds $DefaultDrone $speeds)."
