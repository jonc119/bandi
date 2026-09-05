from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tomllib


@dataclass(frozen=True, slots=True)
class ProjectConfig:
    mode: str
    timezone: str
    pass_statuses: tuple[str, ...]
    exclusion_keywords: tuple[str, ...]
    database_path: Path
    reports_path: Path
    drafts_path: Path
    logs_path: Path
    warehouse_history_url: str = ""
    shipping_tracking_url: str = ""
    project_mappings: dict[str, str] = field(default_factory=dict)


def load_config(config_path: Path, workspace: Path) -> ProjectConfig:
    with config_path.open("rb") as config_file:
        raw = tomllib.load(config_file)

    deployment = raw.get("deployment", {})
    rules = raw.get("rules", {})
    classification = raw.get("classification", {})
    paths = raw.get("paths", {})
    dashboards = raw.get("dashboards", {})
    mode = str(deployment.get("mode", "shadow")).strip().casefold()
    if mode != "shadow":
        raise ValueError("This release is shadow-only; deployment.mode must be 'shadow'.")

    return ProjectConfig(
        mode=mode,
        timezone=str(deployment.get("timezone", "America/New_York")),
        pass_statuses=tuple(rules.get("pass_statuses", ["Field Received"])),
        exclusion_keywords=tuple(classification.get("exclusion_keywords", ())),
        database_path=_resolve(workspace, paths.get("database", "var/state/delivery_qc.db")),
        reports_path=_resolve(workspace, paths.get("reports", "var/reports")),
        drafts_path=_resolve(workspace, paths.get("drafts", "var/drafts")),
        logs_path=_resolve(workspace, paths.get("logs", "var/logs")),
        warehouse_history_url=str(dashboards.get("warehouse_history_url", "")).strip(),
        shipping_tracking_url=str(dashboards.get("shipping_tracking_url", "")).strip(),
        project_mappings=dict(raw.get("matching", {}).get("project_mappings", {})),
    )


def _resolve(workspace: Path, configured_path: str) -> Path:
    path = Path(configured_path)
    return path if path.is_absolute() else workspace / path
