# Delivery QC Agent Instructions

## Scope

This repository implements a deterministic delivery quality-control checker for manufactured Stratus packages and containers.

## Safety Rules

- Keep `deployment.mode` set to `shadow` until the user explicitly approves go-live.
- Do not connect email, calendars, Stratus, or other company systems without explicit approval for that integration phase.
- Do not add Stratus write operations. Status access must remain read-only.
- Do not send email in shadow mode. Draft generation is allowed; transmission is not.
- Do not let an LLM determine pass/fail results. Domain rules must remain deterministic and tested.
- Do not treat a source outage, missing file, ambiguous match, or unknown count as a successful delivery.
- Preserve raw source values and audit evidence alongside normalized values.
- Do not store credentials in source files, committed configuration, fixtures, logs, or reports.

## Development

- Target Python 3.13 and prefer the standard library for the offline core.
- Keep domain logic independent from files, databases, networks, Hermes, and Stratus.
- Add or update tests for every business-rule change.
- Run `py -m unittest discover -s tests -v` before handoff.
- Keep runtime data under `var/`; source code must not depend on checked-in runtime artifacts.

## Architecture

- `src/delivery_qc/domain/` owns deterministic matching and pass/fail rules.
- `src/delivery_qc/adapters/` reads calendar snapshots and GET-only Stratus data.
- `src/delivery_qc/infrastructure/` stores audit evidence and renders reports.
- `scripts/` contains operator-controlled runners; automation must fail closed.
- `tests/` contains synthetic fixtures and all required regression coverage.
- `var/`, `work/`, and `outputs/` are runtime or generated data and must never be committed.

## Agent Handoff

Before ending substantial work:

1. Run the required tests.
2. Review `git status` and `git diff`; never stage credentials or runtime data.
3. Update `HANDOFF.md` with completed work, uncertainty, blockers, and next actions.
4. Do not claim deployment or go-live unless the current environment was directly verified.
5. Leave a small, reviewable checkpoint; do not begin another major task after handoff.

## Local Qwen Coding Lane

- Qwen works only in the dedicated `qwen/agent` branch inside its isolated terminal workspace.
- Qwen may read, edit, test, and commit code in that branch. It must never merge, rebase, force-push,
  or change `main`.
- Qwen must run relevant tests before every commit and update `HANDOFF.md` before stopping.
- The host-side sync task may push only `qwen/agent` to the fixed `https://github.com/jonc119/bandi.git`
  remote. A human or Astra reviews and merges that branch later.
