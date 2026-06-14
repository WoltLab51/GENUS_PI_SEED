param(
    [Parameter(Mandatory = $true)]
    [string]$HostName,

    [string]$CoreId = "pi-core",
    [string]$HostAlias = "github-genus-pi-status",
    [string]$KeyPath = "~/.ssh/genus_pi_status_ed25519",
    [string]$Repository = "WoltLab51/GENUS_PI_STATUS"
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

$keyPathQuoted = Quote-Bash $KeyPath
$coreIdQuoted = Quote-Bash $CoreId
$hostAliasQuoted = Quote-Bash $HostAlias

$remoteScript = @"
set -Eeuo pipefail
KEY_PATH=$keyPathQuoted
CORE_ID=$coreIdQuoted
HOST_ALIAS=$hostAliasQuoted

mkdir -p ~/.ssh
chmod 700 ~/.ssh

case "`$KEY_PATH" in
    "~/"*) KEY_PATH="`$HOME/`${KEY_PATH:2}" ;;
esac
mkdir -p "`$(dirname -- "`$KEY_PATH")"

if [ ! -f "`$KEY_PATH" ]; then
    ssh-keygen -q -t ed25519 -f "`$KEY_PATH" -N "" -C "genus-pi-status@`$CORE_ID"
fi

chmod 600 "`$KEY_PATH"
chmod 644 "`$KEY_PATH.pub"
touch ~/.ssh/config
chmod 600 ~/.ssh/config

if ! grep -q "^Host `$HOST_ALIAS`$" ~/.ssh/config; then
    cat >> ~/.ssh/config <<EOF

Host `$HOST_ALIAS
  HostName github.com
  User git
  IdentityFile `$KEY_PATH
  IdentitiesOnly yes
EOF
fi

if command -v ssh-keyscan >/dev/null 2>&1; then
    ssh-keyscan -t ed25519 github.com >> ~/.ssh/known_hosts 2>/dev/null || true
    sort -u ~/.ssh/known_hosts -o ~/.ssh/known_hosts 2>/dev/null || true
fi

cat "`$KEY_PATH.pub"
"@

Write-Host "[STATUS-KEY] preparing SSH key on $HostName"
$publicKey = $remoteScript | ssh $HostName bash -s
if ($LASTEXITCODE -ne 0) {
    throw "Remote key setup failed with exit code $LASTEXITCODE"
}

Write-Host ""
Write-Host "[STATUS-KEY] Add this deploy key in GitHub:"
Write-Host "Repository: $Repository"
Write-Host "Settings -> Deploy keys -> Add deploy key"
Write-Host "Title: $CoreId status publisher"
Write-Host "Allow write access: checked"
Write-Host ""
Write-Host $publicKey
Write-Host ""
Write-Host "[STATUS-KEY] After adding it, publish with:"
Write-Host ".\deploy\publish_pi_status.ps1 -HostName $HostName -CoreId $CoreId"
