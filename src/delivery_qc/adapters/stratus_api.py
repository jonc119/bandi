from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID

from delivery_qc.domain.models import ContainerStatus, Delivery, MatchResult, MatchState
from delivery_qc.domain.normalize import normalize_text


_API_HOST = "api.gtpstratus.com"
_ALLOWED_PATHS = (
    re.compile(r"^/v1/package$"),
    re.compile(r"^/v1/company/tracking-statuses$"),
    re.compile(r"^/v1/project/[0-9a-f-]{36}$"),
    re.compile(r"^/v1/project/[0-9a-f-]{36}/containers$"),
    re.compile(r"^/v2/package/[0-9a-f-]{36}/assemblies$"),
    re.compile(r"^/v2/package/[0-9a-f-]{36}/parts$"),
)


class StratusApiError(RuntimeError):
    """Raised when a read-only Stratus request cannot be completed safely."""


@dataclass(frozen=True, slots=True)
class StratusPackage:
    id: str
    name: str
    project_id: str
    model_id: str


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


class StratusReadOnlyClient:
    def __init__(
        self,
        app_key: str,
        *,
        base_url: str = "https://api.gtpstratus.com",
        timeout_seconds: float = 30,
        opener: Any | None = None,
        project_mappings: dict[str, str] | None = None,
    ) -> None:
        parsed = urlparse(base_url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != _API_HOST
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(f"Stratus API base URL must be https://{_API_HOST}")
        if not app_key.strip():
            raise ValueError("A Stratus app key is required.")
        self._base_url = f"https://{_API_HOST}"
        self._app_key = app_key.strip()
        self._timeout_seconds = timeout_seconds
        self._opener = opener or build_opener(_NoRedirectHandler())
        self._project_mappings = {
            normalize_text(title): _uuid(project_id)
            for title, project_id in (project_mappings or {}).items()
        }
        self.resolutions: dict[str, MatchResult] = {}

    def list_packages_by_name(self, package_name: str) -> tuple[StratusPackage, ...]:
        packages: dict[str, StratusPackage] = {}
        for candidate_name in _package_name_variants(package_name):
            escaped_name = candidate_name.replace("'", "''")
            items = self._get_all_pages(
                "/v1/package",
                include="id,name,projectId,modelId",
                page_size=200,
                filters={"where": f"name eq '{escaped_name}'"},
            )
            for item in items:
                if item.get("id") and item.get("name") and item.get("projectId"):
                    packages[str(item["id"])] = StratusPackage(
                        id=str(item["id"]),
                        name=str(item["name"]),
                        project_id=str(item["projectId"]),
                        model_id=str(item.get("modelId") or ""),
                    )
            if packages:
                break
        return tuple(packages.values())

    def project_name(self, project_id: str) -> str:
        safe_project_id = _uuid(project_id)
        response = self._get_json(f"/v1/project/{safe_project_id}")
        if not isinstance(response, dict):
            raise StratusApiError("Stratus returned an invalid project response.")
        return str(response.get("name") or response.get("projectName") or response.get("number") or "")

    def project_containers(self, project_id: str) -> tuple[dict[str, Any], ...]:
        safe_project_id = _uuid(project_id)
        return tuple(
            self._get_all_pages(
                f"/v1/project/{safe_project_id}/containers",
                include=(
                    "id,name,currentTrackingStatusId,packageIds,containerIds,"
                    "parentContainerId,contents,partIds,assemblyCadIds"
                ),
                page_size=1000,
            )
        )

    def package_assemblies(self, package_id: str) -> tuple[dict[str, Any], ...]:
        return tuple(
            self._get_all_pages(
                f"/v2/package/{_uuid(package_id)}/assemblies",
                include="id,cadId",
                page_size=1000,
            )
        )

    def package_parts(self, package_id: str) -> tuple[dict[str, Any], ...]:
        return tuple(
            self._get_all_pages(
                f"/v2/package/{_uuid(package_id)}/parts",
                include="id,cadId",
                page_size=100,
            )
        )

    def tracking_statuses(self, project_id: str) -> dict[str, str]:
        response = self._get_json(
            "/v1/company/tracking-statuses",
            {"projectId": _uuid(project_id)},
        )
        if not isinstance(response, list):
            raise StratusApiError("Stratus returned an invalid tracking-status response.")
        return {
            str(item.get("id")): str(item.get("name"))
            for item in response
            if isinstance(item, dict) and item.get("id") and item.get("name")
        }

    def statuses_for_deliveries(
        self, deliveries: tuple[Delivery, ...]
    ) -> tuple[ContainerStatus, ...]:
        observed_at = datetime.now(timezone.utc).isoformat()
        output: list[ContainerStatus] = []
        project_cache: dict[str, str] = {}
        container_cache: dict[str, tuple[dict[str, Any], ...]] = {}
        status_cache: dict[str, dict[str, str]] = {}
        self.resolutions = {}

        for delivery in deliveries:
            candidates = self.list_packages_by_name(delivery.package_name)
            mapped_project = self._project_mappings.get(normalize_text(delivery.raw_summary))
            matches: list[tuple[StratusPackage, str]] = []
            for package in candidates:
                if package.project_id not in project_cache:
                    project_cache[package.project_id] = self.project_name(package.project_id)
                project_name = project_cache[package.project_id]
                if mapped_project and package.project_id != mapped_project:
                    continue
                if not delivery.project or normalize_text(project_name) == normalize_text(delivery.project):
                    matches.append((package, project_name))
            evidence = tuple(
                f"CANDIDATE: {package.id} | {project_cache[package.project_id]} | {package.name}"
                for package in candidates
            )
            if mapped_project:
                evidence += (f"REVIEWED_PROJECT_MAPPING: {delivery.raw_summary} -> {mapped_project}",)
            if len(matches) != 1:
                self.resolutions[delivery.source_uid] = MatchResult(
                    MatchState.AMBIGUOUS if candidates else MatchState.NOT_FOUND,
                    evidence=evidence + ("DELIVERY_STATUS_UNVERIFIED",),
                )
                continue

            package, project_name = matches[0]
            if package.project_id not in container_cache:
                container_cache[package.project_id] = self.project_containers(package.project_id)
            if package.project_id not in status_cache:
                status_cache[package.project_id] = self.tracking_statuses(package.project_id)
            containers = container_cache[package.project_id]
            status_names = status_cache[package.project_id]
            assembly_cad_ids = {
                    str(item.get("cadId"))
                    for item in self.package_assemblies(package.id)
                    if item.get("cadId")
                }
            part_ids = {
                    str(item.get("id"))
                    for item in self.package_parts(package.id)
                    if item.get("id")
                }
            selected_containers = _containers_for_package(
                    containers,
                    package.id,
                    package_part_ids=part_ids,
                    package_assembly_cad_ids=assembly_cad_ids,
                )
            package_statuses: list[ContainerStatus] = []
            for container in selected_containers:
                status_id = str(container.get("currentTrackingStatusId") or "")
                package_statuses.append(
                    ContainerStatus(
                        project=project_name or delivery.project,
                        package_name=delivery.package_name,
                        container_name=str(container.get("name") or container.get("id") or ""),
                        status=status_names.get(status_id, ""),
                        observed_at=observed_at,
                        container_id=str(container.get("id") or ""),
                        package_id=package.id,
                        project_id=package.project_id,
                        model_id=package.model_id,
                    )
                )
            output.extend(package_statuses)
            self.resolutions[delivery.source_uid] = MatchResult(
                MatchState.MATCHED if package_statuses else MatchState.NO_CONTAINERS,
                tuple(package_statuses),
                evidence + (f"SELECTED_PACKAGE: {package.id}", f"STATUS_OBSERVED_AT: {observed_at}"),
            )
        return tuple(output)

    def _get_all_pages(
        self, path: str, *, include: str, page_size: int,
        filters: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        previous_pages: set[str] = set()
        for page in range(100):
            response = self._get_json(
                path,
                {
                    **(filters or {}),
                    "include": include,
                    "page": str(page),
                    "pagesize": str(page_size),
                    "disabletotal": "false",
                },
            )
            data = _paged_data(response)
            if response.get("truncatedResults"):
                raise StratusApiError("Stratus truncated the result; inventory is unverified.")
            signature = json.dumps(data, sort_keys=True)
            if data and signature in previous_pages:
                raise StratusApiError("Stratus repeated a page; inventory is unverified.")
            previous_pages.add(signature)
            output.extend(data)
            total = response.get("total")
            if total is not None:
                if len(output) > int(total):
                    raise StratusApiError("Stratus inventory changed during pagination.")
                if len(output) == int(total):
                    return output
                if not data:
                    raise StratusApiError("Stratus inventory is incomplete.")
            elif len(data) < page_size:
                return output
        raise StratusApiError("Stratus pagination exceeded the 100-page safety limit.")

    def _get_json(self, path: str, query: dict[str, str] | None = None) -> Any:
        if not any(pattern.fullmatch(path) for pattern in _ALLOWED_PATHS):
            raise StratusApiError(f"Blocked non-allowlisted Stratus path: {path}")
        url = f"{self._base_url}{path}"
        if query:
            url = f"{url}?{urlencode(query)}"
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "app-key": self._app_key,
                "User-Agent": "Hermes-Delivery-QC/0.1 shadow-read-only",
            },
            method="GET",
        )
        try:
            with self._opener.open(request, timeout=self._timeout_seconds) as response:
                payload = response.read(20 * 1024 * 1024 + 1)
                if len(payload) > 20 * 1024 * 1024:
                    raise StratusApiError("Stratus response exceeds the 20 MiB safety limit.")
                return json.loads(payload.decode("utf-8"))
        except HTTPError as error:
            raise StratusApiError(f"Stratus GET failed with HTTP {error.code}.") from error
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            raise StratusApiError("Stratus GET failed or returned invalid JSON.") from error


