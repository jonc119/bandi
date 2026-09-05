from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path

from delivery_qc.adapters.stratus_api import StratusReadOnlyClient
from delivery_qc.application.checker import inspect_schedule, run_shadow_check
from delivery_qc.config import load_config
from delivery_qc.infrastructure.database import load_latest_run_history
from delivery_qc.infrastructure.reports import refresh_history_reports


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    workspace = Path(args.workspace).resolve()
    config = load_config(Path(args.config).resolve(), workspace)

    if args.command == "inspect":
        schedule = inspect_schedule(Path(args.ics).resolve(), config)
        print(
            json.dumps(
                {
                    "deliveries": len(schedule.deliveries),
                    "notices": len(schedule.notices),
                    "packages": [delivery.package_name for delivery in schedule.deliveries],
                },
                indent=2,
            )
        )
        return 0

    if args.command == "history":
        paths = refresh_history_reports(
            reports_dir=config.reports_path,
            history=load_latest_run_history(config.database_path),
            generated_at=datetime.now(timezone.utc),
        )
        print("SHADOW MODE — no emails sent")
        print(f"History dashboard: {paths.html}")
        print(f"History JSON: {paths.json}")
        print(f"History CSV: {paths.csv}")
        return 0

    delivery_date = date.fromisoformat(args.date)
    status_records = None
    match_records = None
    if args.stratus_readonly:
        schedule = inspect_schedule(Path(args.ics).resolve(), config)
        daily_deliveries = tuple(
            delivery for delivery in schedule.deliveries if delivery.delivery_date == delivery_date
        )
        if daily_deliveries:
            app_key = _read_app_key()
            if not app_key:
                parser.error(
                    "STRATUS_APP_KEY or STRATUS_APP_KEY_FILE is required for "
                    "--stratus-readonly"
                )
            client = StratusReadOnlyClient(app_key, project_mappings=config.project_mappings)
            status_records = client.statuses_for_deliveries(daily_deliveries)
            match_records = client.resolutions

    outcome = run_shadow_check(
        delivery_date=delivery_date,
        ics_path=Path(args.ics).resolve(),
        statuses_path=Path(args.statuses).resolve() if args.statuses else None,
        config=config,
        status_records=status_records,
        match_records=match_records,
        comparison_ics_path=Path(args.comparison_ics).resolve() if args.comparison_ics else None,
    )
    flagged = sum(result.follow_up_required for result in outcome.results)
    print("SHADOW MODE — no emails sent")
    print(f"Run: {outcome.run_id}")
    print(f"Packages: {len(outcome.results)}; flagged: {flagged}")
    print(f"History dashboard: {outcome.report_paths.index_html}")
    print(f"Daily dashboard: {outcome.report_paths.latest_html}")
    print(f"Report: {outcome.report_paths.markdown}")
    print(f"Hermes handoff: {outcome.report_paths.latest_markdown}")
    return 0


def _read_app_key() -> str:
    app_key = os.environ.get("STRATUS_APP_KEY", "").strip()
    if app_key:
        return app_key
    secret_path = os.environ.get("STRATUS_APP_KEY_FILE", "").strip()
    if not secret_path:
        return ""
    return Path(secret_path).read_text(encoding="utf-8").strip()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Shadow-only Stratus delivery QC checker")
    parser.add_argument("--workspace", default=".", help="Project workspace root")
    parser.add_argument("--config", default="config/qc.toml", help="TOML configuration path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Inspect an ICS file only")
    inspect_parser.add_argument("--ics", required=True, help="Path to the ICS schedule")

    subparsers.add_parser(
        "history",
        help="Rebuild the date-filterable history dashboard from the local audit database",
    )

    run_parser = subparsers.add_parser("run", help="Run a shadow QC check")
    run_parser.add_argument("--date", required=True, help="Delivery date in YYYY-MM-DD format")
    run_parser.add_argument("--ics", required=True, help="Path to the ICS schedule")
    run_parser.add_argument("--comparison-ics", help="Newest snapshot; disagreement blocks publication")
    status_source = run_parser.add_mutually_exclusive_group()
    status_source.add_argument("--statuses", help="Path to the read-only status CSV snapshot")
    status_source.add_argument(
        "--stratus-readonly",
        action="store_true",
        help="Read package/container status using GET-only Stratus API calls",
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
