# Matching hardening and go-live gates

This release remains shadow-only. Zero-defect performance is not a credible promise.

## Changes implemented

- Preserve per-calendar-item match results, including duplicate candidates and package IDs, before container evaluation. An ambiguous lookup cannot become a missing-package result.
- Resolve the verified `Seminole - Arlen` calendar title to project ID `483a7d6f-4c6b-43f4-b02d-5973fe3ddaee`. Evidence was a read-only Stratus lookup of both duplicate roof-curb packages: Sheetmetal Sandbox and 4807_BIM - Seminole High School. The latter returned Pallet 0505, SM - Field Received, matching the one-pallet expectation. Mapping is exact-title, not fuzzy, and cannot override contradictory explicit project data.
- Preserve candidate IDs, selected package, mapping and observation time in report warnings. These are audit evidence, not instructions.
- Distinguish missing packages, ambiguous packages and packages without container evidence. Unmatched items show unverified quantities, not a confirmed missed shipment.
- Reject unknown expected inventory, zero counts, duplicate container names, incomplete package candidate pages and malformed calendars. Preserve different container IDs instead of merging by display name. Cancelled calendar entries are ignored; recurring delivery entries require an expanded source.
- Unknown calendar entries require classification review rather than silent exclusion.

## Verification checkpoint — September 5, 2026

- 38 automated tests pass using the bundled Python interpreter (`py` is unavailable on this host).
- Live Stratus metadata confirmed `pageCount` counts rows on the current page, not total pages. Pagination now follows collected rows versus `total`, rejects truncation/repeated pages, and refuses incomplete inventory.
- Rebuilt the shadow Docker image and successfully appended run `c7b7ec09-7e4e-400a-9124-66b7628354cf` for the September 4 delivery date using the same September 3 calendar snapshot as the original report. This is a retrospective recheck, not verification of the latest calendar feed.
- Current-status results: 12 packages, 8 passes, 4 flagged. Roof curb is PASS_COMPLETE with Pallet 0505 Field Received and 1 expected/1 observed. Both duplicate candidates and the exact reviewed project mapping are retained in audit evidence.
- The local dashboard returned HTTP 200 and contained the new run. No email was sent and no Stratus data or historical run was deleted.
- These are September 5 observations, not proof of receipt by the September 4 cutoff. Go-live gates below remain open.

## Appropriate AI roles

Qwen was used locally as an independent regression-test reviewer during this change. It received only a generic technical scenario, not company source data or credentials. Its suggestions were reviewed, not executed blindly.

Hermes remains the read-only report explanation interface. It must report match uncertainty and quote the deterministic result; it must not convert a suggestion into PASS. The checker does not yet invoke Hermes/Qwen automatically to resolve names. That is intentional until a bounded candidate-suggestion workflow is tested: supply candidate IDs and sanitized source context, accept a schema-validated suggestion only, obtain human approval for a mapping, then rerun deterministic inventory and status checks. No AI-written Stratus status changes, emails, shell execution, configuration edits or automatic approvals.

## Required before go-live

- Review a representative set of shipping days against warehouse evidence, including every flagged item and a sample of passes. Record false positives, false negatives, source coverage and reviewer signoff.
- Verify calendar freshness, date coverage, updates, cancellations, duplicate UIDs and recurring-event expansion. The existing scheduled wrapper can choose an older snapshot containing deliveries; it must not be treated as authoritative evidence of the latest calendar.
- Verify complete container membership: direct package links, part/assembly membership, nested containers and moved contents. Current part/assembly fallback runs only when direct membership is empty; mixed membership remains a release blocker.
- Add receipt transition timestamps or label results strictly as current status. A later Field Received observation cannot prove a delivery was received by 4 PM.
- Test duplicate display names through database persistence; the legacy table keys on container name and must be migrated before supporting those cases without a run failure.
- Verify failures are visible remotely and do not leave stale reports looking current. Calendar REVIEW notices are not yet included in all historical issue-rate metrics.
- Finish the outstanding security-audit remediation, including spreadsheet formula injection, credential storage, dependency findings and dashboard access protections.
- Test the full unattended schedule and notification path. Explicit user go-live approval remains mandatory; this change does not enable email transmission.

Historical reports are retained. Rechecks append new runs and describe present observations rather than changing past receipt facts.
