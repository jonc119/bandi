from dataclasses import replace
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from delivery_qc.adapters.ics_schedule import parse_ics
from delivery_qc.adapters.stratus_api import StratusPackage, StratusReadOnlyClient
from delivery_qc.domain.matching import match_package
from delivery_qc.domain.models import ContainerStatus, Delivery, MatchResult, MatchState, ResultCode
from delivery_qc.domain.rules import evaluate_delivery
from delivery_qc.infrastructure.html_report import write_html_report
from datetime import datetime, timezone


REAL = "483a7d6f-4c6b-43f4-b02d-5973fe3ddaee"
SANDBOX = "3ca5d4cd-1fb4-46a0-9f19-b9d6726e83fb"


class MatchingSafetyTests(unittest.TestCase):
    def setUp(self):
        self.delivery = Delivery("roof", date(2026, 9, 4), "", "ROOF-CURB",
                                 expected_container_count=1, raw_summary="Seminole - Arlen")
        self.packages = (
            StratusPackage("sandbox-package", "ROOF-CURB", SANDBOX, "sandbox-model"),
            StratusPackage("real-package", "ROOF-CURB", REAL, "real-model"),
        )

    def client(self, mappings=None):
        client = StratusReadOnlyClient("synthetic-test-key", project_mappings=mappings)
        client.list_packages_by_name = Mock(return_value=self.packages)
        client.project_name = Mock(side_effect=lambda project: "Seminole High School" if project == REAL else "Sheetmetal Sandbox")
        client.project_containers = Mock(return_value=({
            "id": "pallet-id", "name": "Pallet 0505", "packageIds": ["real-package"],
            "currentTrackingStatusId": "received-id",
        },))
        client.tracking_statuses = Mock(return_value={"received-id": "SM - Field Received"})
        client.package_parts = Mock(return_value=())
        client.package_assemblies = Mock(return_value=())
        return client

    def test_duplicate_exact_names_preserve_ambiguity_not_not_found(self):
        client = self.client()
        self.assertEqual((), client.statuses_for_deliveries((self.delivery,)))
        result = evaluate_delivery(self.delivery, client.resolutions["roof"])
        self.assertEqual(ResultCode.FLAG_AMBIGUOUS_PACKAGE, result.result_code)
        self.assertEqual(0, result.outstanding_count)
        self.assertTrue(any("sandbox-package" in item for item in result.warnings))
        client.project_containers.assert_not_called()

    def test_reviewed_project_id_resolves_roof_curb(self):
        client = self.client({"Seminole - Arlen": REAL})
        client.statuses_for_deliveries((self.delivery,))
        result = evaluate_delivery(self.delivery, client.resolutions["roof"])
        self.assertEqual(ResultCode.PASS_COMPLETE, result.result_code)
        self.assertEqual("real-package", result.containers[0].package_id)
        self.assertTrue(any("REVIEWED_PROJECT_MAPPING" in item for item in result.warnings))

    def test_stale_mapping_cannot_fall_back_to_wrong_project(self):
        client = self.client({"Seminole - Arlen": "00000000-0000-0000-0000-000000000001"})
        client.statuses_for_deliveries((self.delivery,))
        self.assertEqual(MatchState.AMBIGUOUS, client.resolutions["roof"].state)

    def test_explicit_project_conflicting_with_mapping_blocks_match(self):
        client = self.client({"Seminole - Arlen": REAL})
        client.statuses_for_deliveries((replace(self.delivery, project="Sheetmetal Sandbox"),))
        self.assertEqual(MatchState.AMBIGUOUS, client.resolutions["roof"].state)

    def test_title_substring_is_not_an_approved_mapping(self):
        client = self.client({"Seminole": REAL})
        client.statuses_for_deliveries((self.delivery,))
        self.assertEqual(MatchState.AMBIGUOUS, client.resolutions["roof"].state)

    def test_no_candidates_is_not_found(self):
        client = self.client()
        client.list_packages_by_name.return_value = ()
        client.statuses_for_deliveries((self.delivery,))
        self.assertEqual(MatchState.NOT_FOUND, client.resolutions["roof"].state)

    def test_package_without_containers_is_not_missing_package(self):
        client = self.client({"Seminole - Arlen": REAL})
        client.project_containers.return_value = ()
        client.statuses_for_deliveries((self.delivery,))
        result = evaluate_delivery(self.delivery, client.resolutions["roof"])
        self.assertEqual(ResultCode.FLAG_STATUS_UNKNOWN, result.result_code)
        self.assertIn("NO_CONTAINERS_RETURNED", result.reason_codes)

    def test_two_package_ids_in_same_project_remain_ambiguous(self):
        statuses = tuple(ContainerStatus("Seminole", "ROOF-CURB", "Pallet", "Field Received",
                                        package_id=package) for package in ("one", "two"))
        self.assertEqual(MatchState.AMBIGUOUS, match_package(self.delivery, statuses).state)

    def test_explicit_wrong_project_never_falls_back(self):
        status = ContainerStatus("Wrong project", "ROOF-CURB", "Pallet", "Field Received")
        self.assertEqual(MatchState.NOT_FOUND, match_package(replace(self.delivery, project="Seminole"), (status,)).state)

    def test_distinct_container_ids_are_not_collapsed_by_name(self):
        statuses = tuple(ContainerStatus("Seminole", "ROOF-CURB", "Pallet", status,
                                        container_id=identity) for identity, status in (("one", "In Transit"), ("two", "Field Received")))
        match = match_package(self.delivery, statuses)
        self.assertEqual(2, len(match.containers))
        self.assertNotEqual(ResultCode.PASS_COMPLETE, evaluate_delivery(self.delivery, match).result_code)

    def test_unknown_count_blocks_pass(self):
        status = ContainerStatus("Seminole", "ROOF-CURB", "Pallet", "Field Received")
        result = evaluate_delivery(replace(self.delivery, expected_container_count=None), MatchResult(MatchState.MATCHED, (status,)))
        self.assertEqual(ResultCode.FLAG_STATUS_UNKNOWN, result.result_code)

    def test_explicit_names_can_establish_expected_inventory(self):
        status = ContainerStatus("Seminole", "ROOF-CURB", "Pallet", "Field Received")
        delivery = replace(self.delivery, expected_container_count=None, expected_container_names=("Pallet",))
        self.assertEqual(ResultCode.PASS_COMPLETE, evaluate_delivery(delivery, MatchResult(MatchState.MATCHED, (status,))).result_code)

    def test_zero_expected_count_does_not_pass(self):
        status = ContainerStatus("Seminole", "ROOF-CURB", "Pallet", "Field Received")
        result = evaluate_delivery(replace(self.delivery, expected_container_count=0), MatchResult(MatchState.MATCHED, (status,)))
        self.assertNotEqual(ResultCode.PASS_COMPLETE, result.result_code)

    def test_unresolved_dashboard_does_not_claim_zero_received(self):
        result = evaluate_delivery(self.delivery, MatchResult(MatchState.AMBIGUOUS))
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "report.html"
            write_html_report(path=path, run_id="synthetic", delivery_date=self.delivery.delivery_date,
                              created_at=datetime.now(timezone.utc), results=(result,), notices=())
            rendered = path.read_text(encoding="utf-8")
        self.assertIn("Receipt unverified", rendered)
        self.assertNotIn("0 of 1 received", rendered)

    def test_invalid_calendar_is_not_a_zero_delivery_success(self):
        for content in ("", "not a calendar", "BEGIN:VCALENDAR\nBEGIN:VEVENT\nEND:VCALENDAR"):
            with self.subTest(content=content), TemporaryDirectory() as temporary:
                path = Path(temporary) / "source.ics"
                path.write_text(content)
                with self.assertRaises(ValueError):
                    parse_ics(path)

    def test_cancelled_delivery_is_not_scheduled(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "source.ics"
            path.write_text("BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART:20260904\nSTATUS:CANCELLED\nDESCRIPTION:Package Name: ROOF-CURB\nEND:VEVENT\nEND:VCALENDAR")
            self.assertEqual((), parse_ics(path).deliveries)


if __name__ == "__main__":
    unittest.main()
