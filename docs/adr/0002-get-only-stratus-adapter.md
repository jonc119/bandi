# ADR 0002: Allowlisted GET-Only Stratus Adapter

- Status: Accepted
- Date: 2026-08-16

## Context

Manual CSV exports are safe but make a 4:00 PM automated shadow check unreliable. Stratus provides
an Open API with package-to-container relationships and tracking-status IDs.

## Decision

Add an optional adapter that uses only six allowlisted GET endpoint patterns on
`https://api.gtpstratus.com`. Accept the app key through an environment variable or Docker secret
file. Keep the
default Docker service network-disabled, and do not activate the adapter until key handling and
runtime egress are separately approved. Require the app key to run as a dedicated read-only
Stratus user because Stratus App Keys inherit user permissions rather than endpoint scopes.

## Consequences

- The deterministic checker can consume authoritative package/container status data.
- Division-prefixed `Field Received` statuses are handled correctly.
- The adapter cannot call any Stratus write or delete endpoint.
- An approved secret and network deployment remain required before a live shadow run.
