# Current Project Handoff

## Objective

Deliver a deterministic 4:00 PM Eastern delivery QC system that compares the Southwest delivery
calendar with read-only Stratus package/container evidence, flags every incomplete or ambiguous
delivery, and presents a mobile-friendly investigation dashboard.

## Current Task

Finish the remaining release gates, validate the hardened runtime, and move from shadow mode only
after the evidence source, scheduled execution, dashboard, and notification path are all proven.
Separately, configure the isolated Qwen Open WebUI coding lane before returning to the release gates.

## Current State

- The deterministic checker, reports, history dashboard, Excel export, and direct Stratus/Power BI
  investigation links are implemented.
- Matching now unions direct, part, and assembly container membership and preserves stable-ID audit
  evidence. Missing, duplicated, ambiguous, or incomplete data fails closed.
- Export protections, calendar-snapshot disagreement checks, and a restricted health-aware dashboard
  server are implemented in source.
- The project test suite passes 45 tests using the bundled Python runtime with `PYTHONPATH=src`.
- Six local-coder controller security tests pass.
- Codex CLI 0.147.0 was smoke-tested against Ollama and explicitly reported
  `model: qwen3.8:latest`, `provider: ollama`, then returned the expected response.
- Always launch Qwen with explicit `--oss --local-provider ollama` flags. Do not rely on
  `codex -p qwen` alone, because an unresolved profile can inherit the OpenAI provider.
- Qwen Open WebUI setup uses an isolated clone and `qwen/agent` branch. It must not receive the live
  Delivery QC workspace or its runtime material.
- The dedicated clone exists at `C:\Users\jonc1\AI\bandi-qwen`; its clean `qwen/agent` branch is
  published to GitHub. The five-minute `Bandi Qwen Branch Sync` host task was manually verified with
  result code 0. The private `bandi-qwen-terminal` container is healthy, has no host port or internet
  route, and mounts only that clone.
- Open WebUI now uses a stable ignored signing key and a server-side `Bandi Qwen Terminal` connection.
  Its replacement container is healthy and can reach the terminal over the private Docker network. The
  stopped pre-Qwen Open WebUI containers are retained locally for rollback. The connection is enabled and
  bound only to the sole Open WebUI administrator. On 2026-09-05 the actual browser picker and file
  browser were verified. The root cause of the hidden connection was PowerShell serializing a singleton
  as an object rather than an array; the replacement script now preserves the array explicitly.
- The saved coding chat uses Native function calling and the isolated terminal:
  `http://100.82.38.123:3000/c/b0f8b209-635a-4d9e-8f0c-1b42eca837f1`.
  Qwen read both instruction files, wrote `work/qwen-smoke/verification.py`, ran it successfully, and
  ran all 45 project tests successfully through Open WebUI. No tracked files changed during that test.
- Luna reviewed the replacement script; follow-up fixes check rollback exit codes, keep secret values
  out of Docker command arguments, and refuse unexpected network attachments. Docker administrators
  can still inspect container environment values. The existing LAN/Tailscale port binding is preserved.
- `AGENTS.md` records lower-cost delegation and mandatory OpenAI review of the exact Qwen commit
  before merge. GitHub branch protection is not certified here. Local work can continue while hosted
  usage is unavailable; review and merge wait for availability.
- The latest local Qwen smoke run correctly stopped with `TESTS_FAILED`; its proposed tests were not
  merged and production files were not changed.
- The project remains in shadow mode. No statement in this file authorizes go-live.

## Important Decisions

- An LLM may help write and review code or investigate nomenclature, but may never determine a
  delivery pass/fail result.
- Stratus operations remain GET-only. Never add writes or delete company records.
- Unknown calendar coverage, source outages, incomplete inventory, or ambiguous matches are review
  conditions, never successful deliveries.
- Email transmission remains disabled in shadow mode.
- Local Qwen and hosted Codex share state through this file, `AGENTS.md`, tests, and Git—not chat
  history.

## Files Currently Involved

- `src/delivery_qc/adapters/stratus_api.py`
- `src/delivery_qc/application/checker.py`
- `src/delivery_qc/infrastructure/dashboard_server.py`
- `src/delivery_qc/infrastructure/database.py`
- `src/delivery_qc/infrastructure/export_safety.py`
- `scripts/run-daily-shadow.ps1`
- `compose.yaml`
- `tests/test_release_blockers.py`

## Tests / Validation

Preferred container validation:

```powershell
docker compose run --rm --entrypoint python -v "${PWD}\tests:/app/tests:ro" delivery-qc -m unittest discover -s /app/tests -v
```

Bundled local Python validation:

```powershell
$env:PYTHONPATH = "src"
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m unittest discover -s tests -v
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m unittest discover -s local-coder -v
```

Last observed result: 45 project tests passed and 6 controller tests passed on 2026-09-05.

## Known Issues / Release Blockers

- The Power Automate calendar connection does not expose the Southwest delivery calendar. A recent
  run failed because a display name was supplied where a real calendar ID was required.
- The newly hardened dashboard image/source has not been proven as the currently running viewer.
- The automatic notification channel has not been implemented and end-to-end validated.
- Dedicated Stratus key scope, secret handling, and the final production security review still need
  direct verification.
- `config/qc.toml`, `var/`, `work/`, and `outputs/` contain local/runtime material and are excluded
  from Git. Do not inspect or expose credentials unless a specific authorized task requires it.

## Next Actions

1. Review the current repository diff and the release-gate changes listed above.
2. Re-run the full tests and inspect failures without weakening deterministic safety rules.
3. Resolve and prove authoritative calendar intake using a real accessible calendar ID or approved
   attachment-based intake.
4. Deploy and verify the hardened dashboard while preserving the existing instance for rollback.
5. Implement and test the approved notification path, then complete the go-live checklist.
6. Use the verified saved coding chat from the iPhone over Tailscale. Give Qwen a bounded task and
   leave its commits on `qwen/agent` for the OpenAI review gate described in `AGENTS.md`.

## Last Known Good Commit

`6b6181f` — `checkpoint before local Qwen handoff`

This checkpoint was created only after confirming that runtime data, browser state, generated
reports, `config/qc.toml`, and `var/secrets/` were not staged.
