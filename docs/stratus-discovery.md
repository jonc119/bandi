# Stratus Read-Only Discovery

- Inspected: 2026-08-16
- Stratus web version observed: 7.7.46
- Open API definition observed: 2026-08-10

## Confirmed Data Model

The package API exposes `id`, `name`, `projectId`, `currentTrackingStatusId`, and schedule-related
fields such as `requiredDT`. Package lookup also preserves `modelId` so reports can link directly
to the matching Stratus package. The container API exposes `id`, `name`, `currentTrackingStatusId`,
`partIds`, `assemblyCadIds`, and nested `containerIds`. In the live Tony Aguliar API view,
`packageIds` and `contents` were not populated. The checker therefore associates containers by
intersecting package part/assembly identifiers with the minimal identifiers returned for project
containers, then includes nested child containers.

Tracking status IDs resolve to names through the company tracking-status endpoint. Live container
screens showed status names including `MP - Field Received`, `SM - Field Received`, and
`EL - Field Received`, so the checker treats an exact terminal stage of `Field Received` as a pass
while retaining the original full status in reports.

## Confirmed Web Links

The signed-in Stratus web interface exposes these direct read paths:

```text
Package:   https://www.gtpstratus.com/orders?projectId={projectId}&modelId={modelId}&orderId={packageId}
Container: https://www.gtpstratus.com/containers?containerId={containerId}#tab_assign
```

The Excel investigation queue uses these URLs. A package that cannot be matched has no object ID,
so its fallback link opens the Stratus Packages page for manual searching instead of inventing a
detail URL.

## Allowlisted GET Endpoints

```text
GET /v1/package
GET /v1/project/{projectId}
GET /v1/project/{projectId}/containers
GET /v1/company/tracking-statuses?projectId={projectId}
GET /v2/package/{packageId}/assemblies
GET /v2/package/{packageId}/parts
```

The adapter refuses every other path, accepts only `https://api.gtpstratus.com`, disables redirects,
and constructs only HTTP GET requests. It contains no POST, PUT, PATCH, or DELETE capability.

## Authentication Boundary

The API requires a Stratus-generated app key in the `app-key` header. The application reads it
from `STRATUS_APP_KEY` or a Docker secret path named by `STRATUS_APP_KEY_FILE`. No key is present
in source code, TOML, Docker images, reports, drafts, logs, or SQLite.

The Company App Keys screen provides `Run as User` rather than endpoint-level scopes. A production
key must therefore run as a dedicated Stratus user whose company/project role is read-only. A key
running as an administrator or ordinary full-access user is not acceptable, even though this
adapter itself can issue only GET requests.
