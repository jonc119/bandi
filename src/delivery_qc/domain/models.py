from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum


class EventClassification(StrEnum):
    INCLUDED = "INCLUDED"
    EXCLUDED = "EXCLUDED"
    REVIEW = "REVIEW_UNCLASSIFIED"


class MatchState(StrEnum):
    MATCHED = "MATCHED"
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS = "AMBIGUOUS"
    NO_CONTAINERS = "NO_CONTAINERS"


class ResultCode(StrEnum):
    PASS_COMPLETE = "PASS_COMPLETE"
    FLAG_PARTIAL_DELIVERY = "FLAG_PARTIAL_DELIVERY"
    FLAG_NOT_RECEIVED = "FLAG_NOT_RECEIVED"
    FLAG_CONTAINER_MISMATCH = "FLAG_CONTAINER_MISMATCH"
    FLAG_PACKAGE_NOT_FOUND = "FLAG_PACKAGE_NOT_FOUND"
    FLAG_AMBIGUOUS_PACKAGE = "FLAG_AMBIGUOUS_PACKAGE"
    FLAG_STATUS_UNKNOWN = "FLAG_STATUS_UNKNOWN"


@dataclass(frozen=True, slots=True)
class Delivery:
    source_uid: str
    delivery_date: date
    project: str
    package_name: str
    trade: str = ""
    delivery_number: str = ""
    expected_container_count: int | None = None
    expected_container_names: tuple[str, ...] = ()
    raw_summary: str = ""
    raw_description: str = ""


@dataclass(frozen=True, slots=True)
class ContainerStatus:
    project: str
    package_name: str
    container_name: str
    status: str
    observed_at: str = ""
    container_id: str = ""
    package_id: str = ""
    project_id: str = ""
    model_id: str = ""


@dataclass(frozen=True, slots=True)
class ScheduleNotice:
    source_uid: str
    delivery_date: date
    summary: str
    classification: EventClassification
    reason: str


@dataclass(frozen=True, slots=True)
class MatchResult:
    state: MatchState
    containers: tuple[ContainerStatus, ...] = ()
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PackageResult:
    delivery: Delivery
    result_code: ResultCode
    reason_codes: tuple[str, ...]
    containers: tuple[ContainerStatus, ...]
    expected_count: int | None
    observed_count: int
    field_received_count: int
    outstanding_count: int
    follow_up_required: bool
    warnings: tuple[str, ...] = field(default_factory=tuple)
