[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$secretDirectory = Join-Path $projectRoot "var\secrets"
$webUiSecretPath = Join-Path $secretDirectory "open_webui_secret_key"
$terminalSecretPath = Join-Path $secretDirectory "qwen_open_terminal_api_key"
$containerName = "open-webui"
$terminalContainerName = "bandi-qwen-terminal"
$terminalNetworkName = "bandi-qwen-terminal-net"

function Get-ContainerEnvironmentValue {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Environment,
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $prefix = "$Name="
    $entry = $Environment | Where-Object { $_.StartsWith($prefix, [System.StringComparison]::Ordinal) } | Select-Object -First 1
    if ($null -eq $entry) {
        return $null
    }
    return $entry.Substring($prefix.Length)
}

function Restore-PreviousOpenWebUi {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ArchiveName
    )

    docker container inspect $ArchiveName 1>$null 2>$null
    if ($LASTEXITCODE -ne 0) {
        docker start $containerName | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Could not restart the original container in place." }
        return
    }

    docker container inspect $containerName 1>$null 2>$null
    if ($LASTEXITCODE -eq 0) {
        $failedName = "open-webui-qwen-failed-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
        docker stop $containerName | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Could not stop the replacement during rollback." }
        docker rename $containerName $failedName
        if ($LASTEXITCODE -ne 0) { throw "Could not preserve the replacement during rollback." }
        Write-Warning "Preserved failed replacement as $failedName."
    }

    docker container inspect $ArchiveName 1>$null 2>$null
    if ($LASTEXITCODE -ne 0) {
        docker start $containerName | Out-Null
        Write-Warning "The original Open WebUI container was never renamed; started it in place."
        return
    }

    docker rename $ArchiveName $containerName
    if ($LASTEXITCODE -ne 0) { throw "Could not restore the original Open WebUI container name." }
    docker start $containerName | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not restart the original Open WebUI container." }
    Write-Warning "Restored the prior Open WebUI container."
}

docker container inspect $containerName 1>$null 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "Expected Open WebUI container was not found: $containerName"
}
docker container inspect $terminalContainerName 1>$null 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "Expected isolated Qwen terminal was not found: $terminalContainerName"
}
docker network inspect $terminalNetworkName 1>$null 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "Expected Qwen terminal network was not found: $terminalNetworkName"
}
if (-not (Test-Path -LiteralPath $terminalSecretPath)) {
    throw "The Qwen terminal API key is missing. Start the isolated terminal before replacing Open WebUI."
}

$oldContainer = docker inspect $containerName | ConvertFrom-Json | Select-Object -First 1
$unexpectedNetworks = @($oldContainer.NetworkSettings.Networks.PSObject.Properties.Name | Where-Object { $_ -notin @("bridge", $terminalNetworkName) })
if ($unexpectedNetworks.Count -gt 0) {
    throw "Open WebUI has additional network attachments; preserve those explicitly before replacement."
}
$dataMount = $oldContainer.Mounts | Where-Object { $_.Destination -eq "/app/backend/data" -and $_.Type -eq "volume" } | Select-Object -First 1
if ($null -eq $dataMount) {
    throw "The current Open WebUI container does not use a named persistent data volume. Refusing replacement."
}
$portBinding = $oldContainer.NetworkSettings.Ports.'8080/tcp' | Select-Object -First 1
if ($null -eq $portBinding -or [string]::IsNullOrWhiteSpace($portBinding.HostPort)) {
    throw "The current Open WebUI container does not publish port 8080. Refusing replacement."
}

