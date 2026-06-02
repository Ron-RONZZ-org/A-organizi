"""Calendar and event services for kalendaro."""

from __future__ import annotations

from datetime import date
from typing import Any

from A.core.service import CRUDService

from A_organizi.data.storage import get_db

_kalendaro_service: CalendarService | None = None
_evento_service: EventService | None = None


class CalendarService(CRUDService):
    """CRUDService for kalendaroj (calendars) with URL validation."""

    def find_by_uuid_prefix(self, prefix: str, limit: int = 10) -> list[dict[str, Any]]:
        """Find calendars whose UUID starts with prefix (uses core CRUD method)."""
        return super().find_by_uuid_prefix(prefix.lstrip("#"), limit=limit)

    def resolve_uuid(self, ref: str) -> str | None:
        """Resolve a user reference to a calendar UUID.

        Tries exact match first, then unique prefix match.

        Args:
            ref: UUID or UUID prefix (with or without #).

        Returns:
            Full UUID string, or None if not found or ambiguous.
        """
        token = ref.lstrip("#")
        # Exact match
        row = self.db.execute_one(
            "SELECT uuid FROM kalendaroj WHERE uuid = ?", (token,)
        )
        if row:
            return str(row["uuid"])
        # Prefix match (must be unique)
        rows = self.db.execute(
            "SELECT uuid FROM kalendaroj WHERE uuid LIKE ? ORDER BY uuid",
            (f"{token}%",),
        )
        if len(rows) == 1:
            return str(rows[0]["uuid"])
        return None

    def calendar_exists(self, url: str, username: str) -> bool:
        """Check if a calendar with the given URL and username exists.

        Args:
            url: Calendar URL.
            username: Username.

        Returns:
            True if a matching calendar exists.
        """
        row = self.db.execute_one(
            "SELECT 1 FROM kalendaroj WHERE LOWER(url)=LOWER(?) AND LOWER(username)=LOWER(?)",
            (url.strip(), username.strip()),
        )
        return row is not None

    def delete(self, uuid: str, soft: bool = True) -> None:
        """Delete a calendar and all its events.

        Args:
            uuid: Calendar UUID.
            soft: If True, move to trash (not used for calendars).
        """
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM eventoj WHERE kalendaro_uuid = ?", (uuid,))
            conn.execute("DELETE FROM kalendaroj WHERE uuid = ?", (uuid,))


