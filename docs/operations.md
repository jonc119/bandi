# Shadow Operations

## Installed Schedule

- Windows task: `Hermes Delivery QC Shadow 4PM`
- Trigger: daily at 4:00 PM local time (`America/New_York`)
- Execution: current interactive Windows user with limited privilege
- Recovery: start when available, wake to run, and retry twice at 15-minute intervals
- Concurrency: overlapping runs are rejected by both Task Scheduler and a named mutex

The user must remain signed in so Docker Desktop and OneDrive are available. The computer may be
locked. If it is asleep, Task Scheduler is configured to wake it.

## Daily Procedure

1. Power Automate saves Southwest Delivery Schedule attachments to business OneDrive.
2. At 4:00 PM, `scripts/run-daily-shadow.ps1` selects the newest recent `.ics` snapshot that
   still contains package entries for the target delivery date. This preserves same-day evidence
   when a later rolling-calendar export has already removed completed events.
3. The runner rejects a missing feed, a missing ICS, or an ICS older than 96 hours. If no recent
   snapshot contains the target date, it uses the newest source to produce an auditable
   zero-delivery report.
4. Docker queries Stratus through the GET-only adapter and runs deterministic QC rules.
5. Review `index.html` for the selected reporting period, then open a flagged day's
   `latest-delivery-qc-dashboard.html` detail beginning with `Needs attention`.
6. Use the daily report's direct Stratus and Power BI links to inspect each package or container. Download the
   Excel export only when a tabular audit view is useful.

## Health And Reports

- Machine-readable health: `var/logs/latest-run-status.json`
- Human-readable health: `var/reports/latest-delivery-qc-status.md`
- Primary history dashboard: `var/reports/index.html`
- Latest daily dashboard: `var/reports/latest-delivery-qc-dashboard.html`
- Historical machine summary: `var/reports/delivery-qc-history.json`
- Historical sortable export: `var/reports/delivery-qc-history.csv`
- Excel review: `var/reports/latest-delivery-qc-review.xlsx`
- Markdown report: `var/reports/latest-delivery-qc-report.md`
- Full audit data: `var/reports/latest-delivery-qc-report.json`

The latest review files are also copied to business OneDrive under
`Hermes Delivery QC/reports`, making them available on authorized OneDrive devices. Hermes reads
the local report and draft directories through read-only mounts.

The history dashboard counts one issue per scheduled package flagged for investigation and keeps
only the latest completed run for each delivery date. Its presets use the latest checked delivery
date as the endpoint: `This week` begins Monday, `Last 7 days` includes that date and the prior six,
and `Last month` means the previous calendar month. Rebuild it without querying Stratus using
`docker compose run --rm delivery-qc history`.

## Failure Behavior

A source outage, stale or absent ICS file, Docker failure, Stratus error, missing package,
ambiguous package, count mismatch, or unknown status never becomes a successful delivery. The
runner records `FAILED` health when execution cannot complete. Package-level uncertainty is marked
`INVESTIGATE` in the report.

## Go-Live Gate

The workflow remains in shadow mode. It does not send notifications or email. Go-live requires an
explicit approval and a separate change review covering recipients, approval behavior, retry and
monitoring rules, rollback, and least-privilege credentials. Changing configuration alone cannot
activate live behavior; the application currently rejects every mode except `shadow`.
