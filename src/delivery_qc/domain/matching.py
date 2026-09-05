from __future__ import annotations

from collections import defaultdict

from delivery_qc.domain.models import (
    ContainerStatus,
    Delivery,
    MatchResult,
    MatchState,
)
from delivery_qc.domain.normalize import normalize_text


def match_package(
    delivery: Delivery,
    statuses: tuple[ContainerStatus, ...],
) -> MatchResult:
    package_key = normalize_text(delivery.package_name)
    project_key = normalize_text(delivery.project)

    package_groups: dict[tuple[str, str, str], list[ContainerStatus]] = defaultdict(list)
    for status in statuses:
        key = (normalize_text(status.project), normalize_text(status.package_name), status.package_id)
        package_groups[key].append(status)

    package_matches = [
        group
        for (candidate_project, candidate_package, candidate_id), group in package_groups.items()
        if candidate_package == package_key and (not project_key or candidate_project == project_key)
    ]
    if not package_matches:
        return MatchResult(MatchState.NOT_FOUND)
    if len(package_matches) > 1:
        return MatchResult(MatchState.AMBIGUOUS)
    return MatchResult(MatchState.MATCHED, _deduplicate(package_matches[0]))


def _deduplicate(statuses: list[ContainerStatus]) -> tuple[ContainerStatus, ...]:
    by_container: dict[str, ContainerStatus] = {}
    for status in statuses:
        key = status.container_id or normalize_text(status.container_name) or f"row-{len(by_container)}"
        previous = by_container.get(key)
        if previous is None or status.observed_at >= previous.observed_at:
            by_container[key] = status
    return tuple(sorted(by_container.values(), key=lambda item: normalize_text(item.container_name)))
