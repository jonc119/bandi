from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from io import StringIO
import csv
import sqlite3
import unittest
from contextlib import closing
import json
from functools import partial
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import urlopen
from delivery_qc.infrastructure.dashboard_server import DashboardHandler, health_summary
from delivery_qc.application.checker import run_shadow_check
from delivery_qc.config import ProjectConfig

from openpyxl import load_workbook

from delivery_qc.domain.models import ContainerStatus, Delivery, MatchResult, MatchState
from delivery_qc.domain.rules import evaluate_delivery
from delivery_qc.infrastructure.database import persist_run
from delivery_qc.infrastructure.excel_report import write_excel_report
from delivery_qc.infrastructure.export_safety import SafeCsvWriter
import test_matching_safety as matching_fixtures


class ReleaseBlockerTests(unittest.TestCase):
    def test_disagreeing_snapshots_block_report_publication(self):
        fixtures = Path(__file__).parent / 'fixtures'
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = ProjectConfig('shadow', 'America/New_York', ('Field Received',), (),
                                   root/'audit.db', root/'reports', root/'drafts', root/'logs')
            with self.assertRaisesRegex(ValueError, 'snapshots disagree'):
                run_shadow_check(delivery_date=date(2026,8,18), ics_path=fixtures/'deliveries.ics',
                                 comparison_ics_path=fixtures/'no_deliveries.ics', statuses_path=None, config=config)
            self.assertFalse((root/'reports').exists())

    def test_dashboard_denies_directories_and_traversal_and_sets_headers(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'index.html').write_text('<html><body>Test</body></html>')
            (root / 'private.txt').write_text('not public')
            handler = partial(DashboardHandler, directory=str(root), health_path=str(root / 'health.json'))
            server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f'http://127.0.0.1:{server.server_port}'
                with urlopen(base + '/') as response:
                    self.assertEqual('no-store', response.headers['Cache-Control'])
                    self.assertEqual('DENY', response.headers['X-Frame-Options'])
                    self.assertIn(b'no verified success record', response.read())
                for suffix in ('/private.txt', '/2026-09-04/', '/%2e%2e/private.txt'):
                    with self.subTest(suffix=suffix), self.assertRaises(HTTPError) as error:
                        urlopen(base + suffix)
                    self.assertEqual(404, error.exception.code)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_health_separates_recheck_from_missing_daily_run(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'latest-delivery-qc-report.json').write_text(json.dumps({'delivery_date':'2026-09-04','created_at':'2026-09-05T12:00:00Z','run_id':'recheck'}))
            health = root / 'scheduled.json'
            health.write_text(json.dumps({'delivery_date':'2026-09-04','state':'SUCCESS','run_id':'scheduled'}))
            summary = health_summary(root, health, datetime(2026,9,5,22,tzinfo=timezone.utc))
            self.assertEqual('recheck', summary['latest_report_run_id'])
            self.assertEqual('scheduled', summary['scheduled_run_id'])
            self.assertTrue(any('missing' in warning for warning in summary['warnings']))

    def test_csv_formula_prefixes_are_text_and_numbers_stay_numeric(self):
        for value in ("=1+1", "+1+1", "-1+1", "@SUM(1)", " \t=1+1", "\ufeff=1+1", "\ntext", "＝1+1"):
            with self.subTest(value=value):
                output = StringIO()
                SafeCsvWriter(output).writerow([value, 12])
                self.assertEqual(["'" + value, "12"], next(csv.reader(StringIO(output.getvalue()))))

    def test_xlsx_all_source_strings_remain_literal_without_losing_links(self):
        delivery = Delivery("test", date(2026, 9, 5), "=1+1", "=1+1", expected_container_count=1)
        container = ContainerStatus("=1+1", "=1+1", "=1+1", "=1+1",
                                    container_id="container", package_id="package", project_id="project", model_id="model")
        result = evaluate_delivery(delivery, MatchResult(MatchState.MATCHED, (container,)))
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "report.xlsx"
            write_excel_report(path=path, run_id="test", delivery_date=delivery.delivery_date,
                               created_at=datetime.now(timezone.utc), results=(result,))
            book = load_workbook(path)
            source_cells = [cell for sheet in book for row in sheet for cell in row if cell.value == "=1+1"]
            self.assertGreater(len(source_cells), 5)
            self.assertTrue(all(cell.data_type == "s" for cell in source_cells))
            self.assertIsNotNone(book['Package Review']['D5'].hyperlink)
            book.close()

    def test_mixed_direct_and_part_membership_includes_both(self):
        setup = matching_fixtures.MatchingSafetyTests()
        setup.setUp()
        client = setup.client({"Seminole - Arlen": matching_fixtures.REAL})
        client.project_containers.return_value += ({"id": "indirect", "name": "Second pallet",
            "partIds": ["part"], "currentTrackingStatusId": "transit"},)
        client.package_parts.return_value = ({"id": "part"},)
        records = client.statuses_for_deliveries((setup.delivery,))
        self.assertEqual({"pallet-id", "indirect"}, {record.container_id for record in records})
        self.assertTrue(evaluate_delivery(setup.delivery, client.resolutions["roof"]).follow_up_required)

    def test_same_name_distinct_containers_persist_without_merging(self):
        delivery = Delivery("test", date(2026, 9, 5), "project", "package", expected_container_count=2)
        containers = tuple(ContainerStatus("project", "package", "Pallet", "Field Received", container_id=identity)
                           for identity in ("first", "second"))
        result = evaluate_delivery(delivery, MatchResult(MatchState.MATCHED, containers))
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "audit.db"
            persist_run(database_path=path, run_id="test", delivery_date=delivery.delivery_date,
                        created_at=datetime.now(timezone.utc), source_hash="source", status_hash="status", results=(result,), notices=())
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(2, connection.execute("SELECT count(*) FROM container_evidence").fetchone()[0])
                self.assertEqual({"first", "second"}, {row[0] for row in connection.execute("SELECT container_id FROM container_evidence")})


if __name__ == "__main__":
    unittest.main()