def _uuid(value: str) -> str:
    try:
        return str(UUID(value))
    except (ValueError, AttributeError) as error:
        raise StratusApiError("Stratus returned an invalid project id.") from error


def _package_name_variants(package_name: str) -> tuple[str, ...]:
    variants = [package_name]
    missing_closing_parentheses = package_name.count("(") - package_name.count(")")
    if missing_closing_parentheses > 0:
        variants.append(package_name + ")" * missing_closing_parentheses)
    return tuple(dict.fromkeys(variants))


def _paged_data(response: Any) -> list[dict[str, Any]]:
    if not isinstance(response, dict) or not isinstance(response.get("data"), list):
        raise StratusApiError("Stratus returned an invalid paged response.")
    return [item for item in response["data"] if isinstance(item, dict)]


def _containers_for_package(
    containers: tuple[dict[str, Any], ...],
    package_id: str,
    *,
    package_part_ids: set[str] | None = None,
    package_assembly_cad_ids: set[str] | None = None,
) -> tuple[dict[str, Any], ...]:
    package_part_ids = package_part_ids or set()
    package_assembly_cad_ids = package_assembly_cad_ids or set()
    by_id = {
        str(container.get("id")): container
        for container in containers
        if container.get("id")
    }
    if len(by_id) != len(containers):
        raise StratusApiError("Container IDs are missing or duplicated; inventory is unverified.")
    selected_ids = {
        container_id
        for container_id, container in by_id.items()
        if package_id in {str(value) for value in container.get("packageIds") or ()}
        or any(
            str(item.get("referenceId") or "") == package_id
            and _is_package_reference(item.get("referenceType"))
            for item in container.get("contents") or ()
            if isinstance(item, dict)
        )
        or bool(
            package_part_ids.intersection(
                str(value) for value in container.get("partIds") or ()
            )
        )
        or bool(
            package_assembly_cad_ids.intersection(
                str(value) for value in container.get("assemblyCadIds") or ()
            )
        )
    }
    changed = True
    while changed:
        changed = False
        for container_id, container in by_id.items():
            parent_id = str(container.get("parentContainerId") or "")
            referenced_children = {str(value) for value in container.get("containerIds") or ()}
            if container_id in selected_ids:
                new_children = referenced_children - selected_ids
                if new_children:
                    selected_ids.update(new_children)
                    changed = True
            elif parent_id in selected_ids:
                selected_ids.add(container_id)
                changed = True
    if selected_ids - by_id.keys():
        raise StratusApiError("A referenced nested container is missing; inventory is unverified.")
    return tuple(by_id[container_id] for container_id in sorted(selected_ids))


def _is_package_reference(value: Any) -> bool:
    normalized = str(value or "").strip().casefold()
    return normalized in {"4", "package", "4 = package"}
