# Southwest Delivery Email Intake

## Power Automate Flow

- Name: `Southwest Delivery ICS Intake`
- Flow ID: `1eac0f9c-2b3d-462e-bd79-be8b8540b824`
- Status: On
- Trigger: Office 365 Outlook `When a new email arrives (V3)`
- Subject filter: `Southwest Delivery Schedule`
- Only with attachments: Yes
- Include attachments: Yes
- Destination: OneDrive for Business `/Hermes Delivery QC/calendar-feed`
- File naming: UTC timestamp plus the original attachment name

The flow only copies matching attachments. It does not send, move, delete, forward, or reply to
email. The previous calendar-based flow remains off.

## Local Bridge

The installed 4:00 PM runner reads the business OneDrive folder and selects only `.ics` files.
Other attachments are preserved but ignored. It chooses the newest recent snapshot containing
package entries for the target delivery date, rather than blindly using a newer rolling export
that has already removed that day's events. An ICS must be no more than 96 hours old; a missing or
stale source fails closed. The selected file is copied atomically to `var/inbox/calendar-feed/`
before Docker reads it.

## Historical Backfill

Five matching messages received from 2026-08-10 through 2026-08-14 were preserved under
`var/inbox/`. No source message or attachment was deleted.

Historical checks query current Stratus state. They prove parsing, matching, count rules, and
present status, but not the status that existed at 4:00 PM on a past date. Prospective daily runs
create that timestamped evidence.
