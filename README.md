# Hermes Delivery QC Checker

A deterministic delivery quality-control checker for manufactured Stratus packages and
containers. The production-shaped workflow is active in **shadow mode**: it reads the latest
delivery-calendar ICS attachment, queries Stratus through allowlisted GET-only endpoints, checks
every expected container, and publishes review files without sending email or changing company
data.

## Current Workflow

1. Power Automate copies matching Southwest Delivery Schedule attachments to the business
   OneDrive folder `Hermes Delivery QC/calendar-feed`.
2. Windows Scheduled Task `Hermes Delivery QC Shadow 4PM` runs daily at 4:00 PM Eastern.
3. `scripts/run-daily-shadow.ps1` accepts only a recent `.ics` file and copies it into the local
   runtime inbox.
4. Docker runs the checker with live, read-only Stratus access.
5. Deterministic Python rules write responsive daily and historical HTML dashboards plus Markdown,
   JSON, CSV, SQLite audit evidence, and an Excel export.
6. Stable latest files are published to business OneDrive and mounted read-only into Hermes.

## Safety Boundary

- `deployment.mode` remains `shadow` and the application rejects any other mode.
- Stratus access is restricted to allowlisted GET endpoints.
- No email is sent; proposed follow-up messages remain drafts marked `NOT SENT`.
- Hermes can read only `var/reports/` and `var/drafts/`; it cannot modify them.
- Hermes has no email, browser, web-search, terminal, code-execution, or Stratus tool.
- A human must explicitly approve a separate go-live change.

## History Dashboard

The primary interface is `var/reports/index.html`. It is designed for desktop and mobile review:

- Presets answer `This week`, `Last 7 days`, `This month`, and `Last month` immediately.
- Custom start/end dates and date sorting support any reporting period.
- Totals show flagged packages, packages checked, outstanding containers, and days reviewed.
- Only the latest completed run for each delivery date is counted, so reruns are not duplicated.
- One shipping QC issue means one scheduled package was flagged for investigation.
- Every issue opens the corresponding archived daily report at its investigation section.
- `delivery-qc-history.json` provides the same period totals for Hermes or other read-only consumers.

The most recent daily detail remains at `var/reports/latest-delivery-qc-dashboard.html`:

- The top card answers whether anything needs attention that day.
- Exceptions are grouped by package instead of spread across spreadsheet rows.
- Each unresolved container links directly to Stratus and its filtered Shipping dashboard view.
- Each package links directly to Stratus and its filtered Warehouse History view.
- Cleared packages stay collapsed until the reviewer needs them.
- Audit exports remain one click away.

Run the locked-down local viewer with:

```powershell
docker compose up -d delivery-qc-dashboard
```

Then open `http://127.0.0.1:9120/`. Authorized devices on the private Tailscale network can use
`https://desktop-0i2o7e0.tail06a4fa.ts.net/delivery-qc/`. The viewer binds only to localhost,
has no writable mount, holds no credentials, and serves only completed report files through the
existing tailnet-only proxy.

## Excel Export

`var/reports/latest-delivery-qc-review.xlsx` remains available when a spreadsheet is needed:

- `Dashboard`: daily totals and pass/investigate counts.
- `Package Review`: one row per scheduled package with red investigation flags and direct Stratus
  package links when a package is matched.
- `Container Detail`: the exact Stratus status and direct Stratus link for every matched container.

The Excel investigation queue links each flagged container and matched package directly to its
signed-in Stratus page. It also opens the exact matching package on the Power BI `Historical
Requests` page and prefilters the shipping dashboard to the exact pallet or package, so the reviewer
does not land on either report's generic front page. Unmatched packages open the Stratus Packages
page for manual searching.

The same latest HTML and audit outputs, plus the historical JSON and CSV summaries, are copied to business OneDrive under
`Hermes Delivery QC/reports`. Archived run files remain under dated run-ID directories in
`var/reports/`.

## Manual Shadow Run

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-daily-shadow.ps1
```

The runner defaults to today's date, rejects missing or stale calendar input, prevents overlapping
runs, and writes health state to `var/logs/latest-run-status.json`.

Rebuild only the historical dashboard and exports from the local SQLite audit database with:

```powershell
docker compose run --rm delivery-qc history
```

## Development

Python 3.13 or newer is required.

```powershell
$env:PYTHONPATH = "src"
py -m unittest discover -s tests -v
```

See `docs/operations.md`, `docs/delivery-qc-process-flowchart.md`, and
`docs/hermes-handoff.md` for the operating procedure and system boundaries.

## Local Qwen Handoff

`AGENTS.md`, `HANDOFF.md`, tests, and Git are the shared project memory between hosted Codex and
local Qwen. Install the optional profile once with:

```powershell
.\scripts\install-qwen-codex-profile.ps1
```

Then double-click `Start Qwen Codex.cmd`. For a terminal launch, use the same explicit provider guard:

```powershell
codex -p qwen --oss --local-provider ollama -m qwen3.8:latest
```

The launcher verifies Ollama is reachable and begins with a read-only reconstruction of the current
Git state before asking Qwen to continue. It also supplies `--oss --local-provider ollama` explicitly,
so the run cannot silently inherit the OpenAI provider. The existing `Start Local Coding.cmd` remains available
for narrowly allowlisted work in an isolated copy when direct worktree access is not appropriate.

For phone-driven Open WebUI coding, see `docs/qwen-openwebui-workflow.md`. That path uses a separate
`qwen/agent` Git branch and isolated terminal workspace; it never grants Qwen the live QC runtime.
