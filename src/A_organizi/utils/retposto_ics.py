"""Integration between A-lien email attachments and A-organizi calendar import.

Provides functions to scan email messages for .ics attachments and import
calendar events from them, with optional CLI flag overrides.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from A.utils.output import info
from A_organizi.utils.ics import ics_dt, _to_iso, event_exists, iter_ics_events


def list_ics_attachments(
    retposto_svc: Any, message_uuids: list[str],
) -> dict[str, list[dict[str, Any]]]:
    """Filter email messages for those containing .ics attachments.

    Args:
        retposto_svc: A-lien RetpostoService instance.
        message_uuids: Email message UUIDs to check.

    Returns:
        Dict mapping msg_uuid -> list of .ics attachment dicts.
    """
    result: dict[str, list[dict[str, Any]]] = {}
    for msg_uuid in message_uuids:
        attachments = retposto_svc.get_attachments(msg_uuid)
        ics_atts = [
            a for a in attachments
            if a.get("dosiernomo", "").lower().endswith(".ics")
            or a.get("mime_tipo", "") == "text/calendar"
        ]
        if ics_atts:
            result[msg_uuid] = ics_atts
    return result


def count_ics_events(ics_text: str) -> int:
    """Count VEVENT entries in ICS text.

    Args:
        ics_text: Raw ICS calendar text.

    Returns:
        Number of VEVENT entries.
    """
    return len(iter_ics_events(ics_text))


def _apply_overrides(
    event: dict[str, str], overrides: dict[str, str],
) -> dict[str, str]:
    """Apply CLI field overrides to a parsed ICS VEVENT dict.

    Maps CLI flag names to ICS field names:
      titolo -> SUMMARY, loko -> LOCATION, kategorio -> CATEGORIES,
      priskribo -> DESCRIPTION, ripeto -> RRULE.

    Args:
        event: Raw VEVENT dict from iter_ics_events().
        overrides: Dict of CLI flag values (keyed by Python param name).

    Returns:
        Updated event dict with override fields replaced.
    """
    field_map = {
        "titolo": "SUMMARY",
        "loko": "LOCATION",
        "kategorio": "CATEGORIES",
        "priskribo": "DESCRIPTION",
        "ripeto": "RRULE",
    }
    result = dict(event)
    for cli_key, ics_key in field_map.items():
        if cli_key in overrides:
            result[ics_key] = overrides[cli_key]
    return result


def import_ics_from_text(
    db: Any,
    calendar_uuid: str,
    ics_text: str,
    overrides: dict[str, str] | None = None,
    *,
    now: str | None = None,
) -> list[str]:
    """Parse ICS text, apply optional overrides, and insert events.

    Reuses the same dedup logic as insert_ics_events() (checks
    calendar_uuid + titolo + komenco + fino).

    Args:
        db: SQLiteDB instance.
        calendar_uuid: Target calendar UUID.
        ics_text: Raw ICS calendar text.
        overrides: Optional field overrides (titolo, loko, kategorio, etc.).
        now: Optional ISO timestamp override (default: current UTC).

    Returns:
        List of newly inserted event UUIDs.
    """
    ts = now or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    added: list[str] = []

    for event in iter_ics_events(ics_text):
        if overrides:
            event = _apply_overrides(event, overrides)

        start = _to_iso(ics_dt(str(event.get("DTSTART", ts))))
        end = _to_iso(
            ics_dt(str(event.get("DTEND", event.get("DTSTART", ts)))),
        )
        title = str(event.get("SUMMARY", ""))

        if event_exists(db, calendar_uuid, title, start, end):
            continue

        uid = str(uuid.uuid4())
        participants: list[str] = []
        if "ATTENDEE" in event:
            participants.append(str(event["ATTENDEE"]))

        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO eventoj ("
                "uuid, kalendaro_uuid, titolo, komenco, fino, "
                "kategorio, loko, ripeto, partoprenantoj, priskribo, "
                "kreita_je, modifita_je"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    uid,
                    calendar_uuid,
                    title,
                    start,
                    end,
                    str(event.get("CATEGORIES", "")),
                    str(event.get("LOCATION", "")),
                    str(event.get("RRULE", "")),
                    json.dumps(participants, ensure_ascii=False),
                    str(event.get("DESCRIPTION", "")),
                    ts,
                    ts,
                ),
            )
        added.append(uid)

    return added


def import_ics_from_messages(
    db: Any,
    calendar_uuid: str,
    retposto_svc: Any,
    message_uuids: list[str],
    overrides: dict[str, str] | None = None,
) -> dict[str, list[str]]:
    """Import .ics calendar events from email message attachments.

    For each message UUID, finds .ics attachments, extracts their content,
    parses events, applies optional overrides, and inserts into DB.

    Args:
        db: SQLiteDB instance.
        calendar_uuid: Target calendar UUID.
        retposto_svc: A-lien RetpostoService instance.
        message_uuids: Email message UUIDs to scan.
        overrides: Optional CLI flag overrides.

    Returns:
        Dict mapping msg_uuid -> list of imported event UUIDs.
    """
    result: dict[str, list[str]] = {}
    for msg_uuid in message_uuids:
        attachments = retposto_svc.get_attachments(msg_uuid)
        ics_atts = [
            a for a in attachments
            if a.get("dosiernomo", "").lower().endswith(".ics")
            or a.get("mime_tipo", "") == "text/calendar"
        ]
        if not ics_atts:
            continue

        imported: list[str] = []
        for att in ics_atts:
            try:
                content = retposto_svc.get_attachment_content(
                    msg_uuid, att["dosiernomo"],
                )
                ics_text = content.decode("utf-8", errors="replace")
                imported.extend(
                    import_ics_from_text(db, calendar_uuid, ics_text, overrides),
                )
            except Exception as exc:
                info(f"  [~] {att['dosiernomo']}: {exc}")
        if imported:
            result[msg_uuid] = imported

    return result


__all__ = [
    "list_ics_attachments",
    "count_ics_events",
    "import_ics_from_text",
    "import_ics_from_messages",
]
