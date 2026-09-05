from __future__ import annotations

import argparse
from datetime import datetime, time
from functools import partial
from html import escape
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo


def read_object(path: Path) -> dict:
    try:
        if path.stat().st_size > 20 * 1024 * 1024:
            return {}
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def health_summary(reports: Path, health_path: Path, now: datetime | None = None) -> dict:
    local_now = (now or datetime.now(ZoneInfo("America/New_York"))).astimezone(ZoneInfo("America/New_York"))
    report = read_object(reports / "latest-delivery-qc-report.json")
    scheduled = read_object(health_path)
    warnings = []
    if scheduled.get("state") != "SUCCESS":
        warnings.append("Scheduled check failed or has no verified success record.")
    if local_now.time() >= time(16, 30) and scheduled.get("delivery_date") != local_now.date().isoformat():
        warnings.append("Today's 4 PM check is missing. Do not treat an older report as today's result.")
    if not report:
        warnings.append("No readable completed report is available.")
    return {"warnings": warnings, "scheduled_delivery_date": scheduled.get("delivery_date"),
            "scheduled_completed_at": scheduled.get("completed_at"), "scheduled_state": scheduled.get("state", "UNKNOWN"),
            "latest_report_delivery_date": report.get("delivery_date"), "latest_report_checked_at": report.get("created_at"),
            "latest_report_run_id": report.get("run_id"), "scheduled_run_id": scheduled.get("run_id")}


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: str, health_path: str, **kwargs):
        self.reports_root = Path(directory).resolve()
        self.health_path = Path(health_path)
        super().__init__(*args, directory=directory, **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'")
        super().end_headers()

    def send_head(self):
        requested = unquote(urlsplit(self.path).path)
        if requested == "/health.json":
            payload = json.dumps(health_summary(self.reports_root, self.health_path)).encode()
            content_type = "application/json"
        else:
            relative = "index.html" if requested == "/" else requested.lstrip("/")
            target = (self.reports_root / relative).resolve()
            allowed_names = {"index.html", "latest-delivery-qc-dashboard.html", "latest-delivery-qc-review.xlsx",
                "latest-delivery-qc-report.json", "latest-delivery-qc-report.md", "latest-delivery-qc-status.md",
                "delivery-qc-history.json", "delivery-qc-history.csv", "delivery-qc-dashboard.html",
                "delivery-qc-review.xlsx", "delivery-qc-report.json", "delivery-qc-report.md", "delivery-qc-results.csv"}
            if not target.is_relative_to(self.reports_root) or target.name not in allowed_names or not target.is_file():
                self.send_error(404)
                return None
            if target.stat().st_size > 20 * 1024 * 1024:
                self.send_error(413)
                return None
            payload = target.read_bytes()
            content_type = self.guess_type(str(target))
            if target.suffix == ".html":
                health = health_summary(self.reports_root, self.health_path)
                messages = health["warnings"] + [
                    f"Scheduled run: {health['scheduled_delivery_date']} ({health['scheduled_state']}).",
                    f"Latest report: delivery date {health['latest_report_delivery_date']}, checked {health['latest_report_checked_at']}.",
                    "Current observations do not establish historical receipt by 4 PM."]
                banner = '<aside role="status" style="padding:16px;background:#fff4ce;color:#222">' + "<br>".join(escape(item) for item in messages) + "</aside>"
                payload = payload.replace(b"<body>", b"<body>" + banner.encode(), 1)
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        return BytesIO(payload)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", default="/reports")
    parser.add_argument("--health-path", default="/health/latest-run-status.json")
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9120)
    args = parser.parse_args()
    handler = partial(DashboardHandler, directory=args.directory, health_path=args.health_path)
    ThreadingHTTPServer((args.bind, args.port), handler).serve_forever()


if __name__ == "__main__":
    main()
