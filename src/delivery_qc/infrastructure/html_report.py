from __future__ import annotations

from datetime import date, datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

from delivery_qc.domain.models import PackageResult, ResultCode, ScheduleNotice
from delivery_qc.domain.normalize import status_matches
from delivery_qc.infrastructure.report_presentation import (
    ACTION_BY_RESULT,
    ISSUE_BY_RESULT,
    LABEL_BY_RESULT,
    STRATUS_ORDERS_URL,
    container_url,
    issue_anchor,
    package_url,
    power_bi_filter_url,
    result_project,
)


_DISPLAY_TIMEZONE = ZoneInfo("America/New_York")


def write_html_report(
    *,
    path: Path,
    run_id: str,
    delivery_date: date,
    created_at: datetime,
    results: tuple[PackageResult, ...],
    notices: tuple[ScheduleNotice, ...],
    warehouse_history_url: str = "",
    shipping_tracking_url: str = "",
    excel_href: str = "delivery-qc-review.xlsx",
    json_href: str = "delivery-qc-report.json",
    markdown_href: str = "delivery-qc-report.md",
    drafts_href: str = "",
    history_href: str = "index.html",
) -> None:
    content = _render_dashboard(
        run_id=run_id,
        delivery_date=delivery_date,
        created_at=created_at,
        results=results,
        notices=notices,
        warehouse_history_url=warehouse_history_url,
        shipping_tracking_url=shipping_tracking_url,
        excel_href=excel_href,
        json_href=json_href,
        markdown_href=markdown_href,
        drafts_href=drafts_href,
        history_href=history_href,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(content, encoding="utf-8")
    temporary_path.replace(path)


def _render_dashboard(
    *,
    run_id: str,
    delivery_date: date,
    created_at: datetime,
    results: tuple[PackageResult, ...],
    notices: tuple[ScheduleNotice, ...],
    warehouse_history_url: str,
    shipping_tracking_url: str,
    excel_href: str,
    json_href: str,
    markdown_href: str,
    drafts_href: str,
    history_href: str,
) -> str:
    passed_results = tuple(
        result for result in results if result.result_code is ResultCode.PASS_COMPLETE
    )
    flagged_results = tuple(result for result in results if result.follow_up_required)
    outstanding = sum(result.outstanding_count for result in results)
    expected = sum(result.expected_count or result.observed_count for result in results)
    received = sum(result.field_received_count for result in results)

    if flagged_results:
        hero_tone = "attention"
        hero_eyebrow = "Action required"
        hero_title = (
            f"{len(flagged_results)} {_plural(len(flagged_results), 'package')} "
            f"{'needs' if len(flagged_results) == 1 else 'need'} attention"
        )
        hero_copy = (
            f"{outstanding} {_plural(outstanding, 'container')} "
            f"{'remains' if outstanding == 1 else 'remain'} unresolved. "
            "Open the first issue and follow the direct source links."
        )
    elif results:
        hero_tone = "clear"
        hero_eyebrow = "Matched packages received"
        hero_title = "Matched package checks passed"
        hero_copy = "All expected containers in these matches are Field Received. Review calendar notices for coverage gaps."
    else:
        hero_tone = "neutral"
        hero_eyebrow = "Coverage unverified"
        hero_title = "No package entries in this snapshot"
        hero_copy = "This does not establish that no deliveries were scheduled. Verify calendar coverage."

    issue_cards = "".join(
        _issue_card(
            result,
            warehouse_history_url=warehouse_history_url,
            shipping_tracking_url=shipping_tracking_url,
        )
        for result in flagged_results
    )
    if not issue_cards:
        issue_cards = (
            '<div class="empty-state">'
            '<span class="empty-mark" aria-hidden="true">✓</span>'
            '<div><strong>Nothing needs investigation</strong>'
            '<p>There are no unresolved package or container statuses.</p></div>'
            "</div>"
        )

    cleared_rows = "".join(_cleared_row(result) for result in passed_results)
    if not cleared_rows:
        cleared_rows = '<p class="muted inset">No packages are cleared for this date.</p>'

    excluded_note = ""
    if notices:
        excluded_note = (
            f'<span>{len(notices)} other {_plural(len(notices), "calendar event")} '
            'need classification review or were explicitly excluded; see JSON/text evidence.</span>'
        )

    artifact_links = [
        _artifact_link(excel_href, "Excel audit", "Spreadsheet export"),
        _artifact_link(json_href, "JSON evidence", "Machine-readable audit"),
        _artifact_link(markdown_href, "Text report", "Plain-language summary"),
    ]
    if drafts_href and flagged_results:
        artifact_links.append(
            _artifact_link(drafts_href, "Draft follow-ups", "Prepared, never sent")
        )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'; object-src 'none'">
  <title>Delivery QC · {_e(delivery_date.isoformat())}</title>
  <style>{_STYLES}</style>
</head>
<body>
  <header class="topbar">
    <div class="shell topbar-inner">
      <a class="brand" href="{_attr(history_href)}" aria-label="Delivery QC history">
        <span class="brand-mark" aria-hidden="true">DQ</span>
        <span>Delivery QC</span>
      </a>
      <div class="topbar-actions">
        <a class="nav-link" href="{_attr(history_href)}">History</a>
        <span class="mode-pill">Shadow mode · No emails sent</span>
      </div>
    </div>
  </header>

  <main id="top" class="shell">
    <section class="page-heading" aria-labelledby="page-title">
      <div>
        <p class="eyebrow">Daily review</p>
        <h1 id="page-title">{_e(_format_date(delivery_date))}</h1>
        <p class="updated">Checked {_e(_format_time(created_at))}</p>
        <p class="updated">Current status snapshot — not proof of receipt by the scheduled cutoff.</p>
      </div>
      <a class="quiet-button" href="{_attr(excel_href)}">Download Excel</a>
    </section>

    <section class="hero {hero_tone}" aria-label="Delivery status">
      <div>
        <p class="eyebrow">{_e(hero_eyebrow)}</p>
        <h2>{_e(hero_title)}</h2>
        <p>{_e(hero_copy)}</p>
      </div>
      <div class="hero-count" aria-label="{len(flagged_results)} flagged {_plural(len(flagged_results), 'package')}">
        {len(flagged_results)}
      </div>
    </section>

    <section class="metrics" aria-label="Daily totals">
      {_metric("Scheduled", len(results), _plural(len(results), "package"))}
      {_metric("Cleared", len(passed_results), _plural(len(passed_results), "package"))}
      {_metric("Received", received, f"of {expected} containers")}
      {_metric("Known outstanding", outstanding, "unverified matches excluded", attention=bool(outstanding))}
    </section>

    <section class="primary-section" aria-labelledby="attention-title">
      <div class="section-heading">
        <div>
          <p class="eyebrow">Start here</p>
          <h2 id="attention-title">Needs attention</h2>
        </div>
        <span class="section-count">{len(flagged_results)} {_plural(len(flagged_results), "package")}</span>
      </div>
      <div class="issue-list">{issue_cards}</div>
    </section>

    <section class="secondary-section" aria-labelledby="cleared-title">
      <details class="disclosure">
        <summary>
          <span>
            <span class="eyebrow">Verified</span>
            <strong id="cleared-title">Cleared packages</strong>
          </span>
          <span class="summary-meta">{len(passed_results)} {_plural(len(passed_results), "package")} <span class="chevron">›</span></span>
        </summary>
        <div class="cleared-list">{cleared_rows}</div>
      </details>
    </section>

    <section class="secondary-section" aria-labelledby="exports-title">
      <div class="section-heading compact">
        <div>
          <p class="eyebrow">Evidence</p>
          <h2 id="exports-title">Audit &amp; exports</h2>
        </div>
      </div>
      <div class="artifact-grid">{"".join(artifact_links)}</div>
    </section>
  </main>

  <footer class="footer">
    <div class="shell footer-inner">
      <span>PASS requires every expected container to be Field Received.</span>
      {excluded_note}
      <span>Run <code>{_e(run_id)}</code></span>
    </div>
  </footer>
</body>
</html>
"""


def _issue_card(
    result: PackageResult,
    *,
    warehouse_history_url: str,
    shipping_tracking_url: str,
) -> str:
    project = result_project(result) or "Project not identified"
    package_name = result.delivery.package_name
    expected = result.expected_count
    denominator = expected if expected is not None else result.observed_count
    package_href = package_url(result)
    warehouse_href = power_bi_filter_url(
        warehouse_history_url,
        "Package/Name",
        package_name,
    )
    package_actions = [
        _source_link(
            package_href or STRATUS_ORDERS_URL,
            "Open Stratus package" if package_href else "Search Stratus",
            primary=True,
        ),
        _source_link(warehouse_href, "Warehouse history"),
    ]

    unresolved = tuple(
        container
        for container in result.containers
        if not status_matches(container.status, ("Field Received",))
    )
    container_rows = "".join(
        _unresolved_container(
            container_name=container.container_name,
            status=container.status,
            stratus_href=container_url(container.container_id),
            shipping_href=power_bi_filter_url(
                shipping_tracking_url,
                "Part/Container_x002E_Name",
                container.container_name,
            ),
        )
        for container in unresolved
    )
    if not container_rows:
        shipping_href = power_bi_filter_url(
            shipping_tracking_url,
            "Calendar/Package_x0020_Name",
            package_name,
        )
        container_rows = (
            '<div class="unresolved-row package-level">'
            '<div><span class="row-label">Package-level exception</span>'
            f'<span class="row-status">{_e(ISSUE_BY_RESULT[result.result_code])}</span></div>'
            f'<div class="row-actions">{_source_link(shipping_href, "Shipping view")}</div>'
            "</div>"
        )

    reason_text = ", ".join(result.reason_codes) or "None"
    warning_text = ", ".join(result.warnings) or "None"
    expected_text = "Unknown" if expected is None else str(expected)
    unverified = not result.containers
    received_text = "Receipt unverified" if unverified else f"{result.field_received_count} of {denominator} received"
    outstanding_text = "?" if unverified else str(result.outstanding_count)
    evidence = (
        f"Expected {expected_text}; found {result.observed_count}; "
        + ("Receipt and outstanding quantities unverified." if unverified else
         f"Field Received {result.field_received_count}; outstanding {result.outstanding_count}.")
    )

    return f"""
      <article class="issue-card" id="{_attr(issue_anchor(result.delivery.source_uid))}">
        <div class="issue-topline">
          <span class="status-pill">{_e(LABEL_BY_RESULT[result.result_code])}</span>
          <span class="progress">{received_text}</span>
        </div>
        <div class="issue-heading">
          <div>
            <h3>{_e(package_name)}</h3>
            <p>{_e(project)}</p>
          </div>
          <span class="outstanding-number" aria-label="{outstanding_text} outstanding">
            {outstanding_text}<small>{'unverified' if unverified else 'outstanding'}</small>
          </span>
        </div>
        <div class="guidance">
          <div><span>What happened</span><p>{_e(ISSUE_BY_RESULT[result.result_code])}</p></div>
          <div><span>Next step</span><p>{_e(ACTION_BY_RESULT[result.result_code])}</p></div>
        </div>
        <div class="package-actions">{"".join(package_actions)}</div>
        <div class="unresolved-list">
          <p class="list-label">Items to investigate</p>
          {container_rows}
        </div>
        <details class="evidence">
          <summary>Show audit evidence</summary>
          <div>
            <p>{_e(evidence)}</p>
            <p><strong>Reason codes:</strong> {_e(reason_text)}</p>
            <p><strong>Warnings:</strong> {_e(warning_text)}</p>
          </div>
        </details>
      </article>
    """


def _unresolved_container(
    *,
    container_name: str,
    status: str,
    stratus_href: str,
    shipping_href: str,
) -> str:
    return f"""
      <div class="unresolved-row">
        <div>
          <span class="row-label">{_e(container_name)}</span>
          <span class="row-status">{_e(status or "Status unavailable")}</span>
        </div>
        <div class="row-actions">
          {_source_link(stratus_href, "Stratus")}
          {_source_link(shipping_href, "Shipping")}
        </div>
      </div>
    """


def _cleared_row(result: PackageResult) -> str:
    href = package_url(result)
    link = _source_link(href, "Open package") if href else ""
    expected = result.expected_count if result.expected_count is not None else result.observed_count
    return f"""
      <div class="cleared-row">
        <span class="clear-mark" aria-hidden="true">✓</span>
        <div>
          <strong>{_e(result.delivery.package_name)}</strong>
          <span>{_e(result_project(result) or "Project not identified")}</span>
        </div>
        <span class="received-count">{result.field_received_count}/{expected} received</span>
        {link}
      </div>
    """


def _source_link(href: str, label: str, *, primary: bool = False) -> str:
    if not href:
        return '<span class="source-link disabled">Unavailable</span>'
    class_name = "source-link primary" if primary else "source-link"
    return (
        f'<a class="{class_name}" href="{_attr(href)}" target="_blank" '
        f'rel="noopener noreferrer">{_e(label)} <span aria-hidden="true">↗</span></a>'
    )


def _artifact_link(href: str, title: str, subtitle: str) -> str:
    return f"""
      <a class="artifact-link" href="{_attr(href)}">
        <span><strong>{_e(title)}</strong><small>{_e(subtitle)}</small></span>
        <span class="chevron" aria-hidden="true">›</span>
      </a>
    """


def _metric(label: str, value: int, detail: str, *, attention: bool = False) -> str:
    class_name = "metric attention" if attention else "metric"
    return f"""
      <div class="{class_name}">
        <span>{_e(label)}</span>
        <strong>{value}</strong>
        <small>{_e(detail)}</small>
      </div>
    """


def _format_date(value: date) -> str:
    return value.strftime("%A, %B %d, %Y").replace(" 0", " ")


def _plural(value: int, singular: str) -> str:
    return singular if value == 1 else f"{singular}s"


def _format_time(value: datetime) -> str:
    if value.tzinfo is not None:
        value = value.astimezone(_DISPLAY_TIMEZONE)
    return value.strftime("%I:%M %p ET").lstrip("0")


def _e(value: object) -> str:
    return escape(str(value))


def _attr(value: object) -> str:
    return escape(str(value), quote=True)


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
  --amber: #8a4b00;
  --amber-soft: #fff8e8;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
  font-synthesis: none;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body { margin: 0; background: var(--canvas); color: var(--ink); }
a { color: inherit; }
.shell { width: min(1120px, calc(100% - 40px)); margin: 0 auto; }
.topbar { background: rgba(255,255,255,.9); border-bottom: 1px solid var(--line-soft); }
.topbar-inner { min-height: 58px; display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.brand { display: inline-flex; align-items: center; gap: 10px; text-decoration: none; font-weight: 650; letter-spacing: -.01em; }
.brand-mark { width: 30px; height: 30px; display: grid; place-items: center; border-radius: 9px; background: var(--ink); color: white; font-size: 11px; letter-spacing: .04em; }
.topbar-actions { display: flex; align-items: center; gap: 18px; }
.nav-link { color: var(--blue); font-size: 13px; font-weight: 650; text-decoration: none; }
.nav-link:hover { color: var(--blue-hover); }
.mode-pill { color: var(--secondary); font-size: 12px; font-weight: 600; }
.page-heading { padding: 54px 0 28px; display: flex; align-items: end; justify-content: space-between; gap: 20px; }
.eyebrow { margin: 0 0 7px; color: var(--secondary); font-size: 12px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
h1, h2, h3, p { margin-top: 0; }
h1 { margin-bottom: 6px; font-size: clamp(30px, 5vw, 48px); line-height: 1.05; letter-spacing: -.035em; }
.updated { margin: 0; color: var(--secondary); font-size: 14px; }
.quiet-button { border: 1px solid var(--line); border-radius: 980px; padding: 10px 16px; background: var(--surface); color: var(--blue); font-size: 13px; font-weight: 650; text-decoration: none; }
.quiet-button:hover { border-color: #b6b6bb; background: #fbfbfd; }
.hero { min-height: 210px; padding: 38px 42px; border-radius: 28px; display: flex; align-items: center; justify-content: space-between; gap: 32px; overflow: hidden; }
.hero.attention { background: var(--red-soft); }
.hero.clear { background: var(--green-soft); }
.hero.neutral { background: var(--surface); border: 1px solid var(--line-soft); }
.hero h2 { max-width: 690px; margin-bottom: 12px; font-size: clamp(30px, 5vw, 50px); line-height: 1.03; letter-spacing: -.04em; }
.hero p:last-child { max-width: 640px; margin-bottom: 0; color: #424245; font-size: 16px; line-height: 1.5; }
.hero.attention .eyebrow, .hero.attention .hero-count { color: var(--red); }
.hero.clear .eyebrow, .hero.clear .hero-count { color: var(--green); }
.hero-count { flex: 0 0 auto; min-width: 120px; text-align: center; font-size: clamp(72px, 11vw, 126px); font-weight: 700; line-height: .8; letter-spacing: -.07em; }
.metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1px; margin: 24px 0 62px; overflow: hidden; border: 1px solid var(--line-soft); border-radius: 20px; background: var(--line-soft); }
.metric { min-height: 132px; padding: 23px 25px; background: var(--surface); }
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
.issue-list { display: grid; gap: 18px; }
.issue-card { padding: 30px; scroll-margin-top: 24px; border: 1px solid var(--line-soft); border-radius: 24px; background: var(--surface); box-shadow: 0 8px 28px rgba(0,0,0,.04); }
.issue-topline { display: flex; justify-content: space-between; align-items: center; gap: 14px; margin-bottom: 15px; }
.status-pill { display: inline-flex; align-items: center; min-height: 26px; padding: 5px 10px; border-radius: 980px; background: var(--red-soft); color: var(--red); font-size: 11px; font-weight: 750; letter-spacing: .03em; text-transform: uppercase; }
.progress { color: var(--secondary); font-size: 12px; font-weight: 600; }
.issue-heading { display: flex; align-items: start; justify-content: space-between; gap: 24px; }
.issue-heading h3 { margin-bottom: 6px; overflow-wrap: anywhere; font-size: clamp(22px, 4vw, 32px); letter-spacing: -.025em; }
.issue-heading p { margin-bottom: 0; color: var(--secondary); font-size: 13px; }
.outstanding-number { flex: 0 0 auto; color: var(--red); text-align: right; font-size: 32px; font-weight: 700; line-height: 1; letter-spacing: -.04em; }
.outstanding-number small { display: block; margin-top: 5px; color: var(--secondary); font-size: 10px; font-weight: 650; letter-spacing: .02em; text-transform: uppercase; }
.guidance { display: grid; grid-template-columns: 1fr 1fr; gap: 1px; margin: 25px 0 20px; overflow: hidden; border: 1px solid var(--line-soft); border-radius: 16px; background: var(--line-soft); }
.guidance > div { padding: 17px 19px; background: #fbfbfd; }
.guidance span { color: var(--secondary); font-size: 11px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; }
.guidance p { margin: 6px 0 0; font-size: 14px; line-height: 1.45; }
.package-actions, .row-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.package-actions { margin-bottom: 25px; }
.source-link { display: inline-flex; align-items: center; justify-content: center; min-height: 34px; padding: 8px 12px; border: 1px solid var(--line); border-radius: 980px; background: var(--surface); color: var(--blue); font-size: 12px; font-weight: 650; text-decoration: none; white-space: nowrap; }
.source-link:hover { border-color: var(--blue); color: var(--blue-hover); }
.source-link.primary { border-color: var(--blue); background: var(--blue); color: white; }
.source-link.primary:hover { background: var(--blue-hover); }
.source-link.disabled { color: #99999f; cursor: default; }
.list-label { margin-bottom: 8px; color: var(--secondary); font-size: 11px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; }
.unresolved-list { border-top: 1px solid var(--line-soft); padding-top: 20px; }
.unresolved-row { display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 14px 0; border-bottom: 1px solid var(--line-soft); }
.unresolved-row:last-child { border-bottom: 0; }
.row-label, .row-status { display: block; }
.row-label { font-size: 14px; font-weight: 700; }
.row-status { margin-top: 4px; color: var(--red); font-size: 12px; }
.evidence { margin-top: 18px; color: var(--secondary); font-size: 12px; }
.evidence summary { cursor: pointer; color: var(--blue); font-weight: 650; }
.evidence > div { margin-top: 11px; padding: 13px 15px; border-radius: 12px; background: var(--canvas); }
.evidence p { margin-bottom: 5px; line-height: 1.45; }
.evidence p:last-child { margin-bottom: 0; }
.empty-state { display: flex; align-items: center; gap: 17px; min-height: 130px; padding: 28px; border: 1px solid var(--line-soft); border-radius: 22px; background: var(--surface); }
.empty-state p { margin: 4px 0 0; color: var(--secondary); font-size: 13px; }
.empty-mark { width: 44px; height: 44px; display: grid; place-items: center; border-radius: 50%; background: var(--green-soft); color: var(--green); font-size: 20px; font-weight: 750; }
.disclosure { overflow: hidden; border: 1px solid var(--line-soft); border-radius: 22px; background: var(--surface); }
.disclosure > summary { min-height: 88px; padding: 20px 26px; display: flex; align-items: center; justify-content: space-between; gap: 20px; cursor: pointer; list-style: none; }
.disclosure > summary::-webkit-details-marker { display: none; }
.disclosure > summary strong { display: block; font-size: 20px; }
.summary-meta { color: var(--secondary); font-size: 13px; }
.chevron { display: inline-block; margin-left: 6px; color: var(--secondary); font-size: 24px; line-height: .7; }
.disclosure[open] .chevron { transform: rotate(90deg); }
.cleared-list { border-top: 1px solid var(--line-soft); }
.cleared-row { min-height: 70px; display: grid; grid-template-columns: 28px minmax(0,1fr) auto auto; align-items: center; gap: 14px; padding: 12px 24px; border-bottom: 1px solid var(--line-soft); }
.cleared-row:last-child { border-bottom: 0; }
.cleared-row strong, .cleared-row span { display: block; }
.cleared-row strong { overflow-wrap: anywhere; font-size: 13px; }
.cleared-row div > span { margin-top: 3px; color: var(--secondary); font-size: 11px; }
.clear-mark { width: 23px; height: 23px; display: grid !important; place-items: center; border-radius: 50%; background: var(--green-soft); color: var(--green); font-size: 12px; font-weight: 750; }
.received-count { color: var(--secondary); font-size: 12px; white-space: nowrap; }
.artifact-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
.artifact-link { min-height: 78px; display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 17px 20px; border: 1px solid var(--line-soft); border-radius: 16px; background: var(--surface); text-decoration: none; }
.artifact-link:hover { border-color: #b6b6bb; }
.artifact-link strong, .artifact-link small { display: block; }
.artifact-link strong { font-size: 14px; }
.artifact-link small { margin-top: 4px; color: var(--secondary); font-size: 11px; }
.footer { margin-top: 74px; border-top: 1px solid var(--line-soft); background: var(--surface); }
.footer-inner { min-height: 108px; display: flex; flex-wrap: wrap; align-items: center; gap: 10px 22px; color: var(--secondary); font-size: 11px; }
.footer code { overflow-wrap: anywhere; color: #515154; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }
.muted { color: var(--secondary); }
.inset { padding: 20px 24px; }
@media (max-width: 760px) {
  .shell { width: min(100% - 28px, 1120px); }
  .topbar-inner { min-height: 54px; }
  .mode-pill { max-width: 150px; text-align: right; font-size: 10px; }
  .page-heading { padding: 34px 0 22px; align-items: start; }
  .quiet-button { display: none; }
  .hero { min-height: 0; padding: 28px 24px; border-radius: 22px; }
  .hero-count { display: none; }
  .metrics { grid-template-columns: 1fr 1fr; margin-bottom: 46px; }
  .metric { min-height: 112px; padding: 18px; }
  .metric strong { font-size: 30px; }
  .issue-card { padding: 22px 18px; border-radius: 20px; }
  .issue-heading { display: block; }
  .outstanding-number { display: inline-flex; align-items: baseline; gap: 7px; margin-top: 17px; text-align: left; }
  .outstanding-number small { display: inline; }
  .guidance { grid-template-columns: 1fr; }
  .unresolved-row { align-items: start; flex-direction: column; }
  .row-actions { width: 100%; }
  .row-actions .source-link { flex: 1; }
  .cleared-row { grid-template-columns: 28px minmax(0,1fr); }
  .cleared-row .received-count, .cleared-row .source-link { grid-column: 2; width: fit-content; }
  .artifact-grid { grid-template-columns: 1fr; }
  .footer-inner { padding: 22px 0; align-items: start; flex-direction: column; }
}
@media print {
  body { background: white; }
  .topbar, .quiet-button, .package-actions, .row-actions, .artifact-grid { display: none; }
  .hero, .issue-card, .disclosure { box-shadow: none; break-inside: avoid; }
  .shell { width: 100%; }
}
"""
