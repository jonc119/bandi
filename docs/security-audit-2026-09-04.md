# Delivery QC security audit — September 4, 2026

## Assessment

Remediation is needed before broader rollout. The checker has useful isolation and request controls, but confirmed spreadsheet injection and fail-open input handling need correction. This review does not establish that a compromise has occurred or that none has occurred.

Scope: local source, configuration, report generation, Windows secret ACLs, Docker runtime metadata, Tailscale routes, and one local checker-image vulnerability scan. No company records, credentials, firewall rules, or production code were changed. Synthetic probes used temporary files and a harmless `=1+1` formula; Excel itself was not launched.

## Findings, ordered by priority

### 1. High — Untrusted input becomes spreadsheet formulas

Confirmed with synthetic package/project values `=1+1`: generated XLSX cells were stored as formulas in Dashboard A11/B11, Package Review C5/D5, and Container Detail C5/D5. Daily CSV also preserves formula prefixes. Historical CSV writes source strings directly through the same unsafe pattern.

Locations: `src/delivery_qc/infrastructure/excel_report.py:229`, `src/delivery_qc/infrastructure/reports.py:330`, `src/delivery_qc/infrastructure/history_report.py:376`.

An attacker who can influence imported delivery fields could supply formulas that execute when a recipient opens an export. External calls or other effects depend on Excel version and security settings; this audit demonstrated formula creation, not data exfiltration or code execution.

Remediation: explicitly store untrusted XLSX values as text. Neutralize formula-leading CSV fields, including leading whitespace/control characters, while preserving original evidence in JSON. Add regression tests for package, project, container and status fields.

### 2. High integrity risk — Invalid schedule can become a successful empty report

Confirmed: a file containing `This is not a calendar` is accepted by `parse_ics` and returns zero deliveries. The checker permits zero-delivery runs, so a malformed/replaced input can suppress investigations without causing a source failure. Input selection validates extension and file age, not calendar structure or provenance.

Locations: `src/delivery_qc/adapters/ics_schedule.py:40`, `scripts/run-daily-shadow.ps1:127`, `src/delivery_qc/application/checker.py`.

Remediation: validate VCALENDAR/VEVENT structure and distinguish a valid empty schedule from invalid input. Verify permitted senders and attachment provenance in Power Automate; reject unexpected inputs. The documented flow shows a subject filter but the live sender/authentication conditions were not inspected, so email spoofing susceptibility is unverified.

Related integrity defect: `src/delivery_qc/domain/rules.py:52` records an unknown expected count as a warning, and line 63 can still PASS. This conflicts with the repository's explicit unknown-count safety rule. Treat unknown counts as investigation unless independently complete expected-container evidence is available.

### 3. Medium — Plaintext API key resides under OneDrive project storage

Confirmed: Compose binds `var/secrets/stratus_app_key`, beneath the project's OneDrive path. Git exclusion does not prevent OneDrive synchronization. Actual cloud synchronization/sharing of that file was not verified.

Positive checks: no Everyone/Users/Authenticated Users allow entries were found in the inspected secret ACL; exact-key comparison found no duplicate in other scanned small text files; generic source scans found no hardcoded credential candidates. Binary files, large files and Git history were not comprehensively scanned; this directory has no `.git` repository.

Remediation: move future secret storage outside synchronized folders into protected local storage or a credential manager, update the secret mount, and rotate the existing key if cloud exposure is confirmed. Preserve records according to the user's no-deletion requirement.

The key runs as Tony Aguilar per setup history. Effective Stratus permissions were not inspected. The GET-only Python adapter does not constrain a stolen key's server-side authority. Confirm a dedicated read-only role before broader rollout.

### 4. Medium — Report access relies entirely on network reachability

Confirmed runtime: dashboard uses Python `http.server`, serves the whole reports directory, and has no separate login. A request to `/2026-09-04/` returned HTTP 200 and a directory listing. Cache-Control and X-Frame-Options were absent in that response. Archived JSON contains raw schedule details beyond the summary UI.

Location: `compose.yaml:45`.

The host binding is correctly restricted to 127.0.0.1. Tailscale explicitly reports both routes as **tailnet only**, with no Funnel exposure; current status showed one peer, the iPhone. Devices/users allowed to reach HTTPS can access the QC route without the Hermes login. Tailnet ACLs, device posture and account MFA were not inspected; peer count does not prove ACL restrictions.

Remediation: restrict tailnet grants to approved identities/devices; use a report-serving application with explicit route/file allowlists, no directory listings, suitable cache/security headers, and identity enforcement where needed. Preserve existing private-only access.

### 5. Medium — Container hardening and egress gaps

Confirmed: Hermes runs as root with no configured capability drop, writable `/opt/data` and `/qc`, and a normal bridge network. QC report/draft mounts are read-only and no Docker socket was present. Hermes has a read-only root filesystem, no-new-privileges, 4 GB memory and 256 PID limits.

