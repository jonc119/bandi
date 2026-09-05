from datetime import date
import unittest

from delivery_qc.domain.models import ContainerStatus, Delivery, MatchResult, MatchState, ResultCode
from delivery_qc.domain.rules import evaluate_delivery


class RuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.delivery = Delivery(
            source_uid="one",
            delivery_date=date(2026, 8, 18),
            project="Central Hospital",
            package_name="CHW-Riser-01",
            expected_container_count=3,
            expected_container_names=("Cart-1", "Cart-2", "Cart-3"),
        )

    def test_all_containers_field_received_passes(self) -> None:
        statuses = tuple(self._status(index, "Field Received") for index in range(1, 4))
        result = evaluate_delivery(self.delivery, MatchResult(MatchState.MATCHED, statuses))
        self.assertEqual(ResultCode.PASS_COMPLETE, result.result_code)
        self.assertFalse(result.follow_up_required)

    def test_division_prefixed_field_received_passes(self) -> None:
        statuses = (
            self._status(1, "MP - Field Received"),
            self._status(2, "SM - Field Received"),
            self._status(3, "EL - Field Received"),
        )
        result = evaluate_delivery(self.delivery, MatchResult(MatchState.MATCHED, statuses))
        self.assertEqual(ResultCode.PASS_COMPLETE, result.result_code)

    def test_partial_delivery_is_flagged(self) -> None:
        statuses = (
            self._status(1, "Field Received"),
            self._status(2, "In Transit"),
            self._status(3, "Field Received"),
        )
        result = evaluate_delivery(self.delivery, MatchResult(MatchState.MATCHED, statuses))
        self.assertEqual(ResultCode.FLAG_PARTIAL_DELIVERY, result.result_code)
        self.assertEqual(1, result.outstanding_count)
        self.assertTrue(result.follow_up_required)

    def test_missing_container_is_mismatch_not_pass(self) -> None:
        statuses = tuple(self._status(index, "Field Received") for index in range(1, 3))
        result = evaluate_delivery(self.delivery, MatchResult(MatchState.MATCHED, statuses))
        self.assertEqual(ResultCode.FLAG_CONTAINER_MISMATCH, result.result_code)
        self.assertEqual(1, result.outstanding_count)
        self.assertTrue(result.follow_up_required)

    def _status(self, index: int, status: str) -> ContainerStatus:
        return ContainerStatus("Central Hospital", "CHW-Riser-01", f"Cart-{index}", status)


if __name__ == "__main__":
    unittest.main()
