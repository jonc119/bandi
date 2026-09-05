# ADR 0001: Shadow-Only Deterministic Core

- Status: Accepted
- Date: 2026-08-16

## Context

The checker will eventually support a delivery QC workflow involving schedule, Stratus status,
and follow-up communication. Those systems are not approved for connection yet.

## Decision

Implement the first release as a one-shot Python application with local ICS and CSV adapters,
deterministic business rules, SQLite history, and local reports. Keep Hermes outside the decision
path and forbid external writes.

## Consequences

- The business rules can be validated safely with exported snapshots.
- Reports remain useful even when no deliveries are scheduled.
- Email output is a draft artifact only.
- Later source adapters can replace local exports without rewriting the domain rules.
- Live integrations require a new ADR and explicit owner approval.
