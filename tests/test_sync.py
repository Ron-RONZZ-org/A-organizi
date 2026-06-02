"""Tests for sync and undo utilities."""

from __future__ import annotations

import json
import pytest
from unittest.mock import MagicMock, patch

# Mock keyring before importing sync module
mock_keyring = MagicMock()
mock_keyring.set_password = MagicMock()
mock_keyring.get_password = MagicMock(return_value="test_password")
mock_keyring.delete_password = MagicMock()

with patch.dict("sys.modules", {"keyring": mock_keyring}):
    from A_organizi.utils.sync import (
        remote_http_url,
        http_fetch_text,
        fetch_remote_calendar_payloads,
        set_password,
        get_password,
        delete_password,
    )
    from A_organizi.utils.undo import (
        push_undo,
        list_undos,
        apply_undo,
        record_delete_calendar,
        record_delete_event,
        record_import,
    )


class TestSyncUtils:
    """Tests for sync utilities."""

    def test_remote_http_url_caldav(self):
        """Convert caldav:// to https://."""
        assert remote_http_url("caldav://example.com/cal") == "https://example.com/cal"
        assert remote_http_url("caldavs://example.com/cal") == "https://example.com/cal"
        assert remote_http_url("https://example.com/cal") == "https://example.com/cal"

    def test_remote_http_url_http(self):
        """Keep http(s) URLs as-is."""
        assert remote_http_url("http://example.com/cal") == "http://example.com/cal"
        assert remote_http_url("https://example.com/cal") == "https://example.com/cal"

    @patch("urllib.request.urlopen")
    def test_http_fetch_text(self, mock_urlopen):
        """Test HTTP fetch with Basic auth."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b"response body"
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        status, body = http_fetch_text(
            "https://example.com/cal", "user", "pass"
        )

        assert status == 200
        assert body == "response body"

    @patch("urllib.request.urlopen")
    def test_http_fetch_text_error(self, mock_urlopen):
        """Test HTTP error handling."""
        from urllib.error import HTTPError

        mock_error = HTTPError(
            "https://example.com/cal",
            404,
            "Not Found",
            {},
            None,
        )
        mock_error.fp = MagicMock()
        mock_error.read.return_value = b'{"error": "not found"}'

        mock_urlopen.side_effect = mock_error

        status, body = http_fetch_text(
            "https://example.com/cal", "user", "pass"
        )

        assert status == 404

    @patch("urllib.request.urlopen")
    def test_fetch_remote_calendar_payloads(self, mock_urlopen):
        """Test CalDAV REPORT parsing."""
        mock_response = MagicMock()
        mock_response.status = 207
        mock_response.read.return_value = b'''<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:response>
    <d:href>/cal/events/1</d:href>
    <d:prop>
      <c:calendar-data>BEGIN:VCALENDAR
BEGIN:VEVENT
SUMMARY:Test Event
END:VEVENT
END:VCALENDAR</c:calendar-data>
    </d:prop>
  </d:response>
</d:multistatus>'''
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        payloads = fetch_remote_calendar_payloads(
            "https://example.com/cal", "user", "pass"
        )

        assert len(payloads) == 1
        assert "BEGIN:VCALENDAR" in payloads[0]


class TestPasswordManagement:
    """Tests for password management."""

    @patch("A_organizi.utils.sync.keyring", mock_keyring)
    def test_set_password(self):
        """Set password in keyring."""
        set_password("cal-uuid-123", "secret")
        mock_keyring.set_password.assert_called_once()

    @patch("A_organizi.utils.sync.keyring", mock_keyring)
    def test_get_password(self):
        """Get password from keyring."""
        password = get_password("cal-uuid-123")
        assert password == "test_password"

    @patch("A_organizi.utils.sync.keyring", mock_keyring)
    def test_delete_password(self):
        """Delete password from keyring."""
        delete_password("cal-uuid-123")
        mock_keyring.delete_password.assert_called_once()


class TestUndoUtils:
    """Tests for undo utilities."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database."""
        db = MagicMock()
        db.execute = MagicMock(return_value=[])
        db.execute_one = MagicMock(return_value=None)
        return db

    def test_push_undo(self, mock_db):
        """Record an undo operation."""
        change_id = push_undo(
            mock_db,
            "delete_event",
            {"event": {"uuid": "ev-123", "titolo": "Test"}},
        )

        assert change_id is not None
        call_args = mock_db.execute.call_args
        assert "INSERT INTO undo_changes" in call_args[0][0]

    def test_list_undos_empty(self, mock_db):
        """List undo operations (empty)."""
        mock_db.execute.return_value = []
        rows = list_undos(mock_db)

        assert rows == []

    def test_list_undos_with_data(self, mock_db):
        """List undo operations (with data)."""
        mock_db.execute.return_value = [
            {
                "id": "abc123",
                "operacio": "delete_event",
                "payload": '{"event": {"uuid": "ev-123"}}',
                "kreita_je": "2026-05-03T10:00:00",
            }
        ]

        rows = list_undos(mock_db)

        assert len(rows) == 1
        assert rows[0]["id"] == "abc123"
        assert rows[0]["payload"]["event"]["uuid"] == "ev-123"

    def test_apply_undo_not_found(self, mock_db):
        """Apply undo (not found)."""
        mock_db.execute_one.return_value = None
        result = apply_undo(mock_db, "abc123")

        assert result is False

    def test_apply_undo_delete_event(self, mock_db):
        """Apply undo for event deletion."""
        mock_db.execute_one.return_value = {
            "id": "abc123",
            "operacio": "delete_event",
            "payload": '{"event": {"uuid": "ev-123", "kalendaro_uuid": "cal-123", "komenco": "2026-05-03T10:00:00", "fino": "2026-05-03T11:00:00", "kreita_je": "2026-05-03T10:00:00", "modifita_je": "2026-05-03T10:00:00"}}',
        }

        result = apply_undo(mock_db, "abc123")

        assert result is True

    def test_record_delete_calendar(self, mock_db):
        """Record calendar deletion for undo."""
        mock_db.execute_one.return_value = {
            "uuid": "cal-123",
            "url": "https://example.com/cal",
            "username": "user",
            "remote": 1,
            "kreita_je": "2026-05-03T10:00:00",
            "modifita_je": "2026-05-03T10:00:00",
        }
        mock_db.execute.return_value = [
            {
                "uuid": "ev-123",
                "kalendaro_uuid": "cal-123",
                "titolo": "Test",
                "komenco": "2026-05-03T10:00:00",
                "fino": "2026-05-03T11:00:00",
                "kategorio": "",
                "loko": "",
                "ripeto": "",
                "partoprenantoj": "[]",
                "priskribo": "",
                "kreita_je": "2026-05-03T10:00:00",
                "modifita_je": "2026-05-03T10:00:00",
            }
        ]

        change_id = record_delete_calendar(mock_db, "cal-123")

        assert change_id is not None

    def test_record_delete_event(self, mock_db):
        """Record event deletion for undo."""
        mock_db.execute_one.return_value = {
            "uuid": "ev-123",
            "kalendaro_uuid": "cal-123",
            "titolo": "Test",
            "komenco": "2026-05-03T10:00:00",
            "fino": "2026-05-03T11:00:00",
            "kategorio": "",
            "loko": "",
            "ripeto": "",
            "partoprenantoj": "[]",
            "priskribo": "",
            "kreita_je": "2026-05-03T10:00:00",
            "modifita_je": "2026-05-03T10:00:00",
        }

        change_id = record_delete_event(mock_db, "ev-123")

        assert change_id is not None

    def test_record_import(self, mock_db):
        """Record import for undo."""
        change_id = record_import(mock_db, ["ev-123", "ev-456"])

        assert change_id is not None


