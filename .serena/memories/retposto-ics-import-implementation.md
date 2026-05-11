# -R/--retposto : ICS Import from Email

## Summary
Added `--retposto/-R` to `A-organizi okazajo aldoni` to import calendar events from .ics files attached to emails in A-lien.

## Files Created
- `A-organizi/src/A_organizi/cli/okazajo_retposto.py` — CLI helpers (_import_from_retposto, _build_overrides, install prompt)
- `A-organizi/src/A_organizi/utils/retposto_ics.py` — domain logic (list_ics_attachments, import_ics_from_text, import_ics_from_messages)
- `A-organizi/tests/test_retposto_ics.py` — 20 tests

## Files Modified
- `A-organizi/src/A_organizi/cli/okazajo.py` — aldoni() now accepts -R/--retposto; traditional flags (titolo, komenco, fino) made optional
- `A-lien/src/A_lien/service/retposto_msg_ops.py` — added get_attachment_content() method

## Key Behavior
- `--retposto MSG_UUID1 MSG_UUID2` — message UUIDs (not account UUIDs)
- If A-lien not installed: prompt to install [J/n]
- Traditional flags + --retposto: traditional flags OVERWRITE .ics fields for all imported events
- If >1 event would be overwritten: warning in user locale
- Dedup by (calendar_uuid, titolo, komenco, fino)

## Issues
- A-organizi#18 (closed)
- A-lien#50 (closed)
