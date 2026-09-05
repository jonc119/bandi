param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$profileSource = Join-Path $projectRoot "config\qwen.config.toml.example"
$codexRoot = Join-Path $env:USERPROFILE ".codex"
$profileTarget = Join-Path $codexRoot "qwen.config.toml"

if (-not (Test-Path -LiteralPath $profileSource)) {
    throw "Qwen profile template is missing."
}

New-Item -ItemType Directory -Path $codexRoot -Force | Out-Null
if (Test-Path -LiteralPath $profileTarget) {
    throw "Refusing to overwrite existing Codex profile: $profileTarget"
}

Copy-Item -LiteralPath $profileSource -Destination $profileTarget
Write-Host "Installed Codex profile: $profileTarget"