class EventService(CRUDService):
    """CRUDService for eventoj (events) with date-range queries."""

    def find_by_uuid_prefix(self, prefix: str, limit: int = 10) -> list[dict[str, Any]]:
        """Find events whose UUID starts with prefix (uses core CRUD method)."""
        return super().find_by_uuid_prefix(prefix.lstrip("#"), limit=limit)

    def resolve_uuid(self, ref: str) -> str | None:
        """Resolve a user reference to an event UUID.

        Args:
            ref: UUID or UUID prefix (with or without #).

        Returns:
            Full UUID string, or None if not found or ambiguous.
        """
        token = ref.lstrip("#")
        row = self.db.execute_one(
            "SELECT uuid FROM eventoj WHERE uuid = ?", (token,)
        )
        if row:
            return str(row["uuid"])
        rows = self.db.execute(
            "SELECT uuid FROM eventoj WHERE uuid LIKE ? ORDER BY uuid",
            (f"{token}%",),
        )
        if len(rows) == 1:
            return str(rows[0]["uuid"])
        return None

    def list_by_date_range(
        self,
        start: date,
        end: date,
        calendar_uuids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """List events in a date range, optionally filtered by calendar.

        Args:
            start: Start date (inclusive).
            end: End date (inclusive).
            calendar_uuids: Optional list of calendar UUIDs to filter by.

        Returns:
            List of event dicts.
        """
        params: list[str] = [start.isoformat(), end.isoformat()]
        query = (
            "SELECT * FROM eventoj "
            "WHERE date(komenco) >= ? AND date(komenco) <= ?"
        )
        if calendar_uuids:
            placeholders = ",".join("?" for _ in calendar_uuids)
            query += f" AND kalendaro_uuid IN ({placeholders})"
            params.extend(calendar_uuids)
        query += " ORDER BY komenco ASC"
        return self.db.execute(query, tuple(params))

    def delete_by_date_range(
        self,
        start: date,
        end: date,
        calendar_uuids: list[str] | None = None,
    ) -> int:
        """Delete events in a date range.

        Args:
            start: Start date (inclusive).
            end: End date (inclusive).
            calendar_uuids: Optional list of calendar UUIDs to filter by.

        Returns:
            Number of deleted events.
        """
        params: list[str] = [start.isoformat(), end.isoformat()]
        query = (
            "DELETE FROM eventoj "
            "WHERE date(komenco) >= ? AND date(komenco) <= ?"
        )
        if calendar_uuids:
            placeholders = ",".join("?" for _ in calendar_uuids)
            query += f" AND kalendaro_uuid IN ({placeholders})"
            params.extend(calendar_uuids)
        with self.db.transaction() as conn:
            cursor = conn.execute(query, tuple(params))
            return cursor.rowcount

    def search(
        self,
        query: str | None = None,
        *,
        kalendaro: list[str] | None = None,
        kategorio: str | None = None,
        loko: str | None = None,
        dato_de: str | None = None,
        dato_gxis: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Search events with combinable filters.

        Args:
            query: Search text (matches titolo + priskribo).
            kalendaro: Filter by calendar UUIDs.
            kategorio: Filter by category.
            loko: Filter by location.
            dato_de: Start date (ISO) lower bound.
            dato_gxis: Start date (ISO) upper bound.
            limit: Maximum results.

        Returns:
            List of matching event dicts.
        """
        rows = self.db.execute("SELECT * FROM eventoj")
        filtered: list[dict[str, Any]] = [dict(r) for r in rows]

        if kalendaro:
            allowed = set(
                rid for ref in kalendaro
                for rid in [self.resolve_uuid(ref)]
                if rid is not None
            )
            filtered = [
                r for r in filtered if str(r.get("kalendaro_uuid")) in allowed
            ]
        if kategorio:
            low = kategorio.lower()
            filtered = [
                r
                for r in filtered
                if low in str(r.get("kategorio") or "").lower()
            ]
        if loko:
            low = loko.lower()
            filtered = [
                r
                for r in filtered
                if low in str(r.get("loko") or "").lower()
            ]
        if dato_de:
            filtered = [
                r
                for r in filtered
                if str(r.get("komenco") or "") >= dato_de
            ]
        if dato_gxis:
            filtered = [
                r
                for r in filtered
                if str(r.get("komenco") or "") <= dato_gxis
            ]
        if query:
            q = query.lower()
            filtered = [
                r
                for r in filtered
                if q in str(r.get("titolo") or "").lower()
                or q in str(r.get("priskribo") or "").lower()
            ]

        return filtered[:limit]

    # ── Sync hooks ───────────────────────────────────────────────────────

    def _post_create(self, data: dict[str, Any], result: dict[str, Any]) -> None:
        """Enqueue a CalDAV push after local event creation.

        Args:
            data: The input data passed to create().
            result: The created entry with generated UUID and timestamps.
        """
        self._enqueue_sync_for_event(result, "create")

    def _post_update(
        self, uuid: str, old_data: dict[str, Any] | None, new_data: dict[str, Any]
    ) -> None:
        """Enqueue a CalDAV push after local event update.

        Uses ``old_data`` (full event before update) to determine calendar
        ownership, then re-reads the full event from DB for the payload so
        the push includes all fields.

        Args:
            uuid: Entry UUID.
            old_data: The entry state before update (may be None).
            new_data: Partial update dict (only changed fields).
        """
        if old_data is None:
            return
        # Re-read the full event post-update to capture all fields
        full = self.db.execute_one(
            "SELECT * FROM eventoj WHERE uuid = ?", (uuid,)
        )
        event_data = dict(full) if full else old_data
        self._enqueue_sync_for_event(event_data, "update")

    def _post_delete(self, uuid: str, data: dict[str, Any] | None, soft: bool) -> None:
        """Enqueue a CalDAV push after local event deletion.

        Args:
            uuid: Entry UUID.
            data: The entry data before deletion (None if not found).
            soft: True if moved to trash, False if permanently deleted.
        """
        if data is not None:
            self._enqueue_sync_for_event(data, "delete")

    def _enqueue_sync_for_event(
        self,
        event_data: dict[str, Any],
        operation: str,
    ) -> None:
        """Enqueue a CalDAV push job for an event mutation.

        Silently skips if the owning calendar has no remote URL configured.
        Starts the background worker on first enqueue.

        Args:
            event_data: The event dict (must include ``kalendaro_uuid`` and ``uuid``).
            operation: One of ``"create"``, ``"update"``, ``"delete"``.
        """
        cal_uuid = event_data.get("kalendaro_uuid", "")
        if not cal_uuid:
            return

        # Check whether the calendar is remote
        cal = self.db.execute_one(
            "SELECT remote, url FROM kalendaroj WHERE uuid = ?", (cal_uuid,)
        )
        if not cal or not cal.get("remote") or not cal.get("url", "").strip():
            return  # Local-only calendar, nothing to push

        with self.db.transaction() as conn:
            from A_organizi.utils.sync import queue_sync
            queue_sync(
                conn,
                calendar_uuid=cal_uuid,
                operation="push",
                payload={
                    "event_uuid": event_data.get("uuid", ""),
                    "operation": operation,
                    "event_data": event_data,
                },
            )

        # Ensure the background worker is running
        from A_organizi.utils.sync import start_sync_worker
        start_sync_worker()

    def delete_by_date_range(
        self,
        start: date,
        end: date,
        calendar_uuids: list[str] | None = None,
    ) -> int:
        """Delete events in a date range, triggering ``_post_delete`` per event.

        Args:
            start: Start date (inclusive).
            end: End date (inclusive).
            calendar_uuids: Optional list of calendar UUIDs to filter by.

        Returns:
            Number of deleted events.
        """
        events = self.list_by_date_range(start, end, calendar_uuids)
        count = 0
        for event in events:
            self.delete(event["uuid"], soft=False)
            count += 1
        return count


def get_kalendaro_service() -> CalendarService:
    """Get the singleton CalendarService for kalendaroj table."""
    global _kalendaro_service
    if _kalendaro_service is None:
        _kalendaro_service = CalendarService(get_db(), "kalendaroj")
    return _kalendaro_service


def get_evento_service() -> EventService:
    """Get the singleton EventService for eventoj table."""
    global _evento_service
    if _evento_service is None:
        _evento_service = EventService(get_db(), "eventoj")
    return _evento_service


__all__ = [
    "CalendarService",
    "EventService",
    "get_kalendaro_service",
    "get_evento_service",
]