if (-not (Test-Path -LiteralPath $webUiSecretPath)) {
    New-Item -ItemType Directory -Force -Path $secretDirectory | Out-Null
    $randomBytes = [System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
    [Convert]::ToBase64String($randomBytes) | Set-Content -LiteralPath $webUiSecretPath -NoNewline
}

$webUiSecret = Get-Content -LiteralPath $webUiSecretPath -Raw
$terminalApiKey = Get-Content -LiteralPath $terminalSecretPath -Raw
$ollamaBaseUrl = Get-ContainerEnvironmentValue -Environment $oldContainer.Config.Env -Name "OLLAMA_BASE_URL"
if ([string]::IsNullOrWhiteSpace($ollamaBaseUrl)) {
    throw "The existing Open WebUI container has no OLLAMA_BASE_URL. Refusing to change its runtime configuration."
}
$adminIds = @(
    docker exec $containerName python -c 'import sqlite3; database=sqlite3.connect("/app/backend/data/webui.db"); [print(row[0]) for row in database.execute("select id from user where role=''admin''").fetchall()]'
)
if ($LASTEXITCODE -ne 0 -or $adminIds.Count -ne 1 -or [string]::IsNullOrWhiteSpace($adminIds[0])) {
    throw "Expected exactly one Open WebUI administrator before enabling the terminal connection. Refusing broad access."
}
$adminUserId = $adminIds[0].Trim()

$terminalConnection = ConvertTo-Json -Compress -Depth 8 -InputObject @(
    @{
        id = "bandi-qwen-terminal"
        url = "http://bandi-qwen-terminal:8000"
        key = $terminalApiKey
        name = "Bandi Qwen Terminal"
        enabled = $true
        auth_type = "bearer"
        config = @{
            access_grants = @(
                @{
                    principal_type = "user"
                    principal_id = $adminUserId
                    permission = "read"
                }
            )
        }
    }
)
if (-not $terminalConnection.TrimStart().StartsWith("[")) {
    throw "Terminal configuration must be a JSON array."
}

$image = $oldContainer.Config.Image
$archiveName = "open-webui-pre-qwen-$(Get-Date -Format 'yyyyMMdd-HHmmss')"

try {
    docker stop $containerName | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not stop the current Open WebUI container." }
    docker rename $containerName $archiveName
    if ($LASTEXITCODE -ne 0) { throw "Could not archive the current Open WebUI container." }

    $previousWebUiSecret = $env:WEBUI_SECRET_KEY
    $previousTerminalConnections = $env:TERMINAL_SERVER_CONNECTIONS
    try {
        $env:WEBUI_SECRET_KEY = $webUiSecret
        $env:TERMINAL_SERVER_CONNECTIONS = $terminalConnection
        docker run -d --name $containerName --restart unless-stopped --publish "$($portBinding.HostPort):8080" --volume "$($dataMount.Name):/app/backend/data" --env "OLLAMA_BASE_URL=$ollamaBaseUrl" --env WEBUI_SECRET_KEY --env "SCARF_NO_ANALYTICS=true" --env "DO_NOT_TRACK=true" --env "ANONYMIZED_TELEMETRY=false" --env TERMINAL_SERVER_CONNECTIONS $image | Out-Null
        $startExitCode = $LASTEXITCODE
    }
    finally {
        $env:WEBUI_SECRET_KEY = $previousWebUiSecret
        $env:TERMINAL_SERVER_CONNECTIONS = $previousTerminalConnections
    }
    if ($startExitCode -ne 0) { throw "Replacement Open WebUI container failed to start." }

    docker network connect $terminalNetworkName $containerName
    if ($LASTEXITCODE -ne 0) { throw "Replacement Open WebUI container could not join the isolated terminal network." }

    $ready = $false
    for ($attempt = 1; $attempt -le 24; $attempt++) {
        Start-Sleep -Seconds 2
        docker exec $containerName python -c "import urllib.request; urllib.request.urlopen('http://bandi-qwen-terminal:8000/health', timeout=3).read()" 1>$null 2>$null
        if ($LASTEXITCODE -eq 0) {
            $ready = $true
            break
        }
    }
    if (-not $ready) { throw "Replacement Open WebUI could not reach the isolated terminal health endpoint." }

    $webUiReady = $false
    for ($attempt = 1; $attempt -le 45; $attempt++) {
        try {
            Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 "http://127.0.0.1:$($portBinding.HostPort)/" 1>$null
            $webUiReady = $true
            break
        }
        catch {
            Start-Sleep -Seconds 2
        }
    }
    if (-not $webUiReady) { throw "Replacement Open WebUI did not become reachable on its existing host port." }
    Write-Output "Open WebUI replacement is running with the server-side Bandi Qwen Terminal connection."
    Write-Output "The previous container is preserved as $archiveName for rollback."
}
catch {
    $failure = $_
    try {
        Restore-PreviousOpenWebUi -ArchiveName $archiveName
    }
    catch {
        throw "Open WebUI replacement failed and automatic rollback also failed. Replacement error: $($failure.Exception.Message). Rollback error: $($_.Exception.Message)"
    }
    throw "Open WebUI replacement failed; the previous container was restored. $($failure.Exception.Message)"
}