class TestSyncIntegration:
    """Integration tests for sync."""

    def test_sync_queue_structure(self):
        """Verify sync table structure matches requirements."""
        from A_organizi.data.storage import _CREATE_SYNC_QUEUE

        assert "sync_queue" in _CREATE_SYNC_QUEUE
        assert "id" in _CREATE_SYNC_QUEUE
        assert "calendar_uuid" in _CREATE_SYNC_QUEUE
        assert "operacio" in _CREATE_SYNC_QUEUE
        assert "payload" in _CREATE_SYNC_QUEUE
        assert "stato" in _CREATE_SYNC_QUEUE

    def test_undo_changes_structure(self):
        """Verify undo table structure matches requirements."""
        from A_organizi.data.storage import _CREATE_UNDO_CHANGES

        assert "undo_changes" in _CREATE_UNDO_CHANGES
        assert "id" in _CREATE_UNDO_CHANGES
        assert "operacio" in _CREATE_UNDO_CHANGES
        assert "payload" in _CREATE_UNDO_CHANGES
        assert "kreita_je" in _CREATE_UNDO_CHANGES


class TestSyncPushRemote:
    """Tests for CalDAV push and delete helpers."""

    @patch("urllib.request.urlopen")
    def test_push_event_to_remote_success(self, mock_urlopen):
        """PUT creates event on remote (201)."""
        from A_organizi.utils.sync import push_event_to_remote

        mock_response = MagicMock()
        mock_response.status = 201
        mock_response.read.return_value = b""
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        status = push_event_to_remote(
            "https://example.com/cal/", "user", "pass",
            "BEGIN:VCALENDAR\nEND:VCALENDAR\n", "ev-123",
        )

        assert status == 201
        # Verify PUT was called with correct URL
        req = mock_urlopen.call_args[0][0]
        assert req.get_method() == "PUT"
        assert "/ev-123.ics" in req.full_url

    @patch("urllib.request.urlopen")
    def test_push_event_to_remote_failure(self, mock_urlopen):
        """PUT that returns unexpected status raises RuntimeError."""
        from A_organizi.utils.sync import push_event_to_remote
        from urllib.error import HTTPError

        mock_error = HTTPError(
            "https://example.com/cal/ev-123.ics",
            500, "Internal Server Error", {}, None,
        )
        mock_urlopen.side_effect = mock_error

        with pytest.raises(RuntimeError, match="CalDAV PUT failed"):
            push_event_to_remote(
                "https://example.com/cal/", "user", "pass",
                "BEGIN:VCALENDAR\nEND:VCALENDAR\n", "ev-123",
            )

    @patch("urllib.request.urlopen")
    def test_delete_event_from_remote_success(self, mock_urlopen):
        """DELETE removes event on remote (204)."""
        from A_organizi.utils.sync import delete_event_from_remote

        mock_response = MagicMock()
        mock_response.status = 204
        mock_response.read.return_value = b""
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        status = delete_event_from_remote(
            "https://example.com/cal/", "user", "pass", "ev-456",
        )

        assert status == 204
        req = mock_urlopen.call_args[0][0]
        assert req.get_method() == "DELETE"
        assert "/ev-456.ics" in req.full_url

    @patch("urllib.request.urlopen")
    def test_delete_event_from_remote_already_gone(self, mock_urlopen):
        """DELETE returning 404 is accepted as 'already gone'."""
        from A_organizi.utils.sync import delete_event_from_remote
        from urllib.error import HTTPError

        mock_error = HTTPError(
            "https://example.com/cal/ev-456.ics",
            404, "Not Found", {}, None,
        )
        mock_urlopen.side_effect = mock_error

        status = delete_event_from_remote(
            "https://example.com/cal/", "user", "pass", "ev-456",
        )
        assert status == 404

    @patch("urllib.request.urlopen")
    def test_delete_event_from_remote_failure(self, mock_urlopen):
        """DELETE that returns unexpected status raises RuntimeError."""
        from A_organizi.utils.sync import delete_event_from_remote
        from urllib.error import HTTPError

        mock_error = HTTPError(
            "https://example.com/cal/ev-456.ics",
            500, "Internal Server Error", {}, None,
        )
        mock_urlopen.side_effect = mock_error

        with pytest.raises(RuntimeError, match="CalDAV DELETE failed"):
            delete_event_from_remote(
                "https://example.com/cal/", "user", "pass", "ev-456",
            )


