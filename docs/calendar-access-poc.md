# Calendar Access Proof of Concept

## Result

On 2026-08-16, the signed-in Outlook Web session displayed 17 events from `Southwest Delivery Schedule` for 2026-08-17. Their date and title set matched all 17 events in `var/inbox/southwest-delivery-schedule-2026-08-16.ics`.

The ICS supplied the package descriptions needed by the deterministic checker. It classified six Stratus deliveries and eleven unrelated calendar events. A read-only Stratus shadow run completed with one package passed and five packages flagged for review. No email was sent and no company record was modified.

## Current Limitation

The current Outlook permission exposes event dates and titles but not event descriptions. Downloading an individual event through Outlook Web also omits the description. Browser capture alone therefore cannot recover package names, container counts, or other delivery metadata required for a complete QC run.

## Safe Temporary Use

The browser title capture can detect whether the visible daily schedule still matches the latest approved ICS snapshot. Any added, removed, renamed, or moved event must be treated as a stale-input warning; the checker must not silently reuse old package details for a changed event.

## Production Gate

Keep the Power Automate flow off until the shared calendar is selectable with sufficient read access. Production automation should use the supported Microsoft 365 connector rather than an authenticated browser session. Shadow mode remains required until separately approved.
