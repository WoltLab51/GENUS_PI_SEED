param(
    [Parameter(Mandatory = $true)]
    [string]$HostName,

    [string]$RepoDir = "",
    [string]$DbPath = "",
    [string]$AnchorDir = "",
    [string]$StatusRepoDir = "",
    [string]$StatusRepoUrl = "git@github-genus-pi-status:WoltLab51/GENUS_PI_STATUS.git",
    [string]$CoreId = "",
    [string]$Branch = "main",

    [switch]$SkipTests,
    [switch]$SkipAnchor,
    [switch]$InstallCron,
    [switch]$EnableStatusPublish
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

$envParts = @("GENUS_DEPLOY_BRANCH=$(Quote-Bash $Branch)")

if ($DbPath.Trim().Length -gt 0) {
    $envParts += "GENUS_DB_PATH=$(Quote-Bash $DbPath)"
}
if ($AnchorDir.Trim().Length -gt 0) {
    $envParts += "GENUS_ANCHOR_DIR=$(Quote-Bash $AnchorDir)"
}
if ($StatusRepoDir.Trim().Length -gt 0) {
    $envParts += "GENUS_STATUS_REPO_DIR=$(Quote-Bash $StatusRepoDir)"
}
if ($StatusRepoUrl.Trim().Length -gt 0) {
    $envParts += "GENUS_STATUS_REPO_URL=$(Quote-Bash $StatusRepoUrl)"
}

if ($CoreId.Trim().Length -gt 0) {
    $envParts += "GENUS_CORE_ID=$(Quote-Bash $CoreId)"
}
if ($SkipTests) {
    $envParts += "GENUS_DEPLOY_SKIP_TESTS=1"
}
if ($SkipAnchor) {
    $envParts += "GENUS_DEPLOY_SKIP_ANCHOR=1"
}
if ($EnableStatusPublish) {
    $envParts += "GENUS_ENABLE_STATUS_PUBLISH=1"
}

$envPrefix = $envParts -join " "
$remoteCommand = "cd $remoteRepoDir && $envPrefix ./deploy/pi_deploy.sh"
if ($InstallCron) {
    $remoteCommand += " && $envPrefix ./deploy/pi_install_cron.sh"
    if ($EnableStatusPublish) {
        $remoteCommand += " && $envPrefix ./deploy/pi_publish_status.sh"
    }
}

Write-Host "[DEPLOY] ssh $HostName"
ssh $HostName $remoteCommand
if ($LASTEXITCODE -ne 0) {
    throw "Remote deploy failed with exit code $LASTEXITCODE"
}
