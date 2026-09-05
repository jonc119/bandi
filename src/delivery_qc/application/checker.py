from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

from delivery_qc.adapters.ics_schedule import ParsedSchedule, parse_ics
from delivery_qc.adapters.status_snapshot import read_status_snapshot
from delivery_qc.config import ProjectConfig
from delivery_qc.domain.matching import match_package
from delivery_qc.domain.models import ContainerStatus, PackageResult, ScheduleNotice, MatchResult, EventClassification
from delivery_qc.domain.rules import evaluate_delivery
from delivery_qc.infrastructure.database import load_latest_run_history, persist_run
from delivery_qc.infrastructure.reports import ReportPaths, write_reports


@dataclass(frozen=True, slots=True)
class RunOutcome:
    run_id: str
    delivery_date: date
    results: tuple[PackageResult, ...]
    notices: tuple[ScheduleNotice, ...]
    report_paths: ReportPaths


def run_shadow_check(
    *,
    delivery_date: date,
    ics_path: Path,
    statuses_path: Path | None,
    config: ProjectConfig,
    status_records: tuple[ContainerStatus, ...] | None = None,
    match_records: dict[str, MatchResult] | None = None,
    comparison_ics_path: Path | None = None,
) -> RunOutcome:
    schedule = parse_ics(
        ics_path,
        default_timezone=config.timezone,
        exclusion_keywords=config.exclusion_keywords,
    )
    daily_deliveries = tuple(
        delivery for delivery in schedule.deliveries if delivery.delivery_date == delivery_date
    )
    daily_notices = tuple(
        notice for notice in schedule.notices if notice.delivery_date == delivery_date
    )
    if comparison_ics_path is not None:
        comparison = inspect_schedule(comparison_ics_path, config)
        current = {delivery.source_uid: delivery for delivery in comparison.deliveries if delivery.delivery_date == delivery_date}
        selected = {delivery.source_uid: delivery for delivery in daily_deliveries}
        if current != selected:
            raise ValueError("Calendar snapshots disagree for this delivery date; coverage and cancellations require review.")
    if not daily_deliveries:
        daily_notices += (ScheduleNotice("coverage-unverified", delivery_date,
            "No package entries in supplied snapshot; calendar coverage is unverified",
            EventClassification.REVIEW, "CALENDAR_COVERAGE_UNVERIFIED"),)

    if daily_deliveries:
        if status_records is not None:
            statuses = status_records
        elif statuses_path is None or not statuses_path.exists():
            raise FileNotFoundError(
                "A status snapshot is required when Stratus deliveries are scheduled."
            )
        else:
            statuses = read_status_snapshot(statuses_path)
    else:
        statuses = ()

    results = tuple(
        evaluate_delivery(
            delivery,
            match_records[delivery.source_uid] if match_records is not None else match_package(delivery, statuses),
            config.pass_statuses,
        )
        for delivery in daily_deliveries
    )
    run_id = str(uuid4())
    created_at = datetime.now(timezone.utc)
    source_hash = _file_hash(ics_path)
    status_hash = (
        _status_records_hash(status_records)
        if status_records is not None
        else _file_hash(statuses_path) if statuses_path else ""
    )

    persist_run(
        database_path=config.database_path,
        run_id=run_id,
        delivery_date=delivery_date,
        created_at=created_at,
        source_hash=source_hash,
        status_hash=status_hash,
        results=results,
        notices=daily_notices,
    )
    report_paths = write_reports(
        reports_dir=config.reports_path,
        drafts_dir=config.drafts_path,
        run_id=run_id,
        delivery_date=delivery_date,
        created_at=created_at,
        results=results,
        notices=daily_notices,
        history=load_latest_run_history(config.database_path),
        warehouse_history_url=config.warehouse_history_url,
        shipping_tracking_url=config.shipping_tracking_url,
    )
    return RunOutcome(run_id, delivery_date, results, daily_notices, report_paths)


def inspect_schedule(ics_path: Path, config: ProjectConfig) -> ParsedSchedule:
    return parse_ics(
        ics_path,
        default_timezone=config.timezone,
        exclusion_keywords=config.exclusion_keywords,
    )


def _file_hash(path: Path | None) -> str:
    if path is None:
        return ""
    digest = sha256()
    with path.open("rb") as source_file:
        for block in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _status_records_hash(statuses: tuple[ContainerStatus, ...]) -> str:
    canonical = sorted(
        (
            status.project,
            status.package_name,
            status.container_name,
            status.status,
            status.observed_at,
        )
        for status in statuses
    )
    return sha256(json.dumps(canonical).encode("utf-8")).hexdigest()
