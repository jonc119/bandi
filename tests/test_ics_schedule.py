from datetime import date
from pathlib import Path
import unittest

from delivery_qc.adapters.ics_schedule import parse_ics
from delivery_qc.domain.models import EventClassification


FIXTURES = Path(__file__).parent / "fixtures"


class IcsScheduleTests(unittest.TestCase):
    def test_extracts_packages_and_classifies_other_events(self) -> None:
        schedule = parse_ics(FIXTURES / "deliveries.ics")

        self.assertEqual(2, len(schedule.deliveries))
        delivery = schedule.deliveries[0]
        self.assertEqual(date(2026, 8, 18), delivery.delivery_date)
        self.assertEqual("Central Hospital", delivery.project)
        self.assertEqual("CHW-Riser-01", delivery.package_name)
        self.assertEqual(3, delivery.expected_container_count)
        self.assertEqual(("Cart-1", "Cart-2", "Cart-3"), delivery.expected_container_names)
        self.assertEqual(
            [EventClassification.EXCLUDED, EventClassification.REVIEW],
            [notice.classification for notice in schedule.notices],
        )

    def test_extracts_delivery_number_from_additional_info(self) -> None:
        content = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:delivery-number
DTSTART;VALUE=DATE:20260818
SUMMARY:Delivery
DESCRIPTION:Package Name: CHW-Riser-01\\nContainers Completed: 2 carts\\nAdditional Info: DL#3154\\nCategory: Piping
END:VEVENT
END:VCALENDAR
"""
        with self.subTest("DL number"):
            from tempfile import TemporaryDirectory

            with TemporaryDirectory() as temporary_directory:
                path = Path(temporary_directory) / "delivery.ics"
                path.write_text(content, encoding="utf-8")
                schedule = parse_ics(path)

        self.assertEqual("3154", schedule.deliveries[0].delivery_number)


if __name__ == "__main__":
    unittest.main()
