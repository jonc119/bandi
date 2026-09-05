from __future__ import annotations

from dataclasses import replace

from delivery_qc.domain.models import (
    Delivery,
    MatchResult,
    MatchState,
    PackageResult,
    ResultCode,
)
from delivery_qc.domain.normalize import normalize_status, normalize_text, status_matches


def evaluate_delivery(
    delivery: Delivery,
    match: MatchResult,
    pass_statuses: tuple[str, ...] = ("Field Received",),
) -> PackageResult:
    result = _evaluate_delivery(delivery, match, pass_statuses)
    return replace(result, warnings=result.warnings + match.evidence)


def _evaluate_delivery(
    delivery: Delivery,
    match: MatchResult,
    pass_statuses: tuple[str, ...],
) -> PackageResult:
    if match.state is MatchState.NOT_FOUND:
        return _empty_result(delivery, ResultCode.FLAG_PACKAGE_NOT_FOUND, "PACKAGE_NOT_FOUND")
    if match.state is MatchState.AMBIGUOUS:
        return _empty_result(delivery, ResultCode.FLAG_AMBIGUOUS_PACKAGE, "AMBIGUOUS_PACKAGE")

    containers = match.containers
    if not containers:
        return _empty_result(delivery, ResultCode.FLAG_STATUS_UNKNOWN, "NO_CONTAINERS_RETURNED")

    received = [
        container
        for container in containers
        if status_matches(container.status, pass_statuses)
    ]
    unknown = [container for container in containers if not normalize_status(container.status)]
    reasons: list[str] = []
    warnings: list[str] = []
    outstanding_count = len(containers) - len(received)

    expected_count = delivery.expected_container_count
    if expected_count is None and not delivery.expected_container_names:
        reasons.append("EXPECTED_CONTAINER_COUNT_UNKNOWN")
    if expected_count is not None and expected_count <= 0:
        reasons.append("INVALID_EXPECTED_CONTAINER_COUNT")
    if len({normalize_text(container.container_name) for container in containers}) != len(containers):
        reasons.append("DUPLICATE_CONTAINER_NAMES")
    if delivery.expected_container_names:
        expected_names = {normalize_text(name) for name in delivery.expected_container_names}
        observed_names = {normalize_text(container.container_name) for container in containers}
        received_names = {normalize_text(container.container_name) for container in received}
        missing_names = expected_names - observed_names
        extra_names = observed_names - expected_names
        outstanding_count = len(expected_names - received_names)
        if missing_names or extra_names:
            reasons.append("CONTAINER_NAME_MISMATCH")

    if expected_count is not None and len(containers) != expected_count:
        reasons.append("CONTAINER_COUNT_MISMATCH")
        if not delivery.expected_container_names:
            outstanding_count = max(outstanding_count, expected_count - len(received))
    elif expected_count is None:
        warnings.append("EXPECTED_CONTAINER_COUNT_NOT_PROVIDED")

    if unknown:
        reasons.append("UNKNOWN_CONTAINER_STATUS")

    if any(reason in reasons for reason in ("CONTAINER_NAME_MISMATCH", "CONTAINER_COUNT_MISMATCH", "INVALID_EXPECTED_CONTAINER_COUNT", "DUPLICATE_CONTAINER_NAMES")):
        result_code = ResultCode.FLAG_CONTAINER_MISMATCH
    elif unknown or "EXPECTED_CONTAINER_COUNT_UNKNOWN" in reasons:
        result_code = ResultCode.FLAG_STATUS_UNKNOWN
    elif len(received) == len(containers):
        result_code = ResultCode.PASS_COMPLETE
    elif received:
        result_code = ResultCode.FLAG_PARTIAL_DELIVERY
        reasons.append("PARTIAL_FIELD_RECEIPT")
    else:
        result_code = ResultCode.FLAG_NOT_RECEIVED
        reasons.append("NO_FIELD_RECEIPT")

    return PackageResult(
        delivery=delivery,
        result_code=result_code,
        reason_codes=tuple(dict.fromkeys(reasons)),
        containers=containers,
        expected_count=expected_count,
        observed_count=len(containers),
        field_received_count=len(received),
        outstanding_count=max(0, outstanding_count),
        follow_up_required=result_code is not ResultCode.PASS_COMPLETE,
        warnings=tuple(warnings),
    )


def _empty_result(delivery: Delivery, result_code: ResultCode, reason: str) -> PackageResult:
    return PackageResult(
        delivery=delivery,
        result_code=result_code,
        reason_codes=(reason,),
        containers=(),
        expected_count=delivery.expected_container_count,
        observed_count=0,
        field_received_count=0,
        outstanding_count=0,
        follow_up_required=True,
        warnings=("DELIVERY_STATUS_UNVERIFIED",),
    )
