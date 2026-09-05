[CmdletBinding()]
param(
    [string]$WorkspacePath = "$env:USERPROFILE\AI\bandi-qwen"
)

$ErrorActionPreference = "Stop"
$expectedBranch = "qwen/agent"
$expectedRemote = "https://github.com/jonc119/bandi.git"

if (-not (Test-Path -LiteralPath (Join-Path $WorkspacePath ".git"))) {
    throw "Qwen workspace is not a Git repository: $WorkspacePath"
}

$branch = (& git -C $WorkspacePath branch --show-current).Trim()
if ($branch -ne $expectedBranch) {
    throw "Refusing to sync branch '$branch'; expected '$expectedBranch'."
}

$remote = (& git -C $WorkspacePath remote get-url origin).Trim()
if ($remote -ne $expectedRemote) {
    throw "Refusing to sync unexpected remote."
}

if ((& git -C $WorkspacePath status --porcelain)) {
    throw "Refusing to publish uncommitted work."
}

& git -C $WorkspacePath push origin "$expectedBranch`:$expectedBranch"
if ($LASTEXITCODE -ne 0) {
    throw "Qwen branch sync failed."
}

Write-Output "Synced $expectedBranch to GitHub."
