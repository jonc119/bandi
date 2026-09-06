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
docker container inspect $containerName 1>$null 2>$null
if ($LASTEXITCODE -eq 0) {
    throw "Terminal container already exists: $containerName"
}

if (-not (Test-Path -LiteralPath $secretPath)) {
    $secretDirectory = Split-Path -Parent $secretPath
    New-Item -ItemType Directory -Force -Path $secretDirectory | Out-Null
    $randomBytes = [System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
    [Convert]::ToBase64String($randomBytes) | Set-Content -LiteralPath $secretPath -NoNewline
}

$apiKey = Get-Content -LiteralPath $secretPath -Raw
docker network inspect $networkName 1>$null 2>$null
if ($LASTEXITCODE -ne 0) {
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

docker run -d --name $containerName --restart unless-stopped --network $networkName --network-alias $containerName --memory 4g --cpus 6 --pids-limit 256 --security-opt no-new-privileges:true --volume "${WorkspacePath}:/home/user" --env "OPEN_TERMINAL_API_KEY=$apiKey" ghcr.io/open-webui/open-terminal
if ($LASTEXITCODE -ne 0) { throw "Open Terminal container failed to start." }

docker exec $containerName git config --global --add safe.directory /home/user
if ($LASTEXITCODE -ne 0) { throw "Qwen terminal Git workspace initialization failed." }
docker exec $containerName git -C /home/user config core.autocrlf true
if ($LASTEXITCODE -ne 0) { throw "Qwen terminal line-ending initialization failed." }
docker exec $containerName sh -lc "printf '%s\n' '.bashrc' '.profile' '.gitconfig' '.local/' >> /home/user/.git/info/exclude"
if ($LASTEXITCODE -ne 0) { throw "Qwen terminal Git exclude initialization failed." }

Write-Output "Open Terminal started for the isolated Qwen workspace."
