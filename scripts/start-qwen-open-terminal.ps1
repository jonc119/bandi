[CmdletBinding()]
param(
    [string]$WorkspacePath = "$env:USERPROFILE\AI\bandi-qwen"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$secretPath = Join-Path $projectRoot "var\secrets\qwen_open_terminal_api_key"
$containerName = "bandi-qwen-terminal"
$networkName = "bandi-qwen-terminal-net"

if (-not (Test-Path -LiteralPath $WorkspacePath)) {
    throw "Qwen workspace is missing: $WorkspacePath"
}
if (docker container inspect $containerName 2>$null) {
    throw "Terminal container already exists: $containerName"
}

if (-not (Test-Path -LiteralPath $secretPath)) {
    $secretDirectory = Split-Path -Parent $secretPath
    New-Item -ItemType Directory -Force -Path $secretDirectory | Out-Null
    $randomBytes = [System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
    [Convert]::ToBase64String($randomBytes) | Set-Content -LiteralPath $secretPath -NoNewline
}

$apiKey = Get-Content -LiteralPath $secretPath -Raw
if (-not (docker network inspect $networkName 2>$null)) {
    docker network create --internal --attachable $networkName | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Qwen terminal network creation failed." }
}

$openWebUiNetworks = (docker inspect open-webui --format '{{json .NetworkSettings.Networks}}' | ConvertFrom-Json).PSObject.Properties.Name
if ($openWebUiNetworks -notcontains $networkName) {
    docker network connect $networkName open-webui
    if ($LASTEXITCODE -ne 0) { throw "Open WebUI could not join the Qwen terminal network." }
}

docker pull ghcr.io/open-webui/open-terminal
if ($LASTEXITCODE -ne 0) { throw "Open Terminal image pull failed." }

docker run -d --name $containerName --restart unless-stopped --network $networkName --network-alias $containerName --memory 4g --cpus 6 --pids-limit 256 --cap-drop ALL --security-opt no-new-privileges:true --volume "${WorkspacePath}:/home/user" --env "OPEN_TERMINAL_API_KEY=$apiKey" ghcr.io/open-webui/open-terminal
if ($LASTEXITCODE -ne 0) { throw "Open Terminal container failed to start." }

Write-Output "Open Terminal started for the isolated Qwen workspace."
