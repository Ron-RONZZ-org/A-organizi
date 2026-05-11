"""Tests for A_organizi.utils.retposto_ics — ICS import from email."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

SAMPLE_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EO
BEGIN:VEVENT
UID:test-uid-1
SUMMARY:Test Event
DTSTART:20260501T100000Z
DTEND:20260501T110000Z
LOCATION:Office
CATEGORIES:Meeting
DESCRIPTION:A test event
END:VEVENT
BEGIN:VEVENT
UID:test-uid-2
SUMMARY:Second Event
DTSTART:20260502T140000Z
DTEND:20260502T150000Z
LOCATION:Conference Room
CATEGORIES:Meetup
END:VEVENT
END:VCALENDAR"""

SINGLE_EVENT_ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:single-uid
SUMMARY:Single Event
DTSTART:20260503T090000Z
DTEND:20260503T100000Z
END:VEVENT
END:VCALENDAR"""


# ── list_ics_attachments ────────────────────────────────────────────────────


class TestListIcsAttachments:
    """Tests for list_ics_attachments()."""

    def test_empty_uuid_list(self):
        """Empty message list returns empty dict."""
        from A_organizi.utils.retposto_ics import list_ics_attachments

        mock_svc = Mock()
        mock_svc.get_attachments.return_value = []
        result = list_ics_attachments(mock_svc, [])
        assert result == {}

    def test_no_ics_attachments(self):
        """Messages without .ics attachments are excluded."""
        from A_organizi.utils.retposto_ics import list_ics_attachments

        mock_svc = Mock()
        mock_svc.get_attachments.return_value = [
            {"dosiernomo": "photo.jpg", "mime_tipo": "image/jpeg"},
        ]
        result = list_ics_attachments(mock_svc, ["msg-1"])
        assert result == {}

    def test_filters_ics_by_extension(self):
        """Filters attachments with .ics extension."""
        from A_organizi.utils.retposto_ics import list_ics_attachments

        mock_svc = Mock()
        mock_svc.get_attachments.return_value = [
            {"dosiernomo": "invite.ics", "mime_tipo": "text/calendar"},
            {"dosiernomo": "photo.jpg", "mime_tipo": "image/jpeg"},
        ]
        result = list_ics_attachments(mock_svc, ["msg-1"])
        assert "msg-1" in result
        assert len(result["msg-1"]) == 1
        assert result["msg-1"][0]["dosiernomo"] == "invite.ics"

    def test_filters_ics_by_mime(self):
        """Filters attachments with text/calendar MIME type even without .ics ext."""
        from A_organizi.utils.retposto_ics import list_ics_attachments

        mock_svc = Mock()
        mock_svc.get_attachments.return_value = [
            {"dosiernomo": "calendar", "mime_tipo": "text/calendar"},
        ]
        result = list_ics_attachments(mock_svc, ["msg-1"])
        assert "msg-1" in result
        assert len(result["msg-1"]) == 1

    def test_multiple_messages(self):
        """Multiple message UUIDs return aggregated results."""
        from A_organizi.utils.retposto_ics import list_ics_attachments

        mock_svc = Mock()
        def side_effect(uuid):
            if uuid == "msg-a":
                return [{"dosiernomo": "a.ics", "mime_tipo": "text/calendar"}]
            return [{"dosiernomo": "b.ics", "mime_tipo": "text/calendar"}]
        mock_svc.get_attachments.side_effect = side_effect

        result = list_ics_attachments(mock_svc, ["msg-a", "msg-b"])
        assert set(result.keys()) == {"msg-a", "msg-b"}


# ── count_ics_events ────────────────────────────────────────────────────────


class TestCountIcsEvents:
    """Tests for count_ics_events()."""

    def test_counts_two_events(self):
        """Counts VEVENT entries in multi-event ICS."""
        from A_organizi.utils.retposto_ics import count_ics_events

        assert count_ics_events(SAMPLE_ICS) == 2

    def test_counts_single_event(self):
        """Counts single VEVENT entry."""
        from A_organizi.utils.retposto_ics import count_ics_events

        assert count_ics_events(SINGLE_EVENT_ICS) == 1

    def test_no_events_returns_zero(self):
        """Empty VCALENDAR returns 0."""
        from A_organizi.utils.retposto_ics import count_ics_events

        assert count_ics_events("BEGIN:VCALENDAR\nEND:VCALENDAR") == 0

    def test_empty_string(self):
        """Empty string returns 0."""
        from A_organizi.utils.retposto_ics import count_ics_events

        assert count_ics_events("") == 0


# ── import_ics_from_text ────────────────────────────────────────────────────


class TestImportIcsFromText:
    """Tests for import_ics_from_text()."""

    @pytest.fixture
    def db_conn(self, tmp_path):
        """Create an in-memory SQLiteDB with eventoj schema."""
        from A.data.base import SQLiteDB

        db = SQLiteDB(str(tmp_path / "test.db"))
        db.execute(
            "CREATE TABLE IF NOT EXISTS eventoj ("
            "uuid TEXT PRIMARY KEY,"
            "kalendaro_uuid TEXT NOT NULL,"
            "titolo TEXT NOT NULL DEFAULT '',"
            "komenco TEXT NOT NULL,"
            "fino TEXT NOT NULL,"
            "kategorio TEXT NOT NULL DEFAULT '',"
            "loko TEXT NOT NULL DEFAULT '',"
            "ripeto TEXT NOT NULL DEFAULT '',"
            "partoprenantoj TEXT NOT NULL DEFAULT '[]',"
            "priskribo TEXT NOT NULL DEFAULT '',"
            "kreita_je TEXT NOT NULL,"
            "modifita_je TEXT NOT NULL"
            ")"
        )
        return db

    def test_import_basic(self, db_conn):
        """Imports all events from valid ICS text."""
        from A_organizi.utils.retposto_ics import import_ics_from_text

        cal_uuid = "cal-001"
        added = import_ics_from_text(db_conn, cal_uuid, SAMPLE_ICS)
        assert len(added) == 2

        rows = db_conn.execute(
            "SELECT titolo, loko, kategorio FROM eventoj ORDER BY komenco",
        )
        titles = [r["titolo"] for r in rows]
        assert "Test Event" in titles
        assert "Second Event" in titles

    def test_import_dedup(self, db_conn):
        """Duplicate events are skipped."""
        from A_organizi.utils.retposto_ics import import_ics_from_text

        cal_uuid = "cal-001"
        added1 = import_ics_from_text(db_conn, cal_uuid, SAMPLE_ICS)
        added2 = import_ics_from_text(db_conn, cal_uuid, SAMPLE_ICS)
        assert len(added1) == 2
        assert len(added2) == 0

    def test_import_with_overrides(self, db_conn):
        """Overrides replace ICS fields for all events."""
        from A_organizi.utils.retposto_ics import import_ics_from_text

        cal_uuid = "cal-001"
        overrides = {"titolo": "Overridden Title", "loko": "Virtual"}
        added = import_ics_from_text(db_conn, cal_uuid, SAMPLE_ICS, overrides)
        assert len(added) == 2

        rows = db_conn.execute(
            "SELECT titolo, loko FROM eventoj ORDER BY komenco",
        )
        for row in rows:
            assert row["titolo"] == "Overridden Title"
            assert row["loko"] == "Virtual"

    def test_import_partial_overrides(self, db_conn):
        """Only specified fields are overridden, others come from ICS."""
        from A_organizi.utils.retposto_ics import import_ics_from_text

        cal_uuid = "cal-001"
        overrides = {"kategorio": "Imported"}
        added = import_ics_from_text(db_conn, cal_uuid, SAMPLE_ICS, overrides)
        assert len(added) == 2

        rows = db_conn.execute(
            "SELECT titolo, kategorio FROM eventoj ORDER BY komenco",
        )
        first = rows[0]
        assert first["titolo"] == "Test Event"  # from ICS, not overridden
        assert first["kategorio"] == "Imported"

    def test_now_override(self, db_conn):
        """Explicit 'now' parameter is used for timestamps."""
        from A_organizi.utils.retposto_ics import import_ics_from_text

        cal_uuid = "cal-001"
        fixed_now = "2026-01-15T12:00:00+00:00"
        added = import_ics_from_text(
            db_conn, cal_uuid, SINGLE_EVENT_ICS, now=fixed_now,
        )
        assert len(added) == 1

        row = db_conn.execute_one(
            "SELECT kreita_je FROM eventoj WHERE uuid = ?", (added[0],)
        )
        assert row["kreita_je"] == fixed_now


# ── import_ics_from_messages (mocked) ───────────────────────────────────────


class TestImportIcsFromMessages:
    """Tests for import_ics_from_messages() with mocked A-lien service."""

    @pytest.fixture
    def db_conn(self, tmp_path):
        """Create an in-memory SQLiteDB with eventoj schema."""
        from A.data.base import SQLiteDB

        db = SQLiteDB(str(tmp_path / "test.db"))
        db.execute(
            "CREATE TABLE IF NOT EXISTS eventoj ("
            "uuid TEXT PRIMARY KEY,"
            "kalendaro_uuid TEXT NOT NULL,"
            "titolo TEXT NOT NULL DEFAULT '',"
            "komenco TEXT NOT NULL,"
            "fino TEXT NOT NULL,"
            "kategorio TEXT NOT NULL DEFAULT '',"
            "loko TEXT NOT NULL DEFAULT '',"
            "ripeto TEXT NOT NULL DEFAULT '',"
            "partoprenantoj TEXT NOT NULL DEFAULT '[]',"
            "priskribo TEXT NOT NULL DEFAULT '',"
            "kreita_je TEXT NOT NULL,"
            "modifita_je TEXT NOT NULL"
            ")"
        )
        return db

    @pytest.fixture
    def mock_svc(self):
        """Create a Mock RetpostoService."""
        svc = Mock()
        svc.get_attachments.return_value = []
        svc.get_attachment_content.return_value = b""
        return svc

    def test_no_messages_no_import(self, db_conn, mock_svc):
        """Empty message list imports nothing."""
        from A_organizi.utils.retposto_ics import import_ics_from_messages

        result = import_ics_from_messages(db_conn, "cal-001", mock_svc, [])
        assert result == {}

    def test_imports_ics_from_message(self, db_conn):
        """Single message with .ics imports events."""
        from A_organizi.utils.retposto_ics import import_ics_from_messages

        mock_svc = Mock()
        mock_svc.get_attachments.return_value = [
            {"dosiernomo": "invite.ics", "mime_tipo": "text/calendar"},
        ]
        mock_svc.get_attachment_content.return_value = SAMPLE_ICS.encode("utf-8")

        result = import_ics_from_messages(db_conn, "cal-001", mock_svc, ["msg-1"])
        assert "msg-1" in result
        assert len(result["msg-1"]) == 2
        mock_svc.get_attachment_content.assert_called_once_with("msg-1", "invite.ics")

    def test_skips_non_ics_attachments(self, db_conn):
        """Non-.ics attachments are ignored."""
        from A_organizi.utils.retposto_ics import import_ics_from_messages

        mock_svc = Mock()
        mock_svc.get_attachments.return_value = [
            {"dosiernomo": "photo.jpg", "mime_tipo": "image/jpeg"},
        ]

        result = import_ics_from_messages(db_conn, "cal-001", mock_svc, ["msg-1"])
        assert result == {}
        mock_svc.get_attachment_content.assert_not_called()

    def test_imports_multiple_ics_from_one_message(self, db_conn):
        """One message with multiple .ics files imports all."""
        from A_organizi.utils.retposto_ics import import_ics_from_messages

        mock_svc = Mock()
        mock_svc.get_attachments.return_value = [
            {"dosiernomo": "part1.ics", "mime_tipo": "text/calendar"},
            {"dosiernomo": "part2.ics", "mime_tipo": "text/calendar"},
        ]
        def content_side_effect(msg_uuid, filename):
            if filename == "part1.ics":
                return SAMPLE_ICS.encode("utf-8")
            return SINGLE_EVENT_ICS.encode("utf-8")
        mock_svc.get_attachment_content.side_effect = content_side_effect

        result = import_ics_from_messages(db_conn, "cal-001", mock_svc, ["msg-1"])
        assert "msg-1" in result
        assert len(result["msg-1"]) == 3  # 2 + 1

    def test_imports_with_overrides(self, db_conn):
        """Overrides are applied to ICS imported from messages."""
        from A_organizi.utils.retposto_ics import import_ics_from_messages

        mock_svc = Mock()
        mock_svc.get_attachments.return_value = [
            {"dosiernomo": "invite.ics", "mime_tipo": "text/calendar"},
        ]
        mock_svc.get_attachment_content.return_value = SAMPLE_ICS.encode("utf-8")

        overrides = {"titolo": "Email Invite"}
        result = import_ics_from_messages(
            db_conn, "cal-001", mock_svc, ["msg-1"], overrides=overrides,
        )
        assert "msg-1" in result
        assert len(result["msg-1"]) == 2

        rows = db_conn.execute("SELECT titolo FROM eventoj")
        for row in rows:
            assert row["titolo"] == "Email Invite"

    def test_missing_message_skipped_gracefully(self, db_conn):
        """If a message has no .ics, it's skipped without error."""
        from A_organizi.utils.retposto_ics import import_ics_from_messages

        mock_svc = Mock()
        mock_svc.get_attachments.side_effect = [
            [{"dosiernomo": "readme.txt", "mime_tipo": "text/plain"}],
            [{"dosiernomo": "invite.ics", "mime_tipo": "text/calendar"}],
        ]
        mock_svc.get_attachment_content.return_value = SINGLE_EVENT_ICS.encode("utf-8")

        result = import_ics_from_messages(
            db_conn, "cal-001", mock_svc, ["msg-empty", "msg-ics"],
        )
        assert "msg-empty" not in result
        assert "msg-ics" in result
