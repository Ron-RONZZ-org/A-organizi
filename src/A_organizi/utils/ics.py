"""ICS (iCalendar) parsing and generation utilities.

Ported from autish-legacy kalendaro.py (lines 526-614, 997-1016).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any


def iter_ics_events(text: str) -> list[dict[str, str]]:
    """Parse ICS calendar text and extract VEVENT entries.

    Each VEVENT is returned as a dict with uppercase keys
    (DTSTART, DTEND, SUMMARY, LOCATION, etc.).

    Args:
        text: Raw ICS file content.

    Returns:
        List of event dicts.
    """
    events: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if line == "BEGIN:VEVENT":
            current = {}
            continue
        if line == "END:VEVENT":
            if current is not None:
                events.append(current)
            current = None
            continue
        if current is None or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.split(";", 1)[0].upper()
        current[key] = value.strip()
    return events


def ics_dt(value: str) -> datetime:
    """Parse an ICS datetime string into a timezone-aware datetime.

    Supports:
    - ``YYYYMMDDTHHMMSSZ`` (UTC)
    - ``YYYYMMDDTHHMMSS`` (local, treated as UTC)
    - ``YYYYMMDD`` (all-day, treated as UTC midnight)

    Args:
        value: ICS datetime string.

    Returns:
        Timezone-aware datetime in UTC.
    """
    if value.endswith("Z"):
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(
            tzinfo=timezone.utc
        )
    if "T" in value:
        return datetime.strptime(value, "%Y%m%dT%H%M%S").replace(
            tzinfo=timezone.utc
        )
    return datetime.strptime(value, "%Y%m%d").replace(tzinfo=timezone.utc)


def _to_iso(dt: datetime) -> str:
    """Convert a datetime to ISO 8601 string in UTC.

    Args:
        dt: Datetime object.

    Returns:
        ISO 8601 string (e.g. ``"2026-04-21T10:00:00+00:00"``).
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def events_to_ics(rows: list[dict[str, Any]]) -> str:
    """Generate ICS calendar text from event rows.

    Args:
        rows: List of event dicts with keys:
              ``uuid``, ``titolo``, ``komenco``, ``fino``,
              ``loko``, ``kategorio``, ``priskribo``.

    Returns:
        Valid ICS calendar string.
    """
    out = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//A//kalendaro//EO",
    ]
    for row in rows:
        # DB stores ISO 8601 strings; parse and format to ICS
        start_dt = datetime.fromisoformat(
            str(row["komenco"]).replace("Z", "+00:00")
        )
        end_dt = datetime.fromisoformat(
            str(row["fino"]).replace("Z", "+00:00")
        )
        start = start_dt.strftime("%Y%m%dT%H%M%SZ")
        end = end_dt.strftime("%Y%m%dT%H%M%SZ")
        out.extend([
            "BEGIN:VEVENT",
            f"UID:{row['uuid']}",
            f"SUMMARY:{str(row.get('titolo') or '')}",
            f"DTSTART:{start}",
            f"DTEND:{end}",
            f"LOCATION:{str(row.get('loko') or '')}",
            f"CATEGORIES:{str(row.get('kategorio') or '')}",
            f"DESCRIPTION:{str(row.get('priskribo') or '')}",
            "END:VEVENT",
        ])
    out.append("END:VCALENDAR")
    return "\n".join(out) + "\n"


def event_exists(
    db, calendar_uuid: str, title: str, start_iso: str, end_iso: str
) -> bool:
    """Check if an event with the same details already exists.

    Args:
        db: SQLiteDB instance.
        calendar_uuid: Calendar UUID.
        title: Event title.
        start_iso: Start datetime in ISO format.
        end_iso: End datetime in ISO format.

    Returns:
        True if a matching event exists.
    """
    row = db.execute_one(
        "SELECT 1 FROM eventoj "
        "WHERE kalendaro_uuid = ? AND titolo = ? AND komenco = ? AND fino = ?",
        (calendar_uuid, title, start_iso, end_iso),
    )
    return row is not None


def insert_ics_events(
    db, calendar_uuid: str, text: str, *, now: str | None = None
) -> list[str]:
    """Parse ICS text and insert events into the database.

    Skips events that already exist (dedup by
    calendar_uuid + titolo + komenco + fino).

    Args:
        db: SQLiteDB instance.
        calendar_uuid: Calendar UUID to associate events with.
        text: Raw ICS calendar text.
        now: Optional ISO timestamp override (defaults to current UTC).

    Returns:
        List of newly inserted event UUIDs.
    """
    ts = now or datetime.now(timezone.utc).replace(
        microsecond=0
    ).isoformat()
    added: list[str] = []

    for event in iter_ics_events(text):
        start = _to_iso(ics_dt(str(event.get("DTSTART", ts))))
        end = _to_iso(
            ics_dt(str(event.get("DTEND", event.get("DTSTART", ts))))
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


__all__ = [
    "iter_ics_events",
    "ics_dt",
    "events_to_ics",
    "event_exists",
    "insert_ics_events",
]
