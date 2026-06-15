param(
    [Parameter(Mandatory = $true)]
    [string]$HostName,

    [string]$RepoDir = "",
    [string]$CoreId = "pi-core"
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

$remoteCommand = "cd $remoteRepoDir && GENUS_CORE_ID=$(Quote-Bash $CoreId) ./deploy/pi_install_network_watchdog.sh"

Write-Host "[WATCHDOG] ssh $HostName"
ssh -t $HostName $remoteCommand
if ($LASTEXITCODE -ne 0) {
    throw "Remote network watchdog install failed with exit code $LASTEXITCODE"
}
