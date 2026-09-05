from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from delivery_qc.domain.models import (
    Delivery,
    EventClassification,
    ScheduleNotice,
)
from delivery_qc.domain.normalize import parse_container_count, parse_container_names


_LABEL_RE = re.compile(r"^(?P<label>[^:]{1,50}):\s*(?P<value>.*)$")
_DELIVERY_NUMBER_RE = re.compile(r"\bDL\s*#?\s*(?P<number>\d+)\b", re.IGNORECASE)
_DEFAULT_EXCLUSIONS = (
    "meeting",
    "tool delivery",
    "material return",
    "return to shop",
    "pickup",
    "transfer",
)


@dataclass(frozen=True, slots=True)
class ParsedSchedule:
    deliveries: tuple[Delivery, ...]
    notices: tuple[ScheduleNotice, ...]


def parse_ics(
    path: Path,
    default_timezone: str = "America/New_York",
    exclusion_keywords: tuple[str, ...] = (),
) -> ParsedSchedule:
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("Calendar exceeds the 20 MiB safety limit")
    text = path.read_text(encoding="utf-8-sig")
    events = _parse_events(text)
    deliveries: list[Delivery] = []
    notices: list[ScheduleNotice] = []
    exclusions = tuple(keyword.casefold() for keyword in (exclusion_keywords or _DEFAULT_EXCLUSIONS))

    for event in events:
        if _first_value(event, "STATUS").upper() == "CANCELLED":
            continue
        event_date = _event_date(event, default_timezone)
        uid = _first_value(event, "UID") or f"event-{len(deliveries) + len(notices) + 1}"
        summary = _first_value(event, "SUMMARY")
        description = _first_value(event, "DESCRIPTION")
        parsed_packages = _extract_packages(summary, description)
        if parsed_packages and any(key in event for key in ("RRULE", "RDATE", "RECURRENCE-ID")):
            raise ValueError("Recurring delivery events require calendar expansion before QC")

        if not parsed_packages:
            combined = f"{summary}\n{description}".casefold()
            if any(keyword in combined for keyword in exclusions):
                notices.append(
                    ScheduleNotice(
                        source_uid=uid,
                        delivery_date=event_date,
                        summary=summary,
                        classification=EventClassification.EXCLUDED,
                        reason="NON_STRATUS_EVENT_KEYWORD",
                    )
                )
            else:
                notices.append(
                    ScheduleNotice(
                        source_uid=uid,
                        delivery_date=event_date,
                        summary=summary,
                        classification=EventClassification.REVIEW,
                        reason="NO_EXPLICIT_PACKAGE_NAME",
                    )
                )
            continue

        for index, package in enumerate(parsed_packages, start=1):
            package_name = package.get("package_name", "").strip()
            if not package_name:
                continue
            source_uid = uid if len(parsed_packages) == 1 else f"{uid}#{index}"
            deliveries.append(
                Delivery(
                    source_uid=source_uid,
                    delivery_date=event_date,
                    project=package.get("project", "").strip(),
                    package_name=package_name,
                    trade=package.get("trade", "").strip(),
                    delivery_number=package.get("delivery_number", "").strip(),
                    expected_container_count=parse_container_count(
                        package.get("containers", "")
                    ),
                    expected_container_names=parse_container_names(
                        package.get("container_names", "")
                    ),
                    raw_summary=summary,
                    raw_description=description,
                )
            )

    return ParsedSchedule(tuple(deliveries), tuple(notices))


def _parse_events(text: str) -> list[dict[str, list[tuple[dict[str, str], str]]]]:
    unfolded: list[str] = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)

    events: list[dict[str, list[tuple[dict[str, str], str]]]] = []
    if "BEGIN:VCALENDAR" not in unfolded or "END:VCALENDAR" not in unfolded:
        raise ValueError("Invalid or incomplete VCALENDAR")
    current: dict[str, list[tuple[dict[str, str], str]]] | None = None
    for line in unfolded:
        if line == "BEGIN:VEVENT":
            if current is not None:
                raise ValueError("Nested or incomplete VEVENT")
            current = {}
            continue
        if line == "END:VEVENT":
            if current is None:
                raise ValueError("Unexpected END:VEVENT")
            if current is not None:
                events.append(current)
            current = None
            continue
        if current is None or ":" not in line:
            continue
        raw_property, raw_value = line.split(":", 1)
        property_parts = raw_property.split(";")
        property_name = property_parts[0].upper()
        params: dict[str, str] = {}
        for part in property_parts[1:]:
            if "=" in part:
                key, value = part.split("=", 1)
                params[key.upper()] = value
        current.setdefault(property_name, []).append((params, _unescape(raw_value)))
    if current is not None:
        raise ValueError("Incomplete VEVENT")
    return events


