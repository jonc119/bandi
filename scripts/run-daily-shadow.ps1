param(
    [string]$DeliveryDate = (Get-Date).ToString("yyyy-MM-dd"),
    [string]$CalendarFeedPath,
    [string]$PublishPath,
    [int]$MaximumSourceAgeHours = 96
)

$ErrorActionPreference = "Stop"
$workspace = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$logsPath = Join-Path $workspace "var\logs"
$reportsPath = Join-Path $workspace "var\reports"
$localFeedPath = Join-Path $workspace "var\inbox\calendar-feed"
$logPath = Join-Path $logsPath ("daily-{0}.log" -f $DeliveryDate)
$healthJsonPath = Join-Path $logsPath "latest-run-status.json"
$healthMarkdownPath = Join-Path $reportsPath "latest-delivery-qc-status.md"
$mutex = [System.Threading.Mutex]::new($false, "Local\HermesDeliveryQCShadow")
$hasMutex = $false

function Write-Log {
    param([string]$Message)
    $timestamp = (Get-Date).ToString("o")
    Add-Content -LiteralPath $logPath -Value ("{0} {1}" -f $timestamp, $Message) -Encoding utf8
}

function Write-Health {
    param(
        [string]$State,
        [string]$Message,
        [string]$SourceFile = "",
        [string]$RunId = "",
        [int]$PackageCount = 0,
        [int]$PassedCount = 0,
        [int]$FlaggedCount = 0
    )
    $completedAt = (Get-Date).ToString("o")
    $health = [ordered]@{
        schema_version = "1.0"
        mode = "shadow"
        state = $State
        delivery_date = $DeliveryDate
        completed_at = $completedAt
        message = $Message
        source_file = $SourceFile
        run_id = $RunId
        scheduled_packages = $PackageCount
        passed = $PassedCount
        flagged = $FlaggedCount
        emails_sent = $false
    }
    $jsonTemporary = "$healthJsonPath.tmp"
    $health | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $jsonTemporary -Encoding utf8
    Move-Item -LiteralPath $jsonTemporary -Destination $healthJsonPath -Force

    $markdown = @(
        "# Delivery QC Run Status",
        "",
        "> **SHADOW MODE - REVIEW ONLY - NO EMAILS SENT**",
        "",
        "- State: **$State**",
        "- Delivery date: $DeliveryDate",
        "- Completed: $completedAt",
        "- Message: $Message",
        "- Source file: $SourceFile",
        "- Run ID: $RunId",
        "- Scheduled packages: $PackageCount",
        "- Passed: $PassedCount",
        "- Flagged for review: $FlaggedCount",
        ""
    ) -join [Environment]::NewLine
    $markdownTemporary = "$healthMarkdownPath.tmp"
    Set-Content -LiteralPath $markdownTemporary -Value $markdown -Encoding utf8
    Move-Item -LiteralPath $markdownTemporary -Destination $healthMarkdownPath -Force
}

function Publish-File {
    param([string]$Source, [string]$DestinationDirectory)
    if (-not (Test-Path -LiteralPath $Source)) {
        return
    }
    New-Item -ItemType Directory -Force -Path $DestinationDirectory | Out-Null
    $destination = Join-Path $DestinationDirectory ([IO.Path]::GetFileName($Source))
    $temporary = "$destination.tmp"
    Copy-Item -LiteralPath $Source -Destination $temporary -Force
    Move-Item -LiteralPath $temporary -Destination $destination -Force
}

function Get-TargetPackageCount {
    param(
        [string]$IcsPath,
        [string]$TargetDate
    )
    $dateToken = $TargetDate.Replace("-", "")
    $content = Get-Content -LiteralPath $IcsPath -Raw
    $eventPattern = "(?ms)^BEGIN:VEVENT\r?\n.*?^END:VEVENT"
    $datePattern = "(?m)^DTSTART(?:;[^:]*)?:$dateToken(?:T|\r?$)"
    $packagePattern = "(?i)(?:Package Name|Package):"
    $count = 0
    foreach ($eventMatch in [regex]::Matches($content, $eventPattern)) {
        if ($eventMatch.Value -notmatch $datePattern) {
            continue
        }
        $count += [regex]::Matches($eventMatch.Value, $packagePattern).Count
    }
    return $count
}

