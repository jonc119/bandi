from datetime import date, datetime, timezone
from pathlib import Path
import tempfile
import unittest

from delivery_qc.domain.models import Delivery, PackageResult, ResultCode
from delivery_qc.infrastructure.database import load_latest_run_history, persist_run


class HistoryDatabaseTests(unittest.TestCase):
    def test_history_uses_only_latest_run_for_each_delivery_date(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "state.db"
            delivery_date = date(2026, 8, 18)
            persist_run(
                database_path=database_path,
                run_id="earlier-run",
                delivery_date=delivery_date,
                created_at=datetime(2026, 8, 18, 20, 0, tzinfo=timezone.utc),
                source_hash="source",
                status_hash="partial",
                results=(self._result(delivery_date, flagged=True),),
                notices=(),
            )
            persist_run(
                database_path=database_path,
                run_id="latest-run",
                delivery_date=delivery_date,
                created_at=datetime(2026, 8, 18, 20, 5, tzinfo=timezone.utc),
                source_hash="source",
                status_hash="complete",
                results=(self._result(delivery_date, flagged=False),),
                notices=(),
            )
            persist_run(
                database_path=database_path,
                run_id="next-day-run",
                delivery_date=date(2026, 8, 19),
                created_at=datetime(2026, 8, 19, 20, 0, tzinfo=timezone.utc),
                source_hash="source-next",
                status_hash="partial-next",
                results=(self._result(date(2026, 8, 19), flagged=True),),
                notices=(),
            )

            history = load_latest_run_history(database_path)

            self.assertEqual([date(2026, 8, 19), delivery_date], [run.delivery_date for run in history])
            self.assertEqual("latest-run", history[1].run_id)
            self.assertEqual(0, history[1].issue_count)
            self.assertEqual(1, history[1].passed_count)
            self.assertEqual(1, history[0].issue_count)
            self.assertEqual(1, history[0].outstanding_count)

    def _result(self, delivery_date: date, *, flagged: bool) -> PackageResult:
        return PackageResult(
            delivery=Delivery(
                source_uid=f"package-{delivery_date.isoformat()}",
                delivery_date=delivery_date,
                project="Central Hospital",
                package_name="CHW-Riser-01",
            ),
            result_code=(
                ResultCode.FLAG_NOT_RECEIVED if flagged else ResultCode.PASS_COMPLETE
            ),
            reason_codes=("NO_FIELD_RECEIPT",) if flagged else ("ALL_FIELD_RECEIVED",),
            containers=(),
            expected_count=1,
            observed_count=1,
            field_received_count=0 if flagged else 1,
            outstanding_count=1 if flagged else 0,
            follow_up_required=flagged,
        )


if __name__ == "__main__":
    unittest.main()