def _unescape(value: str) -> str:
    return (
        value.replace("\\N", "\n")
        .replace("\\n", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
    )


def _first_value(event: dict[str, list[tuple[dict[str, str], str]]], key: str) -> str:
    values = event.get(key, [])
    return values[0][1] if values else ""


def _event_date(
    event: dict[str, list[tuple[dict[str, str], str]]], default_timezone: str
) -> date:
    values = event.get("DTSTART", [])
    if not values:
        raise ValueError("VEVENT is missing DTSTART")
    params, value = values[0]
    if len(value) == 8 and value.isdigit():
        return datetime.strptime(value, "%Y%m%d").date()

    value_format = "%Y%m%dT%H%M%S" if len(value.rstrip("Z")) == 15 else "%Y%m%dT%H%M"
    parsed = datetime.strptime(value.rstrip("Z"), value_format)
    try:
        target_timezone = ZoneInfo(default_timezone)
    except ZoneInfoNotFoundError as error:
        raise ValueError(f"Unknown configured timezone: {default_timezone}") from error

    if value.endswith("Z"):
        return parsed.replace(tzinfo=timezone.utc).astimezone(target_timezone).date()
    event_timezone = params.get("TZID")
    if event_timezone:
        try:
            return parsed.replace(tzinfo=ZoneInfo(event_timezone)).astimezone(target_timezone).date()
        except ZoneInfoNotFoundError:
            pass
    return parsed.replace(tzinfo=target_timezone).date()


def _extract_packages(summary: str, description: str) -> list[dict[str, str]]:
    lines = [line.strip() for line in f"{summary}\n{description}".splitlines() if line.strip()]
    globals_: dict[str, str] = {}
    packages: list[dict[str, str]] = []
    current: dict[str, str] | None = None

    for line in lines:
        match = _LABEL_RE.match(line)
        if not match:
            continue
        canonical = _canonical_label(match.group("label"))
        value = match.group("value").strip()
        if not canonical or not value:
            continue
        if canonical == "package_name":
            if current:
                packages.append({**globals_, **current})
            current = {"package_name": value}
        elif canonical in {"project", "trade", "delivery_number"}:
            if current:
                current[canonical] = _delivery_number(value) if canonical == "delivery_number" else value
            else:
                globals_[canonical] = _delivery_number(value) if canonical == "delivery_number" else value
        elif canonical == "additional_info":
            delivery_number = _delivery_number(value)
            if delivery_number:
                if current:
                    current["delivery_number"] = delivery_number
                else:
                    globals_["delivery_number"] = delivery_number
        elif canonical in {"containers", "container_names"}:
            if current:
                current[canonical] = value
            else:
                globals_[canonical] = value

    if current:
        packages.append({**globals_, **current})
    return packages


def _canonical_label(label: str) -> str:
    compact = re.sub(r"[^a-z0-9]", "", label.casefold())
    aliases = {
        "project": "project",
        "job": "project",
        "jobname": "project",
        "package": "package_name",
        "packagename": "package_name",
        "stratuspackage": "package_name",
        "trade": "trade",
        "category": "trade",
        "dl": "delivery_number",
        "dlnumber": "delivery_number",
        "deliverynumber": "delivery_number",
        "additionalinfo": "additional_info",
        "containers": "containers",
        "containerscompleted": "containers",
        "containercount": "containers",
        "pallets": "containers",
        "containerids": "container_names",
        "containernames": "container_names",
    }
    return aliases.get(compact, "")


def _delivery_number(value: str) -> str:
    match = _DELIVERY_NUMBER_RE.search(value or "")
    if match:
        return match.group("number")
    return value.strip() if value.strip().isdigit() else ""