try {
    New-Item -ItemType Directory -Force -Path $logsPath, $reportsPath, $localFeedPath | Out-Null
    $hasMutex = $mutex.WaitOne(0)
    if (-not $hasMutex) {
        throw "Another Delivery QC run is already active."
    }

    if (-not $CalendarFeedPath) {
        if (-not $env:OneDriveCommercial) {
            throw "OneDriveCommercial is unavailable."
        }
        $CalendarFeedPath = Join-Path $env:OneDriveCommercial "Hermes Delivery QC\calendar-feed"
    }
    if (-not $PublishPath -and $env:OneDriveCommercial) {
        $PublishPath = Join-Path $env:OneDriveCommercial "Hermes Delivery QC\reports"
    }
    if (-not (Test-Path -LiteralPath $CalendarFeedPath -PathType Container)) {
        throw "Calendar feed folder is unavailable: $CalendarFeedPath"
    }

    $sources = @(Get-ChildItem -LiteralPath $CalendarFeedPath -File |
        Where-Object { $_.Extension -ieq ".ics" } |
        Sort-Object LastWriteTimeUtc -Descending)
    if (-not $sources) {
        throw "No ICS file exists in the calendar feed."
    }

    $freshSources = @($sources | Where-Object {
        ([DateTime]::UtcNow - $_.LastWriteTimeUtc).TotalHours -le $MaximumSourceAgeHours
    })
    if (-not $freshSources) {
        $newestAge = [DateTime]::UtcNow - $sources[0].LastWriteTimeUtc
        throw ("Newest ICS file is stale ({0:N1} hours old): {1}" -f $newestAge.TotalHours, $sources[0].Name)
    }

    $source = $null
    foreach ($candidate in $freshSources) {
        if ((Get-TargetPackageCount -IcsPath $candidate.FullName -TargetDate $DeliveryDate) -gt 0) {
            $source = $candidate
            break
        }
    }
    if (-not $source) {
        $source = $freshSources[0]
        Write-Log ("No recent ICS snapshot contains package entries for {0}; using newest source so the checker can produce a zero-delivery report." -f $DeliveryDate)
    }
    elseif ($source.FullName -ne $freshSources[0].FullName) {
        Write-Log ("Newest ICS omitted {0}; selected the newest recent snapshot that still contains that delivery date: {1}" -f $DeliveryDate, $source.Name)
    }

    $localSource = Join-Path $localFeedPath $source.Name
    if (-not (Test-Path -LiteralPath $localSource)) {
        $temporarySource = "$localSource.tmp"
        Copy-Item -LiteralPath $source.FullName -Destination $temporarySource
        Move-Item -LiteralPath $temporarySource -Destination $localSource
    }
    Write-Log ("Selected calendar source {0}" -f $source.Name)

    $containerSource = "/data/var/inbox/calendar-feed/$($source.Name)"
    $newestSource = $freshSources[0]
    $localNewest = Join-Path $localFeedPath $newestSource.Name
    if (-not (Test-Path -LiteralPath $localNewest)) {
        Copy-Item -LiteralPath $newestSource.FullName -Destination $localNewest
    }
    $comparisonSource = "/data/var/inbox/calendar-feed/$($newestSource.Name)"
    Push-Location $workspace
    try {
        $previousErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        $dockerOutput = & docker compose --profile stratus-readonly run -T delivery-qc-stratus run --date $DeliveryDate --ics $containerSource --comparison-ics $comparisonSource --stratus-readonly 2>&1
        $dockerExitCode = $LASTEXITCODE
        $ErrorActionPreference = $previousErrorActionPreference
    }
    finally {
        $ErrorActionPreference = "Stop"
        Pop-Location
    }
    foreach ($line in $dockerOutput) {
        Write-Log ([string]$line)
    }
    if ($dockerExitCode -ne 0) {
        throw "The Delivery QC container failed with exit code $dockerExitCode."
    }

    $latestReportPath = Join-Path $reportsPath "latest-delivery-qc-report.json"
    if (-not (Test-Path -LiteralPath $latestReportPath)) {
        throw "The checker completed without producing the latest JSON report."
    }
    $report = Get-Content -LiteralPath $latestReportPath -Raw | ConvertFrom-Json
    if ($report.delivery_date -ne $DeliveryDate) {
        throw "The latest report date does not match the requested delivery date."
    }
    $message = "Delivery QC completed successfully. Review flagged packages before taking action."
    $healthState = "SUCCESS"
    if ($report.summary.calendar_review_count -gt 0) {
        $healthState = "REVIEW"
        $message = "Package checks completed, but calendar classification or coverage requires review. Do not treat this as all clear."
    }
    Write-Health -State $healthState -Message $message -SourceFile $source.Name -RunId $report.run_id -PackageCount $report.summary.scheduled_packages -PassedCount $report.summary.passed -FlaggedCount $report.summary.flagged
    Write-Log $message

    if ($PublishPath) {
        Publish-File -Source (Join-Path $reportsPath "latest-delivery-qc-dashboard.html") -DestinationDirectory $PublishPath
        Publish-File -Source (Join-Path $reportsPath "latest-delivery-qc-review.xlsx") -DestinationDirectory $PublishPath
        Publish-File -Source (Join-Path $reportsPath "latest-delivery-qc-report.md") -DestinationDirectory $PublishPath
        Publish-File -Source (Join-Path $reportsPath "latest-delivery-qc-report.json") -DestinationDirectory $PublishPath
        Publish-File -Source (Join-Path $reportsPath "delivery-qc-history.csv") -DestinationDirectory $PublishPath
        Publish-File -Source (Join-Path $reportsPath "delivery-qc-history.json") -DestinationDirectory $PublishPath
        Publish-File -Source $healthMarkdownPath -DestinationDirectory $PublishPath
        Write-Log ("Published shadow reports to {0}" -f $PublishPath)
    }
    exit 0
}
catch {
    $message = $_.Exception.Message
    try {
        Write-Health -State "FAILED" -Message $message
        Write-Log ("FAILED: {0}" -f $message)
        if ($PublishPath) {
            Publish-File -Source $healthMarkdownPath -DestinationDirectory $PublishPath
        }
    }
    catch {
    }
    Write-Error $message
    exit 1
}
finally {
    if ($hasMutex) {
        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
}