The dashboard runs as `deliveryqc`, drops all capabilities, and has a read-only reports mount, but has no memory/PID limits. The offline checker has `network_mode: none`; the Stratus checker and Hermes use ordinary networks without an egress allowlist in the inspected Compose configuration. Actual network egress was not actively tested.

Locations: `compose.yaml`, `work/hermes-docker-compose.yml` plus live Docker inspection.

Remediation: run Hermes under a compatible non-root UID, drop unnecessary capabilities, restrict writable paths and egress, and add resource limits for checker/viewer services. Revalidate Hermes tool restrictions separately against live configuration; documentation alone is insufficient.

### 6. Medium — Resource exhaustion through unbounded inputs

ICS input and individual HTTP responses are read fully into memory. There are no file/body-size caps or event/package-count caps. API pagination does have a 100-page limit and requests have a 30-second timeout. Combined with missing resource limits, unusually large or hostile input can disrupt availability.

Locations: `src/delivery_qc/adapters/ics_schedule.py:40`, `src/delivery_qc/adapters/stratus_api.py:249`.

Remediation: enforce input and response byte limits, total-run/request budgets, schema limits, and container memory/CPU/PID caps.

### 7. Scanner findings — High severity advisories require reachability triage

Docker Scout analyzed local checker image digest prefix `15d15e24f8fd`, 148 packages, using a high/critical filter. It reported zero critical and four high advisory entries across three packages:

| Detected component | Advisory | Scanner remediation |
|---|---|---|
| msgpack 1.1.2 | GHSA-6v7p-g79w-8964 | 1.2.1 |
| msgpack 1.1.2 | CVE-2026-57585 | 1.2.1 |
| zlib 1:1.3.dfsg+really1.3.1-1 | CVE-2026-85091 | No fix reported |
| setuptools 70.3.0 | CVE-2025-47273 | 78.1.1 |

These are scanner-reported entries, not four proven exploitable paths; GHSA/CVE entries may describe the same underlying vulnerability. Top-level package inspection found only pip 26.2.1, delivery-qc 0.1.0, openpyxl 3.1.5 and et_xmlfile 2.0.0. msgpack/setuptools are not top-level application dependencies; package locations and possible vendoring need triage. No vulnerable function was exercised.

The running static viewer uses an older image (ID prefix `a435bc7a5e92`), so these scan results do not certify that viewer image. Hermes and Open WebUI were not vulnerability-scanned. Medium/low advisories were excluded by the scan filter. Base/runtime images and Python dependency ranges are not pinned to a reviewed lock/digest policy.

Remediation: obtain package locations/SBOM, assess reachable code, update or remove affected build tooling in runtime images, rebuild and scan all deployed images. Pin reviewed versions and retain an update process.

### 8. Adjacent exposure — Open WebUI listens on all host interfaces

Live Docker inspection shows Open WebUI port 3000 published on `0.0.0.0` and IPv6, unlike the loopback-only Hermes/QC ports. This expands potential LAN access. Windows firewall and router exposure were not verified, so internet reachability is not established.

Remediation: review the intended access boundary and restrict bindings/firewall access if Tailscale is the only required remote path. Do not change this adjacent service without assessing the existing remote workflow.

## Other integrity and trust limitations

- Historical presets are anchored to the last checked delivery date. Missing days are not counted or highlighted as failures, and reruns replace the prior day's totals in the summary. Historical backfills query current Stratus state. Period totals cannot establish complete original 4 PM performance. Add coverage/staleness indicators and distinguish original checks from later rechecks.
- Reports carry untrusted calendar/source text into Hermes. HTML escapes display fields, but prompt-injection resistance is not proven by escaping. Keep source evidence separate from instructions and verify live tool restrictions.
- Config paths accept absolute/out-of-workspace targets and dashboard URL schemes are not validated. These require configuration control rather than an ordinary calendar-only attacker. Constrain them to intended roots and HTTPS allowlisted destinations.
- The scheduled runner records failures, but the dashboard does not consume failed-run health. A stale successful report can remain visible during an outage.

## Verified strengths

- Stratus requests use a fixed HTTPS host, allowlisted paths, GET, UUID validation for relevant IDs and disabled redirects.
- SQL writes and history reads use bound parameters for values.
- HTML display values are escaped; the history script updates counters via textContent. No raw calendar text is intentionally inserted into executable JavaScript.
- Shadow mode is enforced in configuration; no email-sending path was identified in the project.
- Report/draft mounts into Hermes are read-only; the deterministic checker owns the decisions.
- Private HTTPS access is through Tailscale Serve, with no Funnel exposure observed.

## Recommended work order

1. Fix XLSX/CSV injection and invalid/unknown input success paths; add targeted regressions.
2. Protect the credential outside synchronized storage and verify effective read-only Stratus permissions.
3. Restrict report-serving routes and tailnet access; surface failed/missing checks.
4. Harden Hermes identity/capabilities and resource/egress controls.
5. Triage scanner findings, rebuild every deployed image, and repeat verification.

The existing functional suite passed 19 tests immediately before this audit; those tests did not cover the newly reproduced security defects. This audit did not alter application behavior or claim a clean penetration-test result.
