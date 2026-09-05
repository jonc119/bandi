param(
    [Parameter(Mandatory = $true)]
    [string]$DeliveryDate,
    [Parameter(Mandatory = $true)]
    [string]$IcsPath,
    [string]$StatusesPath
)

$workspace = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$env:PYTHONPATH = Join-Path $workspace "src"
$arguments = @(
    "-m", "delivery_qc",
    "--workspace", $workspace,
    "--config", (Join-Path $workspace "config\qc.toml"),
    "run", "--date", $DeliveryDate,
    "--ics", $IcsPath
)
if ($StatusesPath) {
    $arguments += @("--statuses", $StatusesPath)
}
& py @arguments
exit $LASTEXITCODE
