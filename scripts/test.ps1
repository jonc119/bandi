$workspace = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$env:PYTHONPATH = Join-Path $workspace "src"
Push-Location $workspace
try {
    & py -m unittest discover -s tests -v
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
