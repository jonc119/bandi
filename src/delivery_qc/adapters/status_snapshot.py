from __future__ import annotations

import csv
from pathlib import Path

from delivery_qc.domain.models import ContainerStatus


_REQUIRED_COLUMNS = {"package_name", "container_name", "status"}


def read_status_snapshot(path: Path) -> tuple[ContainerStatus, ...]:
    with path.open("r", encoding="utf-8-sig", newline="") as snapshot_file:
        reader = csv.DictReader(snapshot_file)
        columns = set(reader.fieldnames or ())
        missing = _REQUIRED_COLUMNS - columns
        if missing:
            raise ValueError(f"Status snapshot is missing required columns: {sorted(missing)}")
        statuses = [
            ContainerStatus(
                project=(row.get("project") or "").strip(),
                package_name=(row.get("package_name") or "").strip(),
                container_name=(row.get("container_name") or "").strip(),
                status=(row.get("status") or "").strip(),
                observed_at=(row.get("observed_at") or "").strip(),
            )
            for row in reader
            if any((value or "").strip() for value in row.values())
        ]
    return tuple(statuses)

