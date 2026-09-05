# Local coding while ChatGPT is unavailable

## Start

Double-click `Start Local Coding.cmd` in the project folder. Keep Docker Desktop and Ollama running.
This uses `qwen3.8:latest` through `127.0.0.1:11434`; it makes no OpenAI API calls and needs no ChatGPT quota.

Or run from PowerShell in the project folder:

```powershell
.\scripts\run-local-coder.ps1
.\scripts\run-local-coder.ps1 -Task inventory-guard-tests -Rounds 2
```

The default queue contains three small test-writing jobs. Each job gets a fresh snapshot and at most
two edit/test attempts, then stops. Rerunning intentionally creates new review runs; jobs are not
silently promoted, merged, or marked done across invocations. Close the terminal or press Ctrl+C to
stop the controller. If interrupted during testing, its uniquely named test container may still need
`docker stop <name>`; do not delete it. The controller is not an unattended scheduler or rate-limit monitor.

## Results

Under `var/local-coder/<timestamp-id>/`:

- `status.json`: READY_FOR_REVIEW, TESTS_FAILED or BLOCKED.
- `review.diff`: proposed changes relative to the captured source.
- `proposal-N.json`: Qwen's complete proposed file contents and explanation.
- `baseline-tests.txt` and `tests-N.txt`: actual container test results.
- `source-hashes.json`: baseline integrity manifest for checking drift before review.
- `workspace/`: isolated edited copy, never the production project.

READY_FOR_REVIEW means only that tests passed. It does not mean the code is correct, approved, or deployed.
When ChatGPT is available, ask it to review the latest diffs, check baseline hashes against current source,
inspect test quality, and merge only approved changes with a fresh full test run.

## Boundaries

- Only project source, synthetic fixtures/tests, README, pyproject and AGENTS are copied. No `var/inbox`,
  reports, secrets, business calendar files, compose configuration, `.env`, or company connection tokens.
- Only task-declared `src/*.py` or `tests/*.py` paths are editable. The worker cannot write edits back to
  production. Configure narrowly scoped jobs in `tasks.json`; file allowlists are enforced in code.
- Qwen has no tools, browser, shell, MCP or credential access. The host controller invokes only Ollama
  and a fixed Docker test command. Model output is validated as data, never executed on Windows.
- Proposed Python runs as non-root in a separate read-only, network-disabled container with only the
  isolated source copy mounted read-only. It has a temporary RAM filesystem and CPU/memory/PID/time
  limits. No Docker socket, host home, credentials or production folders are mounted.
- Test containers are preserved, not automatically deleted, honoring the no-deletion requirement.
  They and retained workspaces consume disk; review storage periodically.
- Tests and source can still be wrong or malicious. Container isolation reduces risk; it is not a
  security proof. Review diffs and tests manually. Do not give the local model production write access.
- Hermes stays the report-reading assistant. Its permissions and mounts are unchanged. Using a separate
  coding controller avoids giving the delivery agent shell or deployment privileges.

## Current project handoff

Verified smoke run: `var/local-coder/20260905T181547Z-a4f15cf7`. Qwen generated 16 export
tests and Docker executed them alongside the 45 baseline tests. Three generated assertions failed;
the worker correctly recorded `TESTS_FAILED` and left production untouched. These failures require
review of both expectations and implementation, not automatic weakening of tests to get a green run.

The project is not live. Source improvements include export safety, mixed container membership,
stable-ID evidence storage, calendar disagreement guards and a restricted health-aware dashboard.
The image was rebuilt, but the hardened dashboard has not replaced the running old viewer. Verify
the full suite and deployment separately. Production calendar access and automatic notifications are
still unresolved; the calendar connector lists no Southwest delivery calendar. Never fake coverage.

The shared recommendation at `https://chatgpt.com/s/t_6a9c5aa2c8a0819189d8baf9799966d6` could not be
read: web fetch failed and browser policy blocked broader ChatGPT-origin access. This implementation
is an independent safe handoff, not a claim to reproduce that recommendation. Paste its contents to
adapt the setup if it specifies a particular coding client.
