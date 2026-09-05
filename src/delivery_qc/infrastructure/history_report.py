from __future__ import annotations

from delivery_qc.infrastructure.export_safety import SafeCsvWriter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from html import escape
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from delivery_qc.infrastructure.database import HistoricalPackageResult, HistoricalRun
from delivery_qc.infrastructure.report_presentation import (
    ACTION_BY_RESULT,
    ISSUE_BY_RESULT,
    LABEL_BY_RESULT,
)


_DISPLAY_TIMEZONE = ZoneInfo("America/New_York")


@dataclass(frozen=True, slots=True)
class Period:
    key: str
    label: str
    start_date: date
    end_date: date


def write_history_reports(
    *,
    html_path: Path,
    json_path: Path,
    csv_path: Path,
    history: tuple[HistoricalRun, ...],
    generated_at: datetime,
) -> None:
    as_of_date = _as_of_date(history, generated_at)
    periods = _periods(as_of_date, history)
    _atomic_write(
        html_path,
        _render_dashboard(
            history=history,
            generated_at=generated_at,
            as_of_date=as_of_date,
            periods=periods,
        ),
    )
    _atomic_write(
        json_path,
        json.dumps(
            _history_payload(history, generated_at, as_of_date, periods),
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
    )
    _write_csv(csv_path, history)


def _render_dashboard(
    *,
    history: tuple[HistoricalRun, ...],
    generated_at: datetime,
    as_of_date: date,
    periods: tuple[Period, ...],
) -> str:
    default_period = next(period for period in periods if period.key == "last-7-days")
    selected_runs = _runs_in_period(history, default_period)
    initial_summary = _summary(selected_runs)
    all_issues = tuple(
        (run, package)
        for run in history
        for package in run.packages
        if package.follow_up_required
    )

    preset_buttons = "".join(
        (
            f'<button class="range-chip{" active" if period.key == default_period.key else ""}" '
            f'type="button" data-key="{_attr(period.key)}" '
            f'data-label="{_attr(period.label)}" '
            f'data-start="{period.start_date.isoformat()}" '
            f'data-end="{period.end_date.isoformat()}" '
            f'aria-pressed="{"true" if period.key == default_period.key else "false"}">'
            f'{_e(period.label)}</button>'
        )
        for period in periods
    )

    day_rows = "".join(
        _day_row(run, visible=_contains(default_period, run.delivery_date))
        for run in history
    )
    issue_cards = "".join(
        _issue_card(run, package, visible=_contains(default_period, run.delivery_date))
        for run, package in all_issues
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'; object-src 'none'; connect-src 'none'">
  <title>Delivery QC History</title>
  <style>{_STYLES}</style>
</head>
<body data-as-of="{as_of_date.isoformat()}">
  <header class="topbar">
    <div class="shell topbar-inner">
      <a class="brand" href="#top" aria-label="Delivery QC history home">
        <span class="brand-mark" aria-hidden="true">DQ</span>
        <span>Delivery QC</span>
      </a>
      <div class="topbar-actions">
        <a class="nav-link" href="latest-delivery-qc-dashboard.html">Latest report</a>
        <span class="mode-pill">Shadow mode · No emails sent</span>
      </div>
    </div>
  </header>

  <main id="top" class="shell">
    <section class="page-heading" aria-labelledby="page-title">
      <div>
        <p class="eyebrow">Shipping quality over time</p>
        <h1 id="page-title">Delivery QC history</h1>
        <p class="updated">Updated {_e(_format_time(generated_at))} · Latest checked date {_e(_format_date(as_of_date))}</p>
      </div>
      <a class="quiet-button" href="latest-delivery-qc-dashboard.html">Open latest day</a>
    </section>

    <section class="filter-panel" aria-labelledby="range-title">
      <div>
        <p class="eyebrow" id="range-title">Date range</p>
        <div class="range-chips" role="group" aria-label="Quick date ranges">{preset_buttons}</div>
      </div>
      <div class="custom-range">
        <label>From<input id="from-date" type="date" value="{default_period.start_date.isoformat()}" max="{as_of_date.isoformat()}"></label>
        <label>To<input id="to-date" type="date" value="{default_period.end_date.isoformat()}" max="{as_of_date.isoformat()}"></label>
        <label>Sort<select id="sort-order">
          <option value="date-desc">Newest first</option>
          <option value="date-asc">Oldest first</option>
          <option value="issues-desc">Most issues</option>
        </select></label>
      </div>
    </section>

    <section class="history-hero" aria-live="polite">
      <div>
        <p class="eyebrow" id="period-label">{_e(default_period.label)}</p>
        <h2><span id="issue-total">{initial_summary['issues']}</span> shipping QC <span id="issue-word">{_plural(initial_summary['issues'], 'issue')}</span></h2>
        <p id="range-description">{_e(_format_range(default_period.start_date, default_period.end_date))}</p>
      </div>
      <div class="hero-rate">
        <strong id="issue-rate">{_issue_rate(initial_summary)}%</strong>
        <span>of packages flagged</span>
      </div>
    </section>

    <p class="definition">One shipping QC issue means one scheduled package was flagged for investigation. Reruns are not double-counted; only the latest completed run for each delivery date is included.</p>

    <section class="metrics" aria-label="Selected period totals">
      {_metric("Issues", initial_summary['issues'], "flagged packages", element_id="metric-issues", attention=True)}
      {_metric("Checked", initial_summary['packages'], "scheduled packages", element_id="metric-packages")}
      {_metric("Known outstanding", initial_summary['outstanding'], "unverified matches excluded", element_id="metric-outstanding", attention=True)}
      {_metric("Days reviewed", initial_summary['days'], "latest runs", element_id="metric-days")}
    </section>

    <section class="primary-section" aria-labelledby="issues-title">
      <div class="section-heading">
        <div>
          <p class="eyebrow">Investigation queue</p>
          <h2 id="issues-title">Issues in this range</h2>
        </div>
        <span class="section-count"><span id="visible-issue-count">{initial_summary['issues']}</span> {_plural(initial_summary['issues'], 'package')}</span>
      </div>
      <div class="history-issues" id="history-issues">{issue_cards}</div>
      <div class="empty-state" id="issues-empty"{" hidden" if initial_summary['issues'] else ""}>
        <span class="empty-mark" aria-hidden="true">✓</span>
        <div><strong>No package flags in this range</strong><p>This does not verify calendar coverage. Open each day's calendar notices.</p></div>
      </div>
    </section>

    <section class="secondary-section" aria-labelledby="days-title">
      <div class="section-heading">
        <div>
          <p class="eyebrow">Daily results</p>
          <h2 id="days-title">Reviewed delivery dates</h2>
        </div>
        <span class="section-count"><span id="visible-day-count">{initial_summary['days']}</span> {_plural(initial_summary['days'], 'day')}</span>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Date</th><th>Checked</th><th>Cleared</th><th>Issues</th><th>Outstanding</th><th><span class="sr-only">Report</span></th></tr></thead>
          <tbody id="history-days">{day_rows}</tbody>
        </table>
        <div class="empty-state table-empty" id="days-empty"{" hidden" if initial_summary['days'] else ""}>
          <div><strong>No reviewed dates in this range</strong><p>Choose another preset or enter custom dates.</p></div>
        </div>
      </div>
    </section>

    <section class="secondary-section" aria-labelledby="exports-title">
      <div class="section-heading compact">
        <div><p class="eyebrow">Evidence</p><h2 id="exports-title">History exports</h2></div>
      </div>
      <div class="artifact-grid">
        {_artifact_link("delivery-qc-history.csv", "History CSV", "Sort and analyze every package")}
        {_artifact_link("delivery-qc-history.json", "History JSON", "Machine-readable period totals")}
        {_artifact_link("latest-delivery-qc-review.xlsx", "Latest Excel audit", "Most recent daily workbook")}
      </div>
    </section>
  </main>

  <footer class="footer">
    <div class="shell footer-inner">
      <span>PASS still requires every expected container to be Field Received.</span>
      <span>History ends on {_e(as_of_date.isoformat())}.</span>
    </div>
  </footer>
  <script>{_SCRIPT}</script>
</body>
</html>
"""


def _day_row(run: HistoricalRun, *, visible: bool) -> str:
    tone = "attention" if run.issue_count else "clear" if run.package_count else "neutral"
    status = (
        f"{run.issue_count} {_plural(run.issue_count, 'issue')}"
        if run.issue_count
        else "Matched packages passed; review coverage" if run.package_count else "Coverage unverified"
    )
    report_href = _report_href(run)
    return f"""
      <tr class="history-day {tone}" data-date="{run.delivery_date.isoformat()}" data-packages="{run.package_count}" data-passed="{run.passed_count}" data-issues="{run.issue_count}" data-outstanding="{run.outstanding_count}" data-created="{_attr(run.created_at.isoformat())}"{"" if visible else " hidden"}>
        <td data-label="Date"><strong>{_e(_format_date(run.delivery_date))}</strong><small>{_e(status)}</small></td>
        <td data-label="Checked">{run.package_count}</td>
        <td data-label="Cleared">{run.passed_count}</td>
        <td data-label="Issues"><span class="number {tone}">{run.issue_count}</span></td>
        <td data-label="Outstanding">{run.outstanding_count}</td>
        <td class="row-link"><a href="{_attr(report_href)}">Open day <span aria-hidden="true">›</span></a></td>
      </tr>
    """


def _issue_card(
    run: HistoricalRun,
    package: HistoricalPackageResult,
    *,
    visible: bool,
) -> str:
    report_href = f"{_report_href(run)}#attention-title"
    expected = "Unknown" if package.expected_count is None else str(package.expected_count)
    unverified = package.observed_count == 0
    receipt = "Receipt unverified" if unverified else f"{package.field_received_count} received"
    outstanding = "?" if unverified else str(package.outstanding_count)
    return f"""
      <article class="history-issue" data-date="{run.delivery_date.isoformat()}" data-issues="1"{"" if visible else " hidden"}>
        <div class="issue-date"><time datetime="{run.delivery_date.isoformat()}">{_e(_short_date(run.delivery_date))}</time><span class="status-pill">{_e(LABEL_BY_RESULT[package.result_code])}</span></div>
        <div class="issue-copy">
          <h3>{_e(package.package_name)}</h3>
          <p>{_e(package.project or "Project not identified")}</p>
          <span>{_e(ISSUE_BY_RESULT[package.result_code])}</span>
        </div>
        <div class="issue-counts">
          <span><strong>{outstanding}</strong> {'unverified' if unverified else 'outstanding'}</span>
          <span>{receipt} · {expected} expected</span>
        </div>
        <div class="issue-action">
          <p>{_e(ACTION_BY_RESULT[package.result_code])}</p>
          <a href="{_attr(report_href)}">Open daily issues <span aria-hidden="true">›</span></a>
        </div>
      </article>
    """


def _history_payload(
    history: tuple[HistoricalRun, ...],
    generated_at: datetime,
    as_of_date: date,
    periods: tuple[Period, ...],
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "mode": "shadow",
        "emails_sent": False,
        "generated_at": generated_at.isoformat(),
        "as_of_date": as_of_date.isoformat(),
        "issue_definition": (
            "One issue is one scheduled package whose latest daily run requires follow-up."
        ),
        "deduplication": "Only the latest completed run for each delivery date is counted.",
        "periods": {
            period.key: {
                "label": period.label,
                "start_date": period.start_date.isoformat(),
                "end_date": period.end_date.isoformat(),
                **_summary(_runs_in_period(history, period)),
            }
            for period in periods
        },
        "days": [
            {
                "delivery_date": run.delivery_date.isoformat(),
                "run_id": run.run_id,
                "created_at": run.created_at.isoformat(),
                "report_href": _report_href(run),
                "scheduled_packages": run.package_count,
                "passed": run.passed_count,
                "issues": run.issue_count,
                "outstanding_containers": run.outstanding_count,
                "packages": [
                    {
                        "source_uid": package.source_uid,
                        "project": package.project,
                        "package_name": package.package_name,
                        "result_code": package.result_code.value,
                        "expected_count": package.expected_count,
                        "observed_count": package.observed_count,
                        "field_received_count": package.field_received_count,
                        "outstanding_count": package.outstanding_count,
                        "follow_up_required": package.follow_up_required,
                        "issue_href": (
                            f"{_report_href(run)}#attention-title"
                            if package.follow_up_required
                            else _report_href(run)
                        ),
                    }
                    for package in run.packages
                ],
            }
            for run in history
        ],
    }


def _write_csv(path: Path, history: tuple[HistoricalRun, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    with temporary_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = SafeCsvWriter(csv_file)
        writer.writerow(
            [
                "delivery_date",
                "run_id",
                "created_at",
                "project",
                "package_name",
                "result_code",
                "expected_count",
                "observed_count",
                "field_received_count",
                "outstanding_count",
                "follow_up_required",
                "daily_report",
            ]
        )
        for run in history:
            if not run.packages:
                writer.writerow(
                    [
                        run.delivery_date.isoformat(),
                        run.run_id,
                        run.created_at.isoformat(),
                        "",
                        "",
                        "CALENDAR_COVERAGE_UNVERIFIED",
                        "",
                        0,
                        0,
                        0,
                        "no",
                        _report_href(run),
                    ]
                )
                continue
            for package in run.packages:
                writer.writerow(
                    [
                        run.delivery_date.isoformat(),
                        run.run_id,
                        run.created_at.isoformat(),
                        package.project,
                        package.package_name,
                        package.result_code.value,
                        package.expected_count if package.expected_count is not None else "",
                        package.observed_count,
                        package.field_received_count,
                        package.outstanding_count,
                        "yes" if package.follow_up_required else "no",
                        (
                            f"{_report_href(run)}#attention-title"
                            if package.follow_up_required
                            else _report_href(run)
                        ),
                    ]
                )
    temporary_path.replace(path)


def _periods(
    as_of_date: date,
    history: tuple[HistoricalRun, ...],
) -> tuple[Period, ...]:
    week_start = as_of_date - timedelta(days=as_of_date.weekday())
    month_start = as_of_date.replace(day=1)
    previous_month_end = month_start - timedelta(days=1)
    previous_month_start = previous_month_end.replace(day=1)
    all_start = min((run.delivery_date for run in history), default=as_of_date)
    return (
        Period("this-week", "This week", week_start, as_of_date),
        Period("last-7-days", "Last 7 days", as_of_date - timedelta(days=6), as_of_date),
        Period("this-month", "This month", month_start, as_of_date),
        Period("last-month", "Last month", previous_month_start, previous_month_end),
        Period("all", "All available", all_start, as_of_date),
    )


def _runs_in_period(
    history: tuple[HistoricalRun, ...],
    period: Period,
) -> tuple[HistoricalRun, ...]:
    return tuple(
        run for run in history if _contains(period, run.delivery_date)
    )


def _contains(period: Period, value: date) -> bool:
    return period.start_date <= value <= period.end_date


def _summary(history: tuple[HistoricalRun, ...]) -> dict[str, int]:
    return {
        "days": len(history),
        "packages": sum(run.package_count for run in history),
        "passed": sum(run.passed_count for run in history),
        "issues": sum(run.issue_count for run in history),
        "outstanding": sum(run.outstanding_count for run in history),
    }


def _issue_rate(summary: dict[str, int]) -> str:
    if not summary["packages"]:
        return "0"
    return f"{summary['issues'] / summary['packages'] * 100:.1f}".rstrip("0").rstrip(".")


def _as_of_date(history: tuple[HistoricalRun, ...], generated_at: datetime) -> date:
    if history:
        return max(run.delivery_date for run in history)
    if generated_at.tzinfo is not None:
        generated_at = generated_at.astimezone(_DISPLAY_TIMEZONE)
    return generated_at.date()


def _report_href(run: HistoricalRun) -> str:
    return (
        f"{run.delivery_date.isoformat()}/{run.run_id}/delivery-qc-dashboard.html"
    )


def _metric(
    label: str,
    value: int,
    detail: str,
    *,
    element_id: str,
    attention: bool = False,
) -> str:
    class_name = "metric attention" if attention else "metric"
    return f"""
      <div class="{class_name}">
        <span>{_e(label)}</span>
        <strong id="{_attr(element_id)}">{value}</strong>
        <small>{_e(detail)}</small>
      </div>
    """


def _artifact_link(href: str, title: str, subtitle: str) -> str:
    return f"""
      <a class="artifact-link" href="{_attr(href)}">
        <span><strong>{_e(title)}</strong><small>{_e(subtitle)}</small></span>
        <span class="chevron" aria-hidden="true">›</span>
      </a>
    """


def _format_date(value: date) -> str:
    return value.strftime("%A, %B %d, %Y").replace(" 0", " ")


def _short_date(value: date) -> str:
    return value.strftime("%b %d, %Y").replace(" 0", " ")


def _format_range(start_date: date, end_date: date) -> str:
    if start_date == end_date:
        return _format_date(start_date)
    if start_date.year == end_date.year and start_date.month == end_date.month:
        return (
            f"{start_date.strftime('%B')} {start_date.day}–{end_date.day}, "
            f"{end_date.year}"
        )
    if start_date.year == end_date.year:
        return (
            f"{start_date.strftime('%b')} {start_date.day} – "
            f"{end_date.strftime('%b')} {end_date.day}, {end_date.year}"
        )
    return f"{_short_date(start_date)} – {_short_date(end_date)}"


def _format_time(value: datetime) -> str:
    if value.tzinfo is not None:
        value = value.astimezone(_DISPLAY_TIMEZONE)
    return value.strftime("%B %d, %Y at %I:%M %p ET").replace(" 0", " ").replace(" at 0", " at ")


def _plural(value: int, singular: str) -> str:
    return singular if value == 1 else f"{singular}s"


def _e(value: object) -> str:
    return escape(str(value))


def _attr(value: object) -> str:
    return escape(str(value), quote=True)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(content, encoding="utf-8")
    temporary_path.replace(path)


_SCRIPT = r"""
(() => {
  const dayBody = document.querySelector('#history-days');
  const issueList = document.querySelector('#history-issues');
  const dayRows = [...document.querySelectorAll('.history-day')];
  const issueCards = [...document.querySelectorAll('.history-issue')];
  const presetButtons = [...document.querySelectorAll('.range-chip')];
  const fromInput = document.querySelector('#from-date');
  const toInput = document.querySelector('#to-date');
  const sortSelect = document.querySelector('#sort-order');
  const periodLabel = document.querySelector('#period-label');
  const rangeDescription = document.querySelector('#range-description');
  const issuesEmpty = document.querySelector('#issues-empty');
  const daysEmpty = document.querySelector('#days-empty');

  const number = (element, value) => {
    if (element) element.textContent = String(value);
  };

  const parseDate = (value) => new Date(`${value}T12:00:00`);
  const prettyDate = (value, includeYear = true) => parseDate(value).toLocaleDateString(
    undefined,
    includeYear
      ? { month: 'short', day: 'numeric', year: 'numeric' }
      : { month: 'short', day: 'numeric' },
  );

  const describeRange = (start, end) => {
    if (start === end) return prettyDate(start);
    const startDate = parseDate(start);
    const endDate = parseDate(end);
    if (startDate.getFullYear() === endDate.getFullYear()) {
      return `${prettyDate(start, false)} – ${prettyDate(end)}`;
    }
    return `${prettyDate(start)} – ${prettyDate(end)}`;
  };

  const updateSummary = (label, start, end) => {
    const visibleDays = dayRows.filter((row) => !row.hidden);
    const visibleIssues = issueCards.filter((card) => !card.hidden);
    const totals = visibleDays.reduce(
      (summary, row) => ({
        packages: summary.packages + Number(row.dataset.packages),
        issues: summary.issues + Number(row.dataset.issues),
        outstanding: summary.outstanding + Number(row.dataset.outstanding),
      }),
      { packages: 0, issues: 0, outstanding: 0 },
    );
    const rate = totals.packages ? (totals.issues / totals.packages * 100) : 0;

    periodLabel.textContent = label;
    rangeDescription.textContent = describeRange(start, end);
    number(document.querySelector('#issue-total'), totals.issues);
    document.querySelector('#issue-word').textContent = totals.issues === 1 ? 'issue' : 'issues';
    number(document.querySelector('#issue-rate'), `${Number(rate.toFixed(1))}%`);
    number(document.querySelector('#metric-issues'), totals.issues);
    number(document.querySelector('#metric-packages'), totals.packages);
    number(document.querySelector('#metric-outstanding'), totals.outstanding);
    number(document.querySelector('#metric-days'), visibleDays.length);
    number(document.querySelector('#visible-issue-count'), visibleIssues.length);
    number(document.querySelector('#visible-day-count'), visibleDays.length);
    issuesEmpty.hidden = visibleIssues.length !== 0;
    daysEmpty.hidden = visibleDays.length !== 0;
  };

  const applyRange = (start, end, label) => {
    if (!start || !end) return;
    if (start > end) [start, end] = [end, start];
    fromInput.value = start;
    toInput.value = end;
    dayRows.forEach((row) => {
      row.hidden = row.dataset.date < start || row.dataset.date > end;
    });
    issueCards.forEach((card) => {
      card.hidden = card.dataset.date < start || card.dataset.date > end;
    });
    updateSummary(label, start, end);
  };

  const applySort = () => {
    const direction = sortSelect.value === 'date-asc' ? 1 : -1;
    const dayComparator = (left, right) => {
      if (sortSelect.value === 'issues-desc') {
        const issueDifference = Number(right.dataset.issues) - Number(left.dataset.issues);
        if (issueDifference) return issueDifference;
      }
      return left.dataset.date.localeCompare(right.dataset.date) * direction;
    };
    const issueComparator = (left, right) => (
      left.dataset.date.localeCompare(right.dataset.date) * direction
    );
    [...dayRows].sort(dayComparator).forEach((row) => dayBody.append(row));
    [...issueCards].sort(issueComparator).forEach((card) => issueList.append(card));
  };

  presetButtons.forEach((button) => button.addEventListener('click', () => {
    presetButtons.forEach((item) => {
      const active = item === button;
      item.classList.toggle('active', active);
      item.setAttribute('aria-pressed', String(active));
    });
    applyRange(button.dataset.start, button.dataset.end, button.dataset.label);
  }));

  const applyCustomRange = () => {
    if (!fromInput.value || !toInput.value) return;
    presetButtons.forEach((button) => {
      button.classList.remove('active');
      button.setAttribute('aria-pressed', 'false');
    });
    applyRange(fromInput.value, toInput.value, 'Custom range');
  };

  fromInput.addEventListener('change', applyCustomRange);
  toInput.addEventListener('change', applyCustomRange);
  sortSelect.addEventListener('change', applySort);
  applySort();
})();
"""


_STYLES = """
:root {
  color-scheme: light;
  --canvas: #f5f5f7;
  --surface: #ffffff;
  --ink: #1d1d1f;
  --secondary: #6e6e73;
  --line: #d2d2d7;
  --line-soft: #e8e8ed;
  --blue: #0071e3;
  --blue-hover: #0077ed;
  --red: #d70015;
  --red-soft: #fff1f2;
  --green: #1e7d34;
  --green-soft: #f0faf2;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
  font-synthesis: none;
}
* { box-sizing: border-box; }
[hidden] { display: none !important; }
html { scroll-behavior: smooth; }
body { margin: 0; background: var(--canvas); color: var(--ink); }
a { color: inherit; }
button, input, select { font: inherit; }
.shell { width: min(1120px, calc(100% - 40px)); margin: 0 auto; }
.topbar { background: rgba(255,255,255,.92); border-bottom: 1px solid var(--line-soft); }
.topbar-inner { min-height: 58px; display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.brand { display: inline-flex; align-items: center; gap: 10px; text-decoration: none; font-weight: 650; letter-spacing: -.01em; }
.brand-mark { width: 30px; height: 30px; display: grid; place-items: center; border-radius: 9px; background: var(--ink); color: white; font-size: 11px; letter-spacing: .04em; }
.topbar-actions { display: flex; align-items: center; gap: 18px; }
.nav-link { color: var(--blue); font-size: 13px; font-weight: 650; text-decoration: none; }
.mode-pill { color: var(--secondary); font-size: 12px; font-weight: 600; }
.page-heading { padding: 54px 0 28px; display: flex; align-items: end; justify-content: space-between; gap: 20px; }
.eyebrow { margin: 0 0 7px; color: var(--secondary); font-size: 12px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
h1, h2, h3, p { margin-top: 0; }
h1 { margin-bottom: 6px; font-size: clamp(34px, 5vw, 52px); line-height: 1.04; letter-spacing: -.04em; }
.updated { margin: 0; color: var(--secondary); font-size: 14px; }
.quiet-button { border: 1px solid var(--line); border-radius: 980px; padding: 10px 16px; background: var(--surface); color: var(--blue); font-size: 13px; font-weight: 650; text-decoration: none; white-space: nowrap; }
.filter-panel { display: grid; grid-template-columns: 1fr auto; gap: 30px; margin-bottom: 20px; padding: 22px; border: 1px solid var(--line-soft); border-radius: 22px; background: var(--surface); }
.range-chips { display: flex; flex-wrap: wrap; gap: 8px; }
.range-chip { min-height: 36px; padding: 7px 13px; border: 1px solid var(--line); border-radius: 980px; background: var(--surface); color: var(--ink); cursor: pointer; font-size: 12px; font-weight: 650; }
.range-chip:hover { border-color: #a8a8ad; }
.range-chip.active { border-color: var(--ink); background: var(--ink); color: white; }
.custom-range { display: flex; align-items: end; gap: 10px; }
.custom-range label { display: grid; gap: 6px; color: var(--secondary); font-size: 11px; font-weight: 650; }
.custom-range input, .custom-range select { min-height: 36px; max-width: 150px; padding: 6px 9px; border: 1px solid var(--line); border-radius: 9px; background: white; color: var(--ink); font-size: 12px; }
.history-hero { min-height: 220px; padding: 40px 44px; border-radius: 28px; display: flex; align-items: center; justify-content: space-between; gap: 34px; background: linear-gradient(135deg, #edf5ff, #f8f1ff); }
.history-hero h2 { max-width: 760px; margin-bottom: 12px; font-size: clamp(34px, 6vw, 58px); line-height: 1; letter-spacing: -.05em; }
.history-hero p:last-child { margin: 0; color: #424245; font-size: 15px; }
.hero-rate { flex: 0 0 auto; min-width: 140px; text-align: center; }
.hero-rate strong { display: block; color: var(--blue); font-size: clamp(44px, 7vw, 70px); line-height: 1; letter-spacing: -.06em; }
.hero-rate span { display: block; margin-top: 8px; color: var(--secondary); font-size: 11px; font-weight: 650; text-transform: uppercase; }
.definition { max-width: 820px; margin: 16px 4px 0; color: var(--secondary); font-size: 12px; line-height: 1.5; }
.metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1px; margin: 24px 0 62px; overflow: hidden; border: 1px solid var(--line-soft); border-radius: 20px; background: var(--line-soft); }
.metric { min-height: 126px; padding: 22px 24px; background: var(--surface); }
.metric span, .metric small { display: block; color: var(--secondary); }
.metric span { font-size: 13px; font-weight: 650; }
.metric strong { display: block; margin: 9px 0 2px; font-size: 36px; letter-spacing: -.04em; }
.metric small { font-size: 12px; }
.metric.attention strong { color: var(--red); }
.primary-section, .secondary-section { margin-bottom: 56px; }
.section-heading { display: flex; align-items: end; justify-content: space-between; gap: 18px; margin: 0 2px 18px; }
.section-heading.compact { margin-bottom: 14px; }
.section-heading h2 { margin-bottom: 0; font-size: 28px; letter-spacing: -.025em; }
.section-count { color: var(--secondary); font-size: 13px; }
.history-issues { display: grid; gap: 12px; }
.history-issue { display: grid; grid-template-columns: 150px minmax(220px, 1fr) 150px minmax(210px, .8fr); gap: 22px; align-items: center; padding: 24px; border: 1px solid var(--line-soft); border-radius: 20px; background: var(--surface); box-shadow: 0 6px 22px rgba(0,0,0,.035); }
.issue-date { align-self: start; display: grid; gap: 10px; }
.issue-date time { font-size: 13px; font-weight: 700; }
.status-pill { width: max-content; padding: 5px 9px; border-radius: 980px; background: var(--red-soft); color: var(--red); font-size: 10px; font-weight: 750; letter-spacing: .03em; text-transform: uppercase; }
.issue-copy h3 { margin-bottom: 4px; overflow-wrap: anywhere; font-size: 19px; letter-spacing: -.015em; }
.issue-copy p { margin-bottom: 8px; color: var(--secondary); font-size: 12px; }
.issue-copy > span { color: #424245; font-size: 12px; line-height: 1.45; }
.issue-counts { display: grid; gap: 7px; color: var(--secondary); font-size: 11px; }
.issue-counts strong { color: var(--red); font-size: 22px; }
.issue-action { display: grid; justify-items: start; gap: 10px; }
.issue-action p { margin: 0; color: #424245; font-size: 12px; line-height: 1.4; }
.issue-action a, .row-link a { color: var(--blue); font-size: 12px; font-weight: 700; text-decoration: none; }
.table-wrap { overflow: hidden; border: 1px solid var(--line-soft); border-radius: 20px; background: var(--surface); }
table { width: 100%; border-collapse: collapse; }
th { padding: 13px 18px; border-bottom: 1px solid var(--line-soft); color: var(--secondary); text-align: left; font-size: 10px; letter-spacing: .05em; text-transform: uppercase; }
td { padding: 18px; border-bottom: 1px solid var(--line-soft); font-size: 13px; }
tr:last-child td { border-bottom: 0; }
td strong, td small { display: block; }
td small { margin-top: 4px; color: var(--secondary); font-size: 11px; }
.number { display: inline-grid; min-width: 28px; height: 28px; place-items: center; border-radius: 8px; font-weight: 750; }
.number.attention { background: var(--red-soft); color: var(--red); }
.number.clear { background: var(--green-soft); color: var(--green); }
.row-link { text-align: right; white-space: nowrap; }
.empty-state { display: flex; align-items: center; gap: 17px; min-height: 126px; padding: 27px; border: 1px solid var(--line-soft); border-radius: 20px; background: var(--surface); }
.empty-state p { margin: 4px 0 0; color: var(--secondary); font-size: 13px; }
.empty-mark { width: 42px; height: 42px; display: grid; place-items: center; border-radius: 50%; background: var(--green-soft); color: var(--green); font-size: 20px; font-weight: 800; }
.table-empty { border: 0; border-radius: 0; }
.permanent-empty td, .permanent-empty.issue-empty { padding: 30px; color: var(--secondary); text-align: center; font-size: 13px; }
.artifact-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.artifact-link { display: flex; min-height: 78px; align-items: center; justify-content: space-between; gap: 14px; padding: 17px 19px; border: 1px solid var(--line-soft); border-radius: 16px; background: var(--surface); text-decoration: none; }
.artifact-link strong, .artifact-link small { display: block; }
.artifact-link strong { font-size: 13px; }
.artifact-link small { margin-top: 4px; color: var(--secondary); font-size: 11px; }
.chevron { color: var(--secondary); font-size: 22px; }
.footer { margin-top: 12px; border-top: 1px solid var(--line-soft); background: var(--surface); }
.footer-inner { min-height: 78px; display: flex; align-items: center; justify-content: space-between; gap: 20px; color: var(--secondary); font-size: 11px; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
@media (max-width: 900px) {
  .filter-panel { grid-template-columns: 1fr; }
  .custom-range { flex-wrap: wrap; }
  .history-issue { grid-template-columns: 120px 1fr 130px; }
  .issue-action { grid-column: 2 / -1; }
}
@media (max-width: 700px) {
  .shell { width: min(100% - 24px, 1120px); }
  .topbar-inner { min-height: 54px; }
  .mode-pill { display: none; }
  .page-heading { padding: 34px 2px 20px; align-items: start; }
  .page-heading .quiet-button { display: none; }
  .updated { max-width: 280px; font-size: 12px; line-height: 1.45; }
  .filter-panel { padding: 17px; border-radius: 18px; }
  .range-chips { display: grid; grid-template-columns: repeat(2, 1fr); }
  .range-chip:last-child { grid-column: 1 / -1; }
  .custom-range { display: grid; grid-template-columns: 1fr 1fr; }
  .custom-range label:last-child { grid-column: 1 / -1; }
  .custom-range input, .custom-range select { width: 100%; max-width: none; }
  .history-hero { min-height: 0; padding: 30px 25px; align-items: start; border-radius: 22px; }
  .history-hero h2 { font-size: 40px; }
  .hero-rate { min-width: 82px; }
  .hero-rate strong { font-size: 42px; }
  .hero-rate span { max-width: 72px; margin-left: auto; font-size: 9px; line-height: 1.3; }
  .definition { margin: 13px 3px 0; }
  .metrics { grid-template-columns: 1fr 1fr; margin-bottom: 46px; }
  .metric { min-height: 108px; padding: 18px; }
  .metric strong { font-size: 30px; }
  .primary-section, .secondary-section { margin-bottom: 44px; }
  .section-heading { align-items: start; }
  .section-heading h2 { font-size: 24px; }
  .history-issue { grid-template-columns: 1fr auto; gap: 16px; padding: 20px; }
  .issue-date { display: flex; align-items: center; justify-content: space-between; grid-column: 1 / -1; }
  .issue-copy { grid-column: 1 / -1; }
  .issue-counts { grid-column: 1; }
  .issue-action { grid-column: 2; justify-items: end; text-align: right; }
  .issue-action p { display: none; }
  .table-wrap { border: 0; background: transparent; overflow: visible; }
  thead { display: none; }
  table, tbody { display: block; }
  .history-day { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 13px; margin-bottom: 10px; padding: 18px; border: 1px solid var(--line-soft); border-radius: 18px; background: var(--surface); }
  .history-day td { display: grid; gap: 3px; padding: 0; border: 0; font-size: 13px; }
  .history-day td::before { content: attr(data-label); color: var(--secondary); font-size: 9px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; }
  .history-day td:first-child { grid-column: 1 / -1; }
  .history-day td:first-child::before, .history-day .row-link::before { display: none; }
  .history-day .row-link { grid-column: 1 / -1; padding-top: 12px; border-top: 1px solid var(--line-soft); text-align: left; }
  .artifact-grid { grid-template-columns: 1fr; }
  .footer-inner { min-height: 94px; flex-direction: column; align-items: start; justify-content: center; }
}
@media (max-width: 430px) {
  h1 { font-size: 34px; }
  .history-hero { display: block; }
  .history-hero h2 { font-size: 38px; }
  .hero-rate { display: flex; align-items: baseline; gap: 8px; margin-top: 24px; text-align: left; }
  .hero-rate span { max-width: none; margin: 0; }
  .section-count { max-width: 75px; text-align: right; line-height: 1.35; }
  .issue-action a { text-align: right; }
}
"""
