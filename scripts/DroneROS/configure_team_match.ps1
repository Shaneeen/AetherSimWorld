param(
    [string]$OutputCmd = "",
    [int]$DefaultTeamSize = 2,
    [int]$MaxTeamSize = 5
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

function Clamp-Int {
    param([object]$Value, [int]$Min, [int]$Max, [int]$Fallback)
    try {
        $number = [int][double]$Value
    } catch {
        return $Fallback
    }
    if ($number -lt $Min) { return $Min }
    if ($number -gt $Max) { return $Max }
    return $number
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

function Read-TeamSize {
    param([string]$Team, [int]$Default)
    $inputValue = Read-Host "[team setup] $Team drones [$Default]"
    if ([string]::IsNullOrWhiteSpace($inputValue)) {
        return $Default
    }
    return Clamp-Int $inputValue 1 $MaxTeamSize $Default
}

function Current-TeamSpeeds {
    param([string]$Team)
    if ($Team -eq "red") {
        return @{
            cruise = [double](Get-EnvValue "SIM_RED_CRUISE_SPEED" "235")
            evade = [double](Get-EnvValue "SIM_RED_EVADE_SPEED" "285")
            burst = [double](Get-EnvValue "SIM_RED_BURST_SPEED" "365")
        }
    }
    return @{
        base = [double](Get-EnvValue "SIM_BLUE_BASE_SPEED" "250")
        intercept = [double](Get-EnvValue "SIM_BLUE_INTERCEPT_SPEED" "285")
        search = [double](Get-EnvValue "SIM_BLUE_SEARCH_SPEED" "190")
    }
}

function Describe-TeamSpeeds {
    param([string]$Team, [hashtable]$Speeds)
    if ($Team -eq "red") {
        return "red cruise=$($Speeds.cruise) evade=$($Speeds.evade) burst=$($Speeds.burst) cm/s"
    }
    return "blue base=$($Speeds.base) intercept=$($Speeds.intercept) search=$($Speeds.search) cm/s"
}

function Normalize-TeamSpeeds {
    param([string]$Team, [object]$Proposal, [hashtable]$Current)
    if ($Team -eq "red") {
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

function Invoke-TeamSpeedAi {
    param(
        [string]$Team,
        [hashtable]$Current,
        [string]$ModelName,
        [int]$RedSize,
        [int]$BlueSize
    )

    $apiUrl = Get-EnvValue "OLLAMA_API_URL" "http://127.0.0.1:11434/api/generate"
    $model = Get-EnvValue "OLLAMA_MODEL" "gpt-oss:latest"
    $currentJson = $Current | ConvertTo-Json -Compress
    $prompt = @"
You tune drone team-vs-team simulation speeds in cm/s.
Return only compact JSON, no markdown.
Team to tune: $Team
User drone model/reference: $ModelName
Match size: red=$RedSize blue=$BlueSize
Current speeds: $currentJson
Goal: balanced red-vs-blue team competition. Use the model/reference only as inspiration for relative performance.
For red use keys: cruise, evade, burst.
For blue use keys: base, intercept, search.
Keep values plausible and close enough to current defaults that 2v2, 3v3, and 5v5 remain playable.
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

function Read-ManualTeamSpeeds {
    param([string]$Team, [hashtable]$Current)
    if ($Team -eq "red") {
        Write-Host "[team setup] Manual red speeds. Press Enter on any value to keep its current default."
        $cruiseInput = Read-Host "[team setup] Red cruise speed cm/s [$($Current.cruise)]"
        $evadeInput = Read-Host "[team setup] Red evade speed cm/s [$($Current.evade)]"
        $burstInput = Read-Host "[team setup] Red burst speed cm/s [$($Current.burst)]"
        $proposal = [pscustomobject]@{
            cruise = if ([string]::IsNullOrWhiteSpace($cruiseInput)) { $Current.cruise } else { $cruiseInput }
            evade = if ([string]::IsNullOrWhiteSpace($evadeInput)) { $Current.evade } else { $evadeInput }
            burst = if ([string]::IsNullOrWhiteSpace($burstInput)) { $Current.burst } else { $burstInput }
        }
        return Normalize-TeamSpeeds $Team $proposal $Current
    }

    Write-Host "[team setup] Manual blue speeds. Press Enter on any value to keep its current default."
    $baseInput = Read-Host "[team setup] Blue base speed cm/s [$($Current.base)]"
    $interceptInput = Read-Host "[team setup] Blue intercept speed cm/s [$($Current.intercept)]"
    $searchInput = Read-Host "[team setup] Blue search speed cm/s [$($Current.search)]"
    $proposal = [pscustomobject]@{
        base = if ([string]::IsNullOrWhiteSpace($baseInput)) { $Current.base } else { $baseInput }
        intercept = if ([string]::IsNullOrWhiteSpace($interceptInput)) { $Current.intercept } else { $interceptInput }
        search = if ([string]::IsNullOrWhiteSpace($searchInput)) { $Current.search } else { $searchInput }
    }
    return Normalize-TeamSpeeds $Team $proposal $Current
}

function Choose-TeamSpeeds {
    param([string]$Team, [int]$RedSize, [int]$BlueSize)
    $current = Current-TeamSpeeds $Team
    Write-Host ""
    Write-Host "[team setup] Current $Team default: $(Describe-TeamSpeeds $Team $current)"
    $answer = Read-Host "[team setup] $Team speeds: Enter=defaults, edit=manual, or type a drone model/reference"
    if ([string]::IsNullOrWhiteSpace($answer)) {
        return @{ speeds = $current; model = "default" }
    }

    $answer = $answer.Trim()
    if ($answer -ieq "edit") {
        $speeds = Read-ManualTeamSpeeds $Team $current
        $modelReference = "manual"
    } else {
        Write-Host "[team setup] Asking AI to tune $Team speeds using model/reference '$answer'..."
        try {
            $proposal = Invoke-TeamSpeedAi $Team $current $answer $RedSize $BlueSize
            $speeds = Normalize-TeamSpeeds $Team $proposal $current
            $modelReference = $answer
        } catch {
            Write-Host "[team setup] AI tuning failed: $($_.Exception.Message)"
            Write-Host "[team setup] Keeping $Team default speeds."
            return @{ speeds = $current; model = "default" }
        }
    }

    Write-Host "[team setup] Proposed: $(Describe-TeamSpeeds $Team $speeds)"
    $accept = Read-Host "[team setup] Use these $Team speeds? Press Enter/Y to accept, N to keep defaults"
    if ($accept -match "^[Nn]") {
        Write-Host "[team setup] Keeping $Team default speeds."
        return @{ speeds = $current; model = "default" }
    }

    return @{ speeds = $speeds; model = $modelReference }
}

function Read-RoundMode {
    Write-Host ""
    Write-Host "[team setup] Round rules:"
    Write-Host "[team setup]   1 = tag: normal primary catch scoring"
    Write-Host "[team setup]   2 = elimination: caught red drones drop to the ground until all red drones are caught, then reset"
    $answer = Read-Host "[team setup] Round rule [1]"
    if ($answer -match "^[2Ee]") {
        return "red_elimination"
    }
    return "tag"
}

function Escape-CmdValue {
    param([string]$Value)
    return ($Value -replace '"', '')
}

function Write-TeamMatchCmd {
    param(
        [string]$Path,
        [int]$RedSize,
        [int]$BlueSize,
        [string]$RoundMode,
        [hashtable]$RedProfile,
        [hashtable]$BlueProfile
    )
    if ([string]::IsNullOrWhiteSpace($Path)) {
        return
    }
    $redSpeeds = $RedProfile.speeds
    $blueSpeeds = $BlueProfile.speeds
    $redModel = Escape-CmdValue ([string]$RedProfile.model)
    $blueModel = Escape-CmdValue ([string]$BlueProfile.model)
    @(
        "set `"SIM_TEAM_MATCH_CONFIGURED=1`""
        "set `"SIM_RED_TEAM_SIZE=$RedSize`""
        "set `"SIM_BLUE_TEAM_SIZE=$BlueSize`""
        "set `"SIM_TEAM_ROUND_MODE=$RoundMode`""
        "set `"SIM_RED_MODEL_REFERENCE=$redModel`""
        "set `"SIM_BLUE_MODEL_REFERENCE=$blueModel`""
        "set `"SIM_RED_CRUISE_SPEED=$($redSpeeds.cruise)`""
        "set `"SIM_RED_EVADE_SPEED=$($redSpeeds.evade)`""
        "set `"SIM_RED_BURST_SPEED=$($redSpeeds.burst)`""
        "set `"SIM_BLUE_BASE_SPEED=$($blueSpeeds.base)`""
        "set `"SIM_BLUE_INTERCEPT_SPEED=$($blueSpeeds.intercept)`""
        "set `"SIM_BLUE_SEARCH_SPEED=$($blueSpeeds.search)`""
    ) | Set-Content -Path $Path -Encoding ASCII
}

Write-Host ""
Write-Host "[team setup] Team match setup. Press Enter for default 2v2."
$redSize = Read-TeamSize "Red" (Clamp-Int $DefaultTeamSize 1 $MaxTeamSize 2)
$blueSize = Read-TeamSize "Blue" $redSize
$roundMode = Read-RoundMode

$redProfile = Choose-TeamSpeeds "red" $redSize $blueSize
$blueProfile = Choose-TeamSpeeds "blue" $redSize $blueSize

Write-Host ""
Write-Host "[team setup] Summary:"
Write-Host "[team setup] Red drones: $redSize"
Write-Host "[team setup] Blue drones: $blueSize"
Write-Host "[team setup] Round mode: $roundMode"
Write-Host "[team setup] Red speeds: $(Describe-TeamSpeeds 'red' $redProfile.speeds) model=$($redProfile.model)"
Write-Host "[team setup] Blue speeds: $(Describe-TeamSpeeds 'blue' $blueProfile.speeds) model=$($blueProfile.model)"
$confirm = Read-Host "[team setup] Write this team config? Press Enter/Y to accept, N to cancel"
if ($confirm -match "^[Nn]") {
    Write-Host "[team setup] Team config cancelled."
    exit 0
}

Write-TeamMatchCmd $OutputCmd $redSize $blueSize $roundMode $redProfile $blueProfile
Write-Host "[team setup] Team config accepted."
