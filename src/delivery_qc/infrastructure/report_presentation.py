from __future__ import annotations

from hashlib import sha256
from urllib.parse import quote

from delivery_qc.domain.models import PackageResult, ResultCode


STRATUS_WEB_BASE = "https://www.gtpstratus.com"
STRATUS_ORDERS_URL = f"{STRATUS_WEB_BASE}/orders"

ISSUE_BY_RESULT = {
    ResultCode.PASS_COMPLETE: "All expected containers are Field Received",
    ResultCode.FLAG_PARTIAL_DELIVERY: "Only some matched containers are Field Received",
    ResultCode.FLAG_NOT_RECEIVED: "No matched containers are Field Received",
    ResultCode.FLAG_CONTAINER_MISMATCH: (
        "Calendar count does not match the Stratus container count"
    ),
    ResultCode.FLAG_PACKAGE_NOT_FOUND: "No exact package match; delivery status is unverified",
    ResultCode.FLAG_AMBIGUOUS_PACKAGE: (
        "Package name matched more than one Stratus package"
    ),
    ResultCode.FLAG_STATUS_UNKNOWN: "Container status or expected inventory is unverified",
}

ACTION_BY_RESULT = {
    ResultCode.PASS_COMPLETE: "No action required",
    ResultCode.FLAG_PARTIAL_DELIVERY: (
        "Confirm when the remaining containers will be delivered"
    ),
    ResultCode.FLAG_NOT_RECEIVED: "Verify shipment and field-receipt timing",
    ResultCode.FLAG_CONTAINER_MISMATCH: (
        "Reconcile the calendar count against Stratus containers"
    ),
    ResultCode.FLAG_PACKAGE_NOT_FOUND: (
        "Confirm the package name and project, then search Stratus"
    ),
    ResultCode.FLAG_AMBIGUOUS_PACKAGE: "Confirm the correct project/package match",
    ResultCode.FLAG_STATUS_UNKNOWN: "Review the raw Stratus status values",
}

LABEL_BY_RESULT = {
    ResultCode.PASS_COMPLETE: "Complete",
    ResultCode.FLAG_PARTIAL_DELIVERY: "Partial delivery",
    ResultCode.FLAG_NOT_RECEIVED: "Not received",
    ResultCode.FLAG_CONTAINER_MISMATCH: "Count mismatch",
    ResultCode.FLAG_PACKAGE_NOT_FOUND: "Match unresolved",
    ResultCode.FLAG_AMBIGUOUS_PACKAGE: "Ambiguous package",
    ResultCode.FLAG_STATUS_UNKNOWN: "Unverified evidence",
}


def power_bi_filter_url(base_url: str, field: str, value: str) -> str:
    if not base_url or not value:
        return ""
    escaped_value = value.replace("'", "''")
    separator = "&" if "?" in base_url else "?"
    expression = f"{field} eq '{escaped_value}'"
    return f"{base_url}{separator}filter={quote(expression, safe='')}"


def package_url(result: PackageResult) -> str:
    if not result.containers:
        return ""
    container = result.containers[0]
    if not container.package_id or not container.project_id or not container.model_id:
        return ""
    return (
        f"{STRATUS_ORDERS_URL}?projectId={container.project_id}"
        f"&modelId={container.model_id}&orderId={container.package_id}"
    )


def container_url(container_id: str) -> str:
    if not container_id:
        return ""
    return f"{STRATUS_WEB_BASE}/containers?containerId={container_id}#tab_assign"


def result_project(result: PackageResult) -> str:
    if result.delivery.project:
        return result.delivery.project
    return result.containers[0].project if result.containers else ""


def issue_anchor(source_uid: str) -> str:
    digest = sha256(source_uid.encode("utf-8")).hexdigest()[:12]
    return f"issue-{digest}"
