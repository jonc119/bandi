from datetime import date
import json
import unittest

from delivery_qc.adapters.stratus_api import StratusApiError, StratusReadOnlyClient
from delivery_qc.domain.models import Delivery


PROJECT_ID = "6d8ddfd2-f486-4dcf-b197-94056ab71a6c"
PACKAGE_ID = "c2aaa581-4830-4c53-92d4-b068110c6827"
MODEL_ID = "204c11ad-18cf-4939-ab27-768fa744e60e"
STATUS_ID = "52f319f0-34e0-4df0-a9fc-aa49b60f8bb4"


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback) -> None:
        return None

    def read(self, size=-1) -> bytes:
        payload = json.dumps(self.payload).encode("utf-8")
        return payload if size < 0 else payload[:size]


class FakeOpener:
    def __init__(self, payloads: list[object]) -> None:
        self.payloads = list(payloads)
        self.requests = []

    def open(self, request, timeout: float):
        self.requests.append(request)
        return FakeResponse(self.payloads.pop(0))


class StratusApiTests(unittest.TestCase):
    def test_page_count_is_row_count_not_number_of_pages(self):
        opener = FakeOpener([{"data": [{"id": "one"}, {"id": "two"}], "pageCount": 2, "total": 2}])
        client = StratusReadOnlyClient("test", opener=opener)
        self.assertEqual(2, len(client._get_all_pages("/v1/package", include="id", page_size=200)))
        self.assertEqual(1, len(opener.requests))

    def test_total_drives_pagination_even_on_short_page(self):
        opener = FakeOpener([
            {"data": [{"id": "one"}], "pageCount": 1, "total": 2},
            {"data": [{"id": "two"}], "pageCount": 1, "total": 2},
        ])
        client = StratusReadOnlyClient("test", opener=opener)
        self.assertEqual(2, len(client._get_all_pages("/v1/package", include="id", page_size=200)))
        self.assertEqual(2, len(opener.requests))

    def test_truncated_missing_or_repeated_pages_fail_closed(self):
        for payloads in (
            [{"data": [], "truncatedResults": True}],
            [{"data": [], "total": 2}],
            [{"data": [{"id": "one"}], "total": 3}] * 2,
        ):
            with self.subTest(payloads=payloads):
                client = StratusReadOnlyClient("test", opener=FakeOpener(payloads))
                with self.assertRaises(StratusApiError):
                    client._get_all_pages("/v1/package", include="id", page_size=200)

    def test_reads_package_containers_and_tracking_status_with_get_only(self) -> None:
        opener = FakeOpener(
            [
                {
                    "data": [
                        {
                            "id": PACKAGE_ID,
                            "name": "CHW-Riser-01",
                            "projectId": PROJECT_ID,
                            "modelId": MODEL_ID,
                        }
                    ]
                },
                {"id": PROJECT_ID, "name": "Central Hospital"},
                {
                    "data": [
                        {
                            "id": "container-id",
                            "name": "Cart-1",
                            "currentTrackingStatusId": STATUS_ID,
                            "packageIds": [],
                            "contents": [
                                {
                                    "referenceId": PACKAGE_ID,
                                    "referenceType": 4,
                                }
                            ],
                            "containerIds": ["nested-container-id"],
                        },
                        {
                            "id": "nested-container-id",
                            "name": "Cart-1A",
                            "currentTrackingStatusId": STATUS_ID,
                            "packageIds": [],
                            "parentContainerId": "container-id",
                        }
                    ],
                    "pageCount": 1,
                },
                [{"id": STATUS_ID, "name": "MP - Field Received"}],
                {"data": []},
                {"data": []},
            ]
        )
        client = StratusReadOnlyClient("test-secret", opener=opener)
        delivery = Delivery(
            source_uid="delivery",
            delivery_date=date(2026, 8, 18),
            project="Central Hospital",
            package_name="CHW-Riser-01",
        )

        statuses = client.statuses_for_deliveries((delivery,))

        self.assertEqual(2, len(statuses))
        self.assertEqual("Cart-1", statuses[0].container_name)
        self.assertEqual("Cart-1A", statuses[1].container_name)
        self.assertEqual("MP - Field Received", statuses[0].status)
        self.assertEqual("container-id", statuses[0].container_id)
        self.assertEqual(PACKAGE_ID, statuses[0].package_id)
        self.assertEqual(PROJECT_ID, statuses[0].project_id)
        self.assertEqual(MODEL_ID, statuses[0].model_id)
        self.assertTrue(all(request.get_method() == "GET" for request in opener.requests))
        self.assertTrue(all("test-secret" not in request.full_url for request in opener.requests))
        self.assertTrue(
            all(request.get_header("App-key") == "test-secret" for request in opener.requests)
        )
        self.assertIn(f"/v1/project/{PROJECT_ID}/containers", opener.requests[2].full_url)

    def test_repairs_one_missing_closing_parenthesis_for_exact_lookup(self) -> None:
        opener = FakeOpener(
            [
                {"data": []},
                {
                    "data": [
                        {
                            "id": PACKAGE_ID,
                            "name": "SM-SF-TERMINAL-(1-9)",
                            "projectId": PROJECT_ID,
                        }
                    ]
                },
            ]
        )
        client = StratusReadOnlyClient("test-secret", opener=opener)

        packages = client.list_packages_by_name("SM-SF-TERMINAL-(1-9")

        self.assertEqual(1, len(packages))
        self.assertEqual("SM-SF-TERMINAL-(1-9)", packages[0].name)
        self.assertEqual(2, len(opener.requests))

    def test_matches_containers_by_package_part_overlap(self) -> None:
        opener = FakeOpener(
            [
                {"data": [{"id": PACKAGE_ID, "name": "CHW-Riser-01", "projectId": PROJECT_ID}]},
                {"id": PROJECT_ID, "name": "Central Hospital"},
                {
                    "data": [
                        {
                            "id": "container-id",
                            "name": "Cart-1",
                            "currentTrackingStatusId": STATUS_ID,
                            "packageIds": [],
                            "partIds": ["part-id"],
                        }
                    ],
                    "pageCount": 1,
                },
                [{"id": STATUS_ID, "name": "MP - Field Received"}],
                {"data": [], "pageCount": 1},
                {"data": [{"id": "part-id", "cadId": "part-cad-id"}], "pageCount": 1},
            ]
        )
        client = StratusReadOnlyClient("test-secret", opener=opener)
        delivery = Delivery(
            source_uid="delivery",
            delivery_date=date(2026, 8, 18),
            project="Central Hospital",
            package_name="CHW-Riser-01",
        )

        statuses = client.statuses_for_deliveries((delivery,))

        self.assertEqual(1, len(statuses))
        self.assertEqual("Cart-1", statuses[0].container_name)
        self.assertIn(f"/v2/package/{PACKAGE_ID}/parts", opener.requests[-1].full_url)

    def test_preserves_scheduled_name_after_parenthesis_repair(self) -> None:
        scheduled_name = "SM-SF-TERMINAL-(1-9"
        opener = FakeOpener(
            [
                {"data": []},
                {
                    "data": [
                        {
                            "id": PACKAGE_ID,
                            "name": "SM-SF-TERMINAL-(1-9)",
                            "projectId": PROJECT_ID,
                        }
                    ]
                },
                {"id": PROJECT_ID, "name": "Terminal Project"},
                {
                    "data": [
                        {
                            "id": "container-id",
                            "name": "Cart-1",
                            "currentTrackingStatusId": STATUS_ID,
                            "partIds": ["part-id"],
                        }
                    ],
                    "pageCount": 1,
                },
                [{"id": STATUS_ID, "name": "SM - Field Received"}],
                {"data": [], "pageCount": 1},
                {"data": [{"id": "part-id", "cadId": "part-cad-id"}], "pageCount": 1},
            ]
        )
        client = StratusReadOnlyClient("test-secret", opener=opener)
        delivery = Delivery(
            source_uid="delivery",
            delivery_date=date(2026, 8, 18),
            project="",
            package_name=scheduled_name,
        )

        statuses = client.statuses_for_deliveries((delivery,))

        self.assertEqual(1, len(statuses))
        self.assertEqual(scheduled_name, statuses[0].package_name)

    def test_blocks_non_allowlisted_hosts_and_paths(self) -> None:
        with self.assertRaises(ValueError):
            StratusReadOnlyClient("key", base_url="https://example.com")

        client = StratusReadOnlyClient("key", opener=FakeOpener([]))
        with self.assertRaisesRegex(StratusApiError, "Blocked"):
            client._get_json(f"/v1/container/{PACKAGE_ID}/tracking-status")

    def test_rejects_invalid_project_ids_before_request(self) -> None:
        client = StratusReadOnlyClient("key", opener=FakeOpener([]))
        with self.assertRaisesRegex(StratusApiError, "invalid project id"):
            client.project_containers("not-a-project-id")


if __name__ == "__main__":
    unittest.main()
