from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime
import json
from pathlib import Path
import sqlite3

from delivery_qc.domain.models import PackageResult, ResultCode, ScheduleNotice


@dataclass(frozen=True, slots=True)
class HistoricalPackageResult:
    source_uid: str
    project: str
    package_name: str
    result_code: ResultCode
    expected_count: int | None
    observed_count: int
    field_received_count: int
    outstanding_count: int
    follow_up_required: bool


@dataclass(frozen=True, slots=True)
class HistoricalRun:
    run_id: str
    delivery_date: date
    created_at: datetime
    package_count: int
    notice_count: int
    packages: tuple[HistoricalPackageResult, ...]

    @property
    def passed_count(self) -> int:
        return sum(
            package.result_code is ResultCode.PASS_COMPLETE for package in self.packages
        )

    @property
    def issue_count(self) -> int:
        return sum(package.follow_up_required for package in self.packages)

    @property
    def outstanding_count(self) -> int:
        return sum(package.outstanding_count for package in self.packages if package.observed_count)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    delivery_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode = 'shadow'),
    source_hash TEXT NOT NULL,
    status_hash TEXT NOT NULL,
    package_count INTEGER NOT NULL,
    notice_count INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS package_results (
    run_id TEXT NOT NULL,
    source_uid TEXT NOT NULL,
    project TEXT NOT NULL,
    package_name TEXT NOT NULL,
    result_code TEXT NOT NULL,
    reason_codes_json TEXT NOT NULL,
    warnings_json TEXT NOT NULL,
    expected_count INTEGER,
    observed_count INTEGER NOT NULL,
    field_received_count INTEGER NOT NULL,
    outstanding_count INTEGER NOT NULL,
    follow_up_required INTEGER NOT NULL,
    PRIMARY KEY (run_id, source_uid),
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS container_results (
    run_id TEXT NOT NULL,
    source_uid TEXT NOT NULL,
    container_name TEXT NOT NULL,
    status TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    PRIMARY KEY (run_id, source_uid, container_name),
    FOREIGN KEY (run_id, source_uid)
        REFERENCES package_results(run_id, source_uid)
);

CREATE TABLE IF NOT EXISTS schedule_notices (
    run_id TEXT NOT NULL,
    source_uid TEXT NOT NULL,
    summary TEXT NOT NULL,
    classification TEXT NOT NULL,
    reason TEXT NOT NULL,
    PRIMARY KEY (run_id, source_uid),
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS container_evidence (
    run_id TEXT NOT NULL,
    source_uid TEXT NOT NULL,
    evidence_index INTEGER NOT NULL,
    container_id TEXT NOT NULL,
    container_name TEXT NOT NULL,
    status TEXT NOT NULL,
    package_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    PRIMARY KEY (run_id, source_uid, evidence_index),
    FOREIGN KEY (run_id, source_uid) REFERENCES package_results(run_id, source_uid)
);
"""


def persist_run(
    *,
    database_path: Path,
    run_id: str,
    delivery_date: date,
    created_at: datetime,
    source_hash: str,
    status_hash: str,
    results: tuple[PackageResult, ...],
    notices: tuple[ScheduleNotice, ...],
) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database_path)) as connection:
        with connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(_SCHEMA)
            connection.execute(
            """
            INSERT INTO runs (
                run_id, delivery_date, created_at, mode, source_hash, status_hash,
                package_count, notice_count
            ) VALUES (?, ?, ?, 'shadow', ?, ?, ?, ?)
            """,
            (
                run_id,
                delivery_date.isoformat(),
                created_at.isoformat(),
                source_hash,
                status_hash,
                len(results),
                len(notices),
            ),
        )
            for result in results:
                delivery = result.delivery
                connection.execute(
                """
                INSERT INTO package_results (
                    run_id, source_uid, project, package_name, result_code,
                    reason_codes_json, warnings_json, expected_count, observed_count,
                    field_received_count, outstanding_count, follow_up_required
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    delivery.source_uid,
                    delivery.project or (result.containers[0].project if result.containers else ""),
                    delivery.package_name,
                    result.result_code.value,
                    json.dumps(result.reason_codes),
                    json.dumps(result.warnings),
                    result.expected_count,
                    result.observed_count,
                    result.field_received_count,
                    result.outstanding_count,
                    int(result.follow_up_required),
                ),
            )
                connection.executemany(
                """
                INSERT INTO container_results (
                    run_id, source_uid, container_name, status, observed_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    (
                        run_id,
                        delivery.source_uid,
                        container.container_name,
                        container.status,
                        container.observed_at,
                    )
                    for container in result.containers
                    if sum(item.container_name == container.container_name for item in result.containers) == 1
                ),
            )
                connection.executemany(
                    "INSERT INTO container_evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    ((run_id, delivery.source_uid, index, container.container_id,
                      container.container_name, container.status, container.package_id,
                      container.project_id, container.observed_at)
                     for index, container in enumerate(result.containers)),
                )
            connection.executemany(
            """
            INSERT INTO schedule_notices (
                run_id, source_uid, summary, classification, reason
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                (
                    run_id,
                    notice.source_uid,
                    notice.summary,
                    notice.classification.value,
                    notice.reason,
                )
                for notice in notices
            ),
        )


def load_latest_run_history(database_path: Path) -> tuple[HistoricalRun, ...]:
    if not database_path.exists():
        return ()

    with closing(sqlite3.connect(database_path)) as connection:
        connection.row_factory = sqlite3.Row
        run_rows = connection.execute(
            """
            SELECT
                run_id,
                delivery_date,
                created_at,
                package_count,
                notice_count
            FROM runs AS candidate
            WHERE NOT EXISTS (
                SELECT 1
                FROM runs AS newer
                WHERE newer.delivery_date = candidate.delivery_date
                  AND (
                      newer.created_at > candidate.created_at
                      OR (
                          newer.created_at = candidate.created_at
                          AND newer.run_id > candidate.run_id
                      )
                  )
            )
            ORDER BY delivery_date DESC
            """
        ).fetchall()

        history: list[HistoricalRun] = []
        for run_row in run_rows:
            package_rows = connection.execute(
                """
                SELECT
                    source_uid,
                    project,
                    package_name,
                    result_code,
                    expected_count,
                    observed_count,
                    field_received_count,
                    outstanding_count,
                    follow_up_required
                FROM package_results
                WHERE run_id = ?
                ORDER BY package_name COLLATE NOCASE, source_uid
                """,
                (run_row["run_id"],),
            ).fetchall()
            packages = tuple(
                HistoricalPackageResult(
                    source_uid=package_row["source_uid"],
                    project=package_row["project"],
                    package_name=package_row["package_name"],
                    result_code=ResultCode(package_row["result_code"]),
                    expected_count=package_row["expected_count"],
                    observed_count=package_row["observed_count"],
                    field_received_count=package_row["field_received_count"],
                    outstanding_count=package_row["outstanding_count"],
                    follow_up_required=bool(package_row["follow_up_required"]),
                )
                for package_row in package_rows
            )
            history.append(
                HistoricalRun(
                    run_id=run_row["run_id"],
                    delivery_date=date.fromisoformat(run_row["delivery_date"]),
                    created_at=datetime.fromisoformat(run_row["created_at"]),
                    package_count=run_row["package_count"],
                    notice_count=run_row["notice_count"],
                    packages=packages,
                )
            )

    return tuple(history)
