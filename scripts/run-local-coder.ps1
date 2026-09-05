param(
    [string]$Task = "all",
    [ValidateRange(1, 3)][int]$Rounds = 2
)
$ErrorActionPreference = "Stop"
$python = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python runtime missing. Install Python 3.13 or update the launcher path."
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker Desktop is required for isolated tests."
}
$models = Invoke-RestMethod "http://127.0.0.1:11434/api/tags" -TimeoutSec 10
if ($models.models.name -notcontains "qwen3.8:latest") {
    throw "Ollama does not have qwen3.8:latest."
}
& docker image inspect hermes-delivery-qc-checker:shadow --format '{{.Id}}'
if ($LASTEXITCODE -ne 0) { throw "Build the QC test image before starting local coding." }
& $python (Join-Path $PSScriptRoot "local_coder.py") --task $Task --rounds $Rounds
exit $LASTEXITCODE