class TestEventServiceSyncHooks:
    """Tests that EventService _post_* hooks enqueue sync jobs."""

    @pytest.fixture
    def db_with_remote_calendar(self, tmp_path):
        """Set up a real SQLite DB with a remote calendar and return services."""
        import A_organizi.data.storage as storage_module
        import A_organizi.service.kalendaro as kalendaro_module
        import uuid as uuid_mod

        storage_module._db_instance = None
        from A_organizi.data.storage import get_db

        db = get_db()
        now = "2026-06-02T12:00:00"

        # Insert a remote calendar
        cal_uuid = str(uuid_mod.uuid4())
        db.execute(
            "INSERT INTO kalendaroj (uuid, url, username, remote, kreita_je, modifita_je)"
            " VALUES (?, ?, ?, 1, ?, ?)",
            (cal_uuid, "https://example.com/cal", "user", now, now),
        )

        return db, cal_uuid, now

    @pytest.fixture
    def db_with_local_calendar(self, tmp_path):
        """Set up a real SQLite DB with a local-only calendar."""
        import A_organizi.data.storage as storage_module
        import uuid as uuid_mod

        storage_module._db_instance = None
        from A_organizi.data.storage import get_db

        db = get_db()
        now = "2026-06-02T12:00:00"

        # Insert a local calendar (remote=0)
        cal_uuid = str(uuid_mod.uuid4())
        db.execute(
            "INSERT INTO kalendaroj (uuid, url, username, remote, kreita_je, modifita_je)"
            " VALUES (?, ?, ?, 0, ?, ?)",
            (cal_uuid, "", "", now, now),
        )

        return db, cal_uuid, now

    def _count_sync_queue(self, db):
        """Return number of pending sync jobs."""
        row = db.execute_one("SELECT COUNT(*) AS cnt FROM sync_queue")
        return row["cnt"] if row else 0

    def test_post_create_remote_calendar_enqueues(self, db_with_remote_calendar):
        """Creating an event in a remote calendar enqueues a push job."""
        db, cal_uuid, now = db_with_remote_calendar
        from A_organizi.service.kalendaro import get_evento_service

        svc = get_evento_service()
        svc.create({
            "kalendaro_uuid": cal_uuid,
            "titolo": "Sync Test",
            "komenco": "2026-06-02T10:00:00",
            "fino": "2026-06-02T11:00:00",
        })

        assert self._count_sync_queue(db) == 1
        job = db.execute_one("SELECT * FROM sync_queue")
        assert job is not None
        assert job["operacio"] == "push"
        payload = json.loads(job["payload"])
        assert payload["operation"] == "create"
        assert "event_uuid" in payload

    def test_post_create_local_calendar_skips(self, db_with_local_calendar):
        """Creating an event in a local calendar does NOT enqueue a push job."""
        db, cal_uuid, now = db_with_local_calendar
        from A_organizi.service.kalendaro import get_evento_service

        svc = get_evento_service()
        svc.create({
            "kalendaro_uuid": cal_uuid,
            "titolo": "Local Only",
            "komenco": "2026-06-02T10:00:00",
            "fino": "2026-06-02T11:00:00",
        })

        assert self._count_sync_queue(db) == 0

    def test_post_update_enqueues(self, db_with_remote_calendar):
        """Updating an event in a remote calendar enqueues a push job."""
        db, cal_uuid, now = db_with_remote_calendar
        from A_organizi.service.kalendaro import get_evento_service

        svc = get_evento_service()
        event = svc.create({
            "kalendaro_uuid": cal_uuid,
            "titolo": "To Update",
            "komenco": "2026-06-02T10:00:00",
            "fino": "2026-06-02T11:00:00",
        })
        # Clear queue from create
        db.execute("DELETE FROM sync_queue")
        assert self._count_sync_queue(db) == 0

        svc.update(event["uuid"], {"titolo": "Updated Title"})

        assert self._count_sync_queue(db) == 1
        job = db.execute_one("SELECT * FROM sync_queue")
        payload = json.loads(job["payload"])
        assert payload["operation"] == "update"

    def test_post_delete_enqueues(self, db_with_remote_calendar):
        """Deleting an event from a remote calendar enqueues a push job."""
        db, cal_uuid, now = db_with_remote_calendar
        from A_organizi.service.kalendaro import get_evento_service

        svc = get_evento_service()
        event = svc.create({
            "kalendaro_uuid": cal_uuid,
            "titolo": "To Delete",
            "komenco": "2026-06-02T10:00:00",
            "fino": "2026-06-02T11:00:00",
        })
        # Clear queue from create
        db.execute("DELETE FROM sync_queue")

        svc.delete(event["uuid"], soft=False)

        assert self._count_sync_queue(db) == 1
        job = db.execute_one("SELECT * FROM sync_queue")
        payload = json.loads(job["payload"])
        assert payload["operation"] == "delete"
        assert payload["event_uuid"] == event["uuid"]

    def test_delete_by_date_range_triggers_hooks(self, db_with_remote_calendar):
        """delete_by_date_range calls self.delete() per event, triggering _post_delete."""
        db, cal_uuid, now = db_with_remote_calendar
        from A_organizi.service.kalendaro import get_evento_service

        svc = get_evento_service()

        # Create two events in range
        svc.create({
            "kalendaro_uuid": cal_uuid,
            "titolo": "Event A",
            "komenco": "2026-06-02T10:00:00",
            "fino": "2026-06-02T11:00:00",
        })
        svc.create({
            "kalendaro_uuid": cal_uuid,
            "titolo": "Event B",
            "komenco": "2026-06-02T14:00:00",
            "fino": "2026-06-02T15:00:00",
        })
        # Clear queue from creates
        db.execute("DELETE FROM sync_queue")

        from datetime import date
        deleted = svc.delete_by_date_range(date(2026, 6, 2), date(2026, 6, 2))

        assert deleted == 2
        # Each delete triggers _post_delete → one sync_queue job per event
        assert self._count_sync_queue(db) == 2


class TestSyncQueueIndex:
    """Tests that the sync_queue index is created."""

    def test_sync_queue_index_exists(self):
        """Verify the sync_queue index is in the schema."""
        from A_organizi.data.storage import _CREATE_INDEXES

        has_index = any("idx_sync_queue_calendar_stato" in idx for idx in _CREATE_INDEXES)
        assert has_index, "Missing sync_queue index in _CREATE_INDEXES"

    def test_sync_queue_index_created_in_db(self, tmp_path):
        """Verify the index is actually created in the database."""
        import A_organizi.data.storage as storage_module
        storage_module._db_instance = None
        from A_organizi.data.storage import get_db

        db = get_db()
        rows = db.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_sync_queue_calendar_stato'")
        assert len(rows) == 1, "Index idx_sync_queue_calendar_stato not found in DB"
        assert rows[0]["name"] == "idx_sync_queue_calendar_stato"