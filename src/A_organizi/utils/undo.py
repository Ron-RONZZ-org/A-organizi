"""Undo utilities for calendar operations."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from A_organizi.data.storage import get_db

_MAX_UNDO = 30


# ──────────────────────────────────────────────────────────────────────────────
# Undo operations
# ──────────────────────────────────────────────────────────────────────────────


def push_undo(
    db,
    operation: str,
    payload: dict[str, Any],
) -> str:
    """Record an undo operation.

    Args:
        db: Database connection.
        operation: Operation type (delete_calendar, delete_event, import_events).
        payload: Operation payload (JSON-serializable).

    Returns:
        The change ID.
    """
    now = datetime.now().isoformat()
    change_id = uuid.uuid4().hex[:12]

    db.execute(
        """INSERT INTO undo_changes (id, operacio, payload, kreita_je)
           VALUES (?, ?, ?, ?)""",
        (change_id, operation, json.dumps(payload), now),
    )

    # Trim old undo records
    _trim_undo(db)

    return change_id


def _trim_undo(db) -> None:
    """Trim undo history to max size."""
    count = db.execute_one("SELECT COUNT(*) as n FROM undo_changes")
    if count and count.get("n", 0) > _MAX_UNDO:
        trim_count = count["n"] - _MAX_UNDO
        db.execute(
            f"""DELETE FROM undo_changes WHERE id IN (
              SELECT id FROM undo_changes ORDER BY kreita_je ASC LIMIT {trim_count}
            )"""
        )


def list_undos(
    db,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """List recent undo operations.

    Args:
        db: Database connection.
        limit: Maximum number to return.

    Returns:
        List of undo records.
    """
    rows = db.execute(
        "SELECT * FROM undo_changes ORDER BY kreita_je DESC LIMIT ?", (limit,)
    )
    result: list[dict[str, Any]] = []
    for row in rows:
        record = dict(row)
        record["payload"] = json.loads(row["payload"])
        result.append(record)
    return result


def apply_undo(
    db,
    change_id: str,
) -> bool:
    """Apply a specific undo operation.

    Args:
        db: Database connection.
        change_id: The change ID to undo.

    Returns:
        True if successful, False if not found.
    """
    row = db.execute_one(
        "SELECT * FROM undo_changes WHERE id = ?", (change_id,)
    )
    if not row:
        return False

    operation = row["operacio"]
    payload = json.loads(row["payload"])

    if operation == "delete_calendar":
        # Restore deleted calendar + its events
        _restore_calendar(db, payload)
    elif operation == "delete_event":
        # Restore deleted event
        _restore_event(db, payload)
    elif operation == "import_events":
        # Remove imported events
        _revert_import(db, payload)
    else:
        return False

    # Remove the undo record after applying
    db.execute("DELETE FROM undo_changes WHERE id = ?", (change_id,))
    return True


def _restore_calendar(db, payload: dict[str, Any]) -> None:
    """Restore a deleted calendar and its events.

    Args:
        db: Database connection.
        payload: Must contain 'calendar' and optionally 'events' key.
    """
    cal_data = payload.get("calendar")
    events_data = payload.get("events", [])

    if cal_data:
        db.execute(
            """INSERT INTO kalendaroj (uuid, url, username, remote, kreita_je, modifita_je)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                cal_data["uuid"],
                cal_data["url"],
                cal_data.get("username", ""),
                cal_data.get("remote", 1),
                cal_data["kreita_je"],
                cal_data["modifita_je"],
            ),
        )

    for ev in events_data:
        db.execute(
            """INSERT INTO eventoj
               (uuid, kalendaro_uuid, titolo, komenco, fino, kategorio, loko,
                ripeto, partoprenantoj, priskribo, kreita_je, modifita_je)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ev["uuid"],
                ev["kalendaro_uuid"],
                ev.get("titolo", ""),
                ev["komenco"],
                ev["fino"],
                ev.get("kategorio", ""),
                ev.get("loko", ""),
                ev.get("ripeto", ""),
                ev.get("partoprenantoj", "[]"),
                ev.get("priskribo", ""),
                ev["kreita_je"],
                ev["modifita_je"],
            ),
        )


def _restore_event(db, payload: dict[str, Any]) -> None:
    """Restore a deleted event.

    Args:
        db: Database connection.
        payload: Must contain 'event' key.
    """
    ev = payload.get("event")
    if not ev:
        return

    db.execute(
        """INSERT INTO eventoj
           (uuid, kalendaro_uuid, titolo, komenco, fino, kategorio, loko,
            ripeto, partoprenantoj, priskribo, kreita_je, modifita_je)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            ev["uuid"],
            ev["kalendaro_uuid"],
            ev.get("titolo", ""),
            ev["komenco"],
            ev["fino"],
            ev.get("kategorio", ""),
            ev.get("loko", ""),
            ev.get("ripeto", ""),
            ev.get("partoprenantoj", "[]"),
            ev.get("priskribo", ""),
            ev["kreita_je"],
            ev["modifita_je"],
        ),
    )


def _revert_import(db, payload: dict[str, Any]) -> None:
    """Remove imported events.

    Args:
        db: Database connection.
        payload: Must contain 'imported_uuids' list.
    """
    imported_uuids = payload.get("imported_uuids", [])
    if not imported_uuids:
        return

    for uid in imported_uuids:
        db.execute("DELETE FROM eventoj WHERE uuid = ?", (uid,))


# ──────────────────────────────────────────────────────────────────────────────
# Helper wrappers (use with service layer)
# ──────────────────────────────────────────────────────────────────────────────


def record_delete_calendar(
    db,
    calendar_uuid: str,
) -> str:
    """Record a calendar deletion for undo.

    Args:
        db: Database connection.
        calendar_uuid: The UUID of the calendar being deleted.

    Returns:
        The change ID.
    """
    # Get calendar data
    cal = db.execute_one(
        "SELECT * FROM kalendaroj WHERE uuid = ?", (calendar_uuid,)
    )
    if not cal:
        return ""

    # Get all events for this calendar
    events = db.execute(
        "SELECT * FROM eventoj WHERE kalendaro_uuid = ?", (calendar_uuid,)
    )

    payload = {
        "calendar": dict(cal),
        "events": [dict(e) for e in events],
    }

    return push_undo(db, "delete_calendar", payload)


def record_delete_event(
    db,
    event_uuid: str,
) -> str:
    """Record an event deletion for undo.

    Args:
        db: Database connection.
        event_uuid: The UUID of the event being deleted.

    Returns:
        The change ID.
    """
    ev = db.execute_one(
        "SELECT * FROM eventoj WHERE uuid = ?", (event_uuid,)
    )
    if not ev:
        return ""

    payload = {"event": dict(ev)}
    return push_undo(db, "delete_event", payload)


def record_import(
    db,
    imported_uuids: list[str],
) -> str:
    """Record an import for undo.

    Args:
        db: Database connection.
        imported_uuids: List of imported event UUIDs.

    Returns:
        The change ID.
    """
    payload = {"imported_uuids": imported_uuids}
    return push_undo(db, "import_events", payload)


__all__ = [
    "push_undo",
    "list_undos",
    "apply_undo",
    "record_delete_calendar",
    "record_delete_event",
    "record_import",
    "_MAX_UNDO",
]