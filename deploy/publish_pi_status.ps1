param(
    [Parameter(Mandatory = $true)]
    [string]$HostName,

    [string]$RepoDir = "",
    [string]$CoreId = "pi-core",
    [string]$StatusRepoUrl = "git@github-genus-pi-status:WoltLab51/GENUS_PI_STATUS.git"
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

$remoteRepoDir = '$HOME/GENUS_PI_SEED'
if ($RepoDir.Trim().Length -gt 0) {
    $remoteRepoDir = Quote-Bash $RepoDir
}

$remoteCommand = "cd $remoteRepoDir && GENUS_CORE_ID=$(Quote-Bash $CoreId) GENUS_STATUS_REPO_URL=$(Quote-Bash $StatusRepoUrl) ./deploy/pi_publish_status.sh"

Write-Host "[STATUS] ssh $HostName"
ssh $HostName $remoteCommand
if ($LASTEXITCODE -ne 0) {
    throw "Remote status publish failed with exit code $LASTEXITCODE"
}
