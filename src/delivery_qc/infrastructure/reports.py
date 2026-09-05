from __future__ import annotations

from delivery_qc.infrastructure.export_safety import SafeCsvWriter
from dataclasses import asdict, dataclass
from datetime import date, datetime
import json
from pathlib import Path
import re

from delivery_qc.domain.models import PackageResult, ResultCode, ScheduleNotice
from delivery_qc.domain.normalize import status_matches
from delivery_qc.infrastructure.database import HistoricalRun
from delivery_qc.infrastructure.excel_report import write_excel_report
from delivery_qc.infrastructure.history_report import write_history_reports
from delivery_qc.infrastructure.html_report import write_html_report


@dataclass(frozen=True, slots=True)
class ReportPaths:
    markdown: Path
    json: Path
    csv: Path
    excel: Path
    html: Path
    drafts: tuple[Path, ...]
    latest_markdown: Path
    latest_json: Path
    latest_excel: Path
    latest_html: Path
    index_html: Path
    history_json: Path
    history_csv: Path
    latest_drafts: Path


@dataclass(frozen=True, slots=True)
class HistoryReportPaths:
    html: Path
    json: Path
    csv: Path


def write_reports(
    *,
    reports_dir: Path,
    drafts_dir: Path,
    run_id: str,
    delivery_date: date,
    created_at: datetime,
    results: tuple[PackageResult, ...],
    notices: tuple[ScheduleNotice, ...],
    history: tuple[HistoricalRun, ...],
    warehouse_history_url: str = "",
    shipping_tracking_url: str = "",
) -> ReportPaths:
    run_dir = reports_dir / delivery_date.isoformat() / run_id
    draft_dir = drafts_dir / delivery_date.isoformat() / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    markdown_path = run_dir / "delivery-qc-report.md"
    json_path = run_dir / "delivery-qc-report.json"
    csv_path = run_dir / "delivery-qc-results.csv"
    excel_path = run_dir / "delivery-qc-review.xlsx"
    html_path = run_dir / "delivery-qc-dashboard.html"

    markdown_path.write_text(
        _markdown_report(run_id, delivery_date, created_at, results, notices),
        encoding="utf-8",
    )
    json_path.write_text(
        json.dumps(
            _json_report(run_id, delivery_date, created_at, results, notices),
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_csv(csv_path, results)
    write_excel_report(
        path=excel_path,
        run_id=run_id,
        delivery_date=delivery_date,
        created_at=created_at,
        results=results,
        warehouse_history_url=warehouse_history_url,
        shipping_tracking_url=shipping_tracking_url,
    )
    write_html_report(
        path=html_path,
        run_id=run_id,
        delivery_date=delivery_date,
        created_at=created_at,
        results=results,
        notices=notices,
        warehouse_history_url=warehouse_history_url,
        shipping_tracking_url=shipping_tracking_url,
        history_href="../../index.html",
    )

    draft_paths: list[Path] = []
    flagged = tuple(result for result in results if result.follow_up_required)
    if flagged:
        draft_dir.mkdir(parents=True, exist_ok=False)
        for index, result in enumerate(flagged, start=1):
            safe_name = _safe_filename(result.delivery.package_name)
            draft_path = draft_dir / f"{index:02d}-{safe_name}-follow-up.md"
            draft_path.write_text(_follow_up_draft(result, delivery_date), encoding="utf-8")
            draft_paths.append(draft_path)

    latest_markdown = reports_dir / "latest-delivery-qc-report.md"
    latest_json = reports_dir / "latest-delivery-qc-report.json"
    latest_excel = reports_dir / "latest-delivery-qc-review.xlsx"
    latest_html = reports_dir / "latest-delivery-qc-dashboard.html"
    latest_drafts = drafts_dir / "latest-follow-up-drafts.md"
    _atomic_write(latest_markdown, markdown_path.read_text(encoding="utf-8"))
    _atomic_write(latest_json, json_path.read_text(encoding="utf-8"))
    _atomic_copy(latest_excel, excel_path)
    write_html_report(
        path=latest_html,
        run_id=run_id,
        delivery_date=delivery_date,
        created_at=created_at,
        results=results,
        notices=notices,
        warehouse_history_url=warehouse_history_url,
        shipping_tracking_url=shipping_tracking_url,
        excel_href="latest-delivery-qc-review.xlsx",
        json_href="latest-delivery-qc-report.json",
        markdown_href="latest-delivery-qc-report.md",
        history_href="index.html",
    )
    history_paths = refresh_history_reports(
        reports_dir=reports_dir,
        history=history,
        generated_at=created_at,
    )
    _atomic_write(
        latest_drafts,
        _combined_drafts(delivery_date, tuple(draft_paths)),
    )

    return ReportPaths(
        markdown=markdown_path,
        json=json_path,
        csv=csv_path,
        excel=excel_path,
        html=html_path,
        drafts=tuple(draft_paths),
        latest_markdown=latest_markdown,
        latest_json=latest_json,
        latest_excel=latest_excel,
        latest_html=latest_html,
        index_html=history_paths.html,
        history_json=history_paths.json,
        history_csv=history_paths.csv,
        latest_drafts=latest_drafts,
    )


def refresh_history_reports(
    *,
    reports_dir: Path,
    history: tuple[HistoricalRun, ...],
    generated_at: datetime,
) -> HistoryReportPaths:
    paths = HistoryReportPaths(
        html=reports_dir / "index.html",
        json=reports_dir / "delivery-qc-history.json",
        csv=reports_dir / "delivery-qc-history.csv",
    )
    write_history_reports(
        html_path=paths.html,
        json_path=paths.json,
        csv_path=paths.csv,
        history=history,
        generated_at=generated_at,
    )
    return paths


def _markdown_report(
    run_id: str,
    delivery_date: date,
    created_at: datetime,
    results: tuple[PackageResult, ...],
    notices: tuple[ScheduleNotice, ...],
) -> str:
    passed = sum(result.result_code is ResultCode.PASS_COMPLETE for result in results)
    flagged = len(results) - passed
    lines = [
        "# Delivery QC Report",
        "",
        "> **SHADOW MODE — REVIEW ONLY — NO EMAILS SENT**",
        "",
        f"- Delivery date: {delivery_date.isoformat()}",
        f"- Run ID: `{run_id}`",
        f"- Created: {created_at.isoformat()}",
        f"- Scheduled Stratus packages: {len(results)}",
        f"- Passed: {passed}",
        f"- Flagged for review: {flagged}",
        "",
    ]
    if not results:
        lines.extend(
            [
                "## Outcome",
                "",
                "No Stratus deliveries found in this snapshot; calendar coverage is unverified.",
                "",
            ]
        )
    else:
        lines.extend(["## Package Results", ""])
        for result in results:
            delivery = result.delivery
            project = _result_project(result)
            expected = "not provided" if result.expected_count is None else str(result.expected_count)
            lines.extend(
                [
                    f"### {delivery.package_name}",
                    "",
                    f"- Project: {project or 'not provided'}",
                    f"- Result: **{result.result_code.value}**",
                    f"- Containers: {result.field_received_count} Field Received / "
                    f"{result.observed_count} observed / {expected} expected",
                    f"- Follow-up draft required: {'yes' if result.follow_up_required else 'no'}",
                    f"- Reasons: {', '.join(result.reason_codes) or 'none'}",
                    f"- Warnings: {', '.join(result.warnings) or 'none'}",
                    "",
                ]
            )
            if result.containers:
                lines.extend(["| Container | Status |", "|---|---|"])
                lines.extend(
                    f"| {_table_value(container.container_name)} | {_table_value(container.status)} |"
                    for container in result.containers
                )
                lines.append("")

    if notices:
        lines.extend(["## Other Calendar Events", ""])
        for notice in notices:
            lines.append(
                f"- `{notice.classification.value}` — {notice.summary or '(no summary)'} "
                f"({notice.reason})"
            )
        lines.append("")

    lines.extend(
        [
            "## Safety",
            "",
            "This run read its configured schedule and status sources and wrote local review "
            "artifacts only. It did not send email or modify Stratus or any company system.",
            "",
        ]
    )
    return "\n".join(lines)


def _json_report(
    run_id: str,
    delivery_date: date,
    created_at: datetime,
    results: tuple[PackageResult, ...],
    notices: tuple[ScheduleNotice, ...],
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "mode": "shadow",
        "emails_sent": False,
        "run_id": run_id,
        "delivery_date": delivery_date.isoformat(),
        "created_at": created_at.isoformat(),
        "status_basis": "Current observation, not historical receipt-time evidence",
        "summary": {
            "scheduled_packages": len(results),
            "passed": sum(result.result_code is ResultCode.PASS_COMPLETE for result in results),
            "flagged": sum(result.follow_up_required for result in results),
            "calendar_review_count": sum(notice.classification.value == "REVIEW_UNCLASSIFIED" for notice in notices),
        },
        "results": [_result_dict(result) for result in results],
        "notices": [
            {
                "source_uid": notice.source_uid,
                "summary": notice.summary,
                "classification": notice.classification.value,
                "reason": notice.reason,
            }
            for notice in notices
        ],
    }


def _result_dict(result: PackageResult) -> dict[str, object]:
    delivery = asdict(result.delivery)
    delivery["delivery_date"] = result.delivery.delivery_date.isoformat()
    return {
        "delivery": delivery,
        "result_code": result.result_code.value,
        "reason_codes": list(result.reason_codes),
        "warnings": list(result.warnings),
        "expected_count": result.expected_count,
        "observed_count": result.observed_count,
        "receipt_verified": bool(result.containers),
        "field_received_count": result.field_received_count,
        "outstanding_count": result.outstanding_count,
        "follow_up_required": result.follow_up_required,
        "containers": [asdict(container) for container in result.containers],
    }


def _write_csv(path: Path, results: tuple[PackageResult, ...]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = SafeCsvWriter(csv_file)
        writer.writerow(
            [
                "delivery_date",
                "project",
                "package_name",
                "result_code",
                "expected_count",
                "observed_count",
                "field_received_count",
                "outstanding_count",
                "follow_up_required",
                "reason_codes",
                "warnings",
            ]
        )
        for result in results:
            writer.writerow(
                [
                    result.delivery.delivery_date.isoformat(),
                    _result_project(result),
                    result.delivery.package_name,
                    result.result_code.value,
                    result.expected_count if result.expected_count is not None else "",
                    result.observed_count,
                    result.field_received_count if result.containers else "Unverified",
                    result.outstanding_count if result.containers else "Unverified",
                    "yes" if result.follow_up_required else "no",
                    ";".join(result.reason_codes),
                    ";".join(result.warnings),
                ]
            )


def _follow_up_draft(result: PackageResult, delivery_date: date) -> str:
    delivery = result.delivery
    project = _result_project(result)
    non_received = [
        container.container_name
        for container in result.containers
        if not status_matches(container.status, ("Field Received",))
    ]
    received_names = {
        container.container_name.casefold().strip()
        for container in result.containers
        if status_matches(container.status, ("Field Received",))
    }
    missing_expected = [
        name
        for name in delivery.expected_container_names
        if name.casefold().strip() not in received_names
    ]
    outstanding = list(dict.fromkeys([*missing_expected, *non_received]))
    outstanding_text = ", ".join(outstanding) or "the remaining expected containers"
    verified_nonreceipt = result.result_code in (ResultCode.FLAG_PARTIAL_DELIVERY, ResultCode.FLAG_NOT_RECEIVED)
    finding = "is not fully Field Received in the current snapshot" if verified_nonreceipt else "has unresolved matching, count, or status evidence"
    request = "Please confirm when the remaining containers are expected to be delivered." if verified_nonreceipt else "Please verify the package identity and expected inventory before concluding a delivery was missed."
    return "\n".join(
        [
            "# SHADOW MODE — PROPOSED EMAIL — NOT SENT",
            "",
            f"Subject: Delivery follow-up — {delivery.package_name}",
            "",
            "Hello,",
            "",
            f"Our delivery QC review for {delivery_date.isoformat()} shows that package "
            f"{delivery.package_name} for {project or 'the project'} {finding}.",
            "",
            f"Outstanding or unresolved: {outstanding_text}.",
            "",
            request,
            "",
            "Thank you,",
            "",
            "[Sender name]",
            "",
            f"Internal reason: {result.result_code.value}; "
            f"{', '.join(result.reason_codes) or 'no reason code'}",
            "",
        ]
    )


def _result_project(result: PackageResult) -> str:
    if result.delivery.project:
        return result.delivery.project
    return result.containers[0].project if result.containers else ""


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-.")
    return cleaned[:80] or "package"


def _table_value(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _combined_drafts(delivery_date: date, draft_paths: tuple[Path, ...]) -> str:
    lines = [
        "# SHADOW MODE — PROPOSED FOLLOW-UPS — NOT SENT",
        "",
        f"Delivery date: {delivery_date.isoformat()}",
        "",
    ]
    if not draft_paths:
        lines.extend(["No follow-up drafts were required for this run.", ""])
        return "\n".join(lines)

    for index, draft_path in enumerate(draft_paths, start=1):
        lines.extend(
            [
                f"## Draft {index}",
                "",
                draft_path.read_text(encoding="utf-8").strip(),
                "",
            ]
        )
    return "\n".join(lines)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(content, encoding="utf-8")
    temporary_path.replace(path)


def _atomic_copy(path: Path, source: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_bytes(source.read_bytes())
    temporary_path.replace(path)
