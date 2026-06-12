param(
    [Parameter(Mandatory = $true)]
    [string]$HostName,

    [string]$RepoDir = "/home/pi/GENUS_PI_SEED",
    [string]$DbPath = "/home/pi/.genus/genus.sqlite3",
    [string]$AnchorDir = "/home/pi/.genus/anchors",
    [string]$CoreId = "",
    [string]$Branch = "main",

    [switch]$SkipTests,
    [switch]$SkipAnchor
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Quote-Bash {
    param([Parameter(Mandatory = $true)][string]$Value)
    $single = [char]39
    $double = [char]34
    $escapedSingle = "$single$double$single$double$single"
    return "$single" + $Value.Replace("$single", $escapedSingle) + "$single"
}

$envParts = @(
    "GENUS_DEPLOY_BRANCH=$(Quote-Bash $Branch)",
    "GENUS_DB_PATH=$(Quote-Bash $DbPath)",
    "GENUS_ANCHOR_DIR=$(Quote-Bash $AnchorDir)"
)

if ($CoreId.Trim().Length -gt 0) {
    $envParts += "GENUS_CORE_ID=$(Quote-Bash $CoreId)"
}
if ($SkipTests) {
    $envParts += "GENUS_DEPLOY_SKIP_TESTS=1"
}
if ($SkipAnchor) {
    $envParts += "GENUS_DEPLOY_SKIP_ANCHOR=1"
}

$remoteCommand = "cd $(Quote-Bash $RepoDir) && " + ($envParts -join " ") + " ./deploy/pi_deploy.sh"

Write-Host "[DEPLOY] ssh $HostName"
ssh $HostName $remoteCommand
if ($LASTEXITCODE -ne 0) {
    throw "Remote deploy failed with exit code $LASTEXITCODE"
}
