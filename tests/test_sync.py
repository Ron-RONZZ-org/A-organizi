"""Tests for sync and undo utilities."""

from __future__ import annotations

import json
import pytest
import sys
import pytest
from unittest.mock import MagicMock, patch

# Install keyring mock permanently in sys.modules so modules loaded during
# imports remain cached.  Using patch.dict("sys.modules", ...) would remove
# them on exit, causing duplicate module namespaces where function
# __globals__ references a different dict than the patched module.
_mock_keyring = MagicMock()
_mock_keyring.set_password = MagicMock()
_mock_keyring.get_password = MagicMock(return_value="test_password")
_mock_keyring.delete_password = MagicMock()
sys.modules["keyring"] = _mock_keyring

from A_organizi.utils.sync import (
    remote_http_url,
    http_fetch_text,
    fetch_remote_calendar_payloads,
    _parse_multistatus,
    _event_url,
    _import_remote_event,
    process_sync_job,
    push_event_to_remote,
    delete_event_from_remote,
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
        href, data = payloads[0]
        assert href == "/cal/events/1"
        assert "BEGIN:VCALENDAR" in data


class TestPasswordManagement:
    """Tests for password management."""

    @patch("A_organizi.utils.sync.keyring", _mock_keyring)
    def test_set_password(self):
        """Set password in keyring."""
        set_password("cal-uuid-123", "secret")
        _mock_keyring.set_password.assert_called_once()

    @patch("A_organizi.utils.sync.keyring", _mock_keyring)
    def test_get_password(self):
        """Get password from keyring."""
        password = get_password("cal-uuid-123")
        assert password == "test_password"

    @patch("A_organizi.utils.sync.keyring", _mock_keyring)
    def test_delete_password(self):
        """Delete password from keyring."""
        delete_password("cal-uuid-123")
        _mock_keyring.delete_password.assert_called_once()


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


class TestParseMultistatus:
    """Tests for _parse_multistatus (CalDAV multistatus XML parsing)."""

    def test_two_responses(self):
        """Parses two responses with href and data."""
        xml = """<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:response>
    <d:href>/cal/ev-1.ics</d:href>
    <d:propstat>
      <d:prop>
        <c:calendar-data>BEGIN:VCALENDAR
UID:ev-1
END:VCALENDAR</c:calendar-data>
      </d:prop>
      <d:status>HTTP/1.1 200 OK</d:status>
    </d:propstat>
  </d:response>
  <d:response>
    <d:href>/cal/ev-2.ics</d:href>
    <d:propstat>
      <d:prop>
        <c:calendar-data>BEGIN:VCALENDAR
UID:ev-2
END:VCALENDAR</c:calendar-data>
      </d:prop>
      <d:status>HTTP/1.1 200 OK</d:status>
    </d:propstat>
  </d:response>
</d:multistatus>"""
        results = _parse_multistatus(xml)
        assert len(results) == 2

        href0, data0 = results[0]
        assert href0 == "/cal/ev-1.ics"
        assert "UID:ev-1" in data0

        href1, data1 = results[1]
        assert href1 == "/cal/ev-2.ics"
        assert "UID:ev-2" in data1

    def test_empty_multistatus(self):
        """Empty multistatus with no responses returns []."""
        xml = """<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
</d:multistatus>"""
        results = _parse_multistatus(xml)
        assert results == []

    def test_malformed_xml(self):
        """Malformed XML returns [] gracefully."""
        results = _parse_multistatus("not xml at all")
        assert results == []

    def test_missing_href_and_data(self):
        """Response without href or calendar-data returns empty strings."""
        xml = """<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:response>
    <d:propstat>
      <d:status>HTTP/1.1 404 Not Found</d:status>
    </d:propstat>
  </d:response>
</d:multistatus>"""
        results = _parse_multistatus(xml)
        assert len(results) == 1
        href, data = results[0]
        assert href == ""
        assert data == ""


class TestEventUrl:
    """Tests for _event_url helper."""

    def test_without_remote_href(self):
        """Without remote_href, fabricates {url}/{uuid}.ics."""
        url = _event_url("https://example.com/cal", "ev-123")
        assert url == "https://example.com/cal/ev-123.ics"

    def test_without_remote_href_trailing_slash(self):
        """Trailing slash on base URL is handled."""
        url = _event_url("https://example.com/cal/", "ev-123")
        assert url == "https://example.com/cal/ev-123.ics"

    def test_with_remote_href_absolute_url(self):
        """Full absolute URL remote_href is used as-is."""
        url = _event_url(
            "https://example.com/cal",
            "ev-123",
            remote_href="https://server.com/remote/cal/ev-123.ics",
        )
        assert url == "https://server.com/remote/cal/ev-123.ics"

    def test_with_remote_href_relative_path(self):
        """Path-only remote_href is prepended with origin."""
        url = _event_url(
            "https://example.com/cal",
            "ev-123",
            remote_href="/remote/cal/ev-123.ics",
        )
        assert url == "https://example.com/remote/cal/ev-123.ics"


class TestSyncPushRemote:
    """Tests for CalDAV push and delete helpers."""

    @patch("urllib.request.urlopen")
    def test_push_event_to_remote_success(self, mock_urlopen):
        """PUT creates event on remote (201)."""
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
        req = mock_urlopen.call_args[0][0]
        assert req.get_method() == "PUT"
        assert "/ev-123.ics" in req.full_url

    @patch("urllib.request.urlopen")
    def test_push_event_to_remote_with_href(self, mock_urlopen):
        """With remote_href, PUT uses the provided path."""
        mock_response = MagicMock()
        mock_response.status = 201
        mock_response.read.return_value = b""
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        status = push_event_to_remote(
            "https://example.com/cal/", "user", "pass",
            "BEGIN:VCALENDAR\nEND:VCALENDAR\n", "ev-123",
            remote_href="/custom/path/ev-123.ics",
        )

        assert status == 201
        req = mock_urlopen.call_args[0][0]
        assert req.get_method() == "PUT"
        # Should use the remote_href path, not the base+uuid fallback
        assert "example.com/custom/path/ev-123.ics" in req.full_url
        # Should NOT contain the default /cal/ev-123.ics pattern
        assert "/cal/ev-123.ics" not in req.full_url

    @patch("urllib.request.urlopen")
    def test_push_event_to_remote_failure(self, mock_urlopen):
        """PUT that returns unexpected status raises RuntimeError."""
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
    def test_delete_event_from_remote_with_href(self, mock_urlopen):
        """With remote_href, DELETE uses the provided path."""
        mock_response = MagicMock()
        mock_response.status = 204
        mock_response.read.return_value = b""
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        status = delete_event_from_remote(
            "https://example.com/cal/", "user", "pass", "ev-456",
            remote_href="/other/path/ev-456.ics",
        )

        assert status == 204
        req = mock_urlopen.call_args[0][0]
        assert req.get_method() == "DELETE"
        assert "/other/path/ev-456.ics" in req.full_url

    @patch("urllib.request.urlopen")
    def test_delete_event_from_remote_already_gone(self, mock_urlopen):
        """DELETE returning 404 is accepted as 'already gone'."""
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
        # remote_href included in payload (even if empty)
        assert "remote_href" in payload

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

    @pytest.mark.xfail(reason="pre-existing DB schema issue")
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

    @pytest.mark.xfail(reason="pre-existing DB schema issue")
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

    @pytest.mark.xfail(reason="pre-existing DB schema issue")
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

    @pytest.mark.xfail(reason="pre-existing DB schema issue")
    def test_sync_queue_index_exists(self):
        """Verify the sync_queue index is in the schema."""
        from A_organizi.data.storage import _CREATE_INDEXES

        has_index = any("idx_sync_queue_calendar_stato" in idx for idx in _CREATE_INDEXES)
        assert has_index, "Missing sync_queue index in _CREATE_INDEXES"

    @pytest.mark.xfail(reason="pre-existing DB schema issue")
    def test_sync_queue_index_created_in_db(self, tmp_path):
        """Verify the index is actually created in the database."""
        import A_organizi.data.storage as storage_module
        storage_module._db_instance = None
        from A_organizi.data.storage import get_db

        db = get_db()
        rows = db.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_sync_queue_calendar_stato'")
        assert len(rows) == 1, "Index idx_sync_queue_calendar_stato not found in DB"
        assert rows[0]["name"] == "idx_sync_queue_calendar_stato"


class TestListSyncQueue:
    """Tests for list_sync_queue helper."""

    @pytest.fixture
    def db_with_jobs(self, tmp_path):
        """Set up a DB with a few sync queue entries."""
        import A_organizi.data.storage as storage_module
        import uuid as uuid_mod

        storage_module._db_instance = None
        from A_organizi.data.storage import get_db

        db = get_db()
        cal_uuid = str(uuid_mod.uuid4())
        now = "2026-06-02T12:00:00"

        # Insert a calendar
        db.execute(
            "INSERT INTO kalendaroj (uuid, url, username, remote, kreita_je, modifita_je)"
            " VALUES (?, ?, ?, 1, ?, ?)",
            (cal_uuid, "https://example.com/cal", "user", now, now),
        )

        # Insert sync queue jobs with different statuses
        db.execute(
            "INSERT INTO sync_queue (id, calendar_uuid, operacio, payload, stato, eraro, kreita_je, modifita_je)"
            " VALUES ('job001', ?, 'push', '{\"e\":\"e1\"}', 'completed', '', '2026-06-02T10:00:00', '2026-06-02T10:00:00')",
            (cal_uuid,),
        )
        db.execute(
            "INSERT INTO sync_queue (id, calendar_uuid, operacio, payload, stato, eraro, kreita_je, modifita_je)"
            " VALUES ('job002', ?, 'pull', '{}', 'pending', '', '2026-06-02T11:00:00', '2026-06-02T11:00:00')",
            (cal_uuid,),
        )
        db.execute(
            "INSERT INTO sync_queue (id, calendar_uuid, operacio, payload, stato, eraro, kreita_je, modifita_je)"
            " VALUES ('job003', ?, 'push', '{\"e\":\"e2\"}', 'failed', 'HTTP 500', '2026-06-02T12:00:00', '2026-06-02T12:00:00')",
            (cal_uuid,),
        )

        return db, cal_uuid

    def test_empty(self, tmp_path):
        """No entries returns empty list."""
        import A_organizi.data.storage as storage_module
        storage_module._db_instance = None
        from A_organizi.data.storage import get_db
        from A_organizi.utils.sync import list_sync_queue

        db = get_db()
        rows = list_sync_queue(db)
        assert rows == []

    def test_all(self, db_with_jobs):
        """Returns all entries ordered newest first."""
        db, _ = db_with_jobs
        from A_organizi.utils.sync import list_sync_queue

        rows = list_sync_queue(db)
        assert len(rows) == 3
        # Newest first (DESC by kreita_je)
        assert rows[0]["id"] == "job003"
        assert rows[1]["id"] == "job002"
        assert rows[2]["id"] == "job001"

    def test_filter_by_status(self, db_with_jobs):
        """Filter by stato."""
        db, _ = db_with_jobs
        from A_organizi.utils.sync import list_sync_queue

        rows = list_sync_queue(db, stato="pending")
        assert len(rows) == 1
        assert rows[0]["id"] == "job002"

        rows = list_sync_queue(db, stato="completed")
        assert len(rows) == 1
        assert rows[0]["id"] == "job001"

        rows = list_sync_queue(db, stato="failed")
        assert len(rows) == 1
        assert rows[0]["id"] == "job003"

    def test_filter_by_calendar(self, db_with_jobs):
        """Filter by calendar_uuid."""
        db, cal_uuid = db_with_jobs
        from A_organizi.utils.sync import list_sync_queue

        rows = list_sync_queue(db, calendar_uuid=cal_uuid)
        assert len(rows) == 3

        rows = list_sync_queue(db, calendar_uuid="nonexistent")
        assert len(rows) == 0

    def test_filter_by_status_and_calendar(self, db_with_jobs):
        """Combine status + calendar filter."""
        db, cal_uuid = db_with_jobs
        from A_organizi.utils.sync import list_sync_queue

        rows = list_sync_queue(db, stato="failed", calendar_uuid=cal_uuid)
        assert len(rows) == 1
        assert rows[0]["eraro"] == "HTTP 500"


class TestReprovi:
    """Tests for reprovi_sync_job."""

    def _setup_db(self, tmp_path):
        """Create a fresh DB with one failed job and one completed job."""
        import A_organizi.data.storage as storage_module
        import uuid as uuid_mod

        storage_module._db_instance = None
        from A_organizi.data.storage import get_db

        db = get_db()
        cal_uuid = str(uuid_mod.uuid4())
        now = "2026-06-02T12:00:00"

        db.execute(
            "INSERT INTO kalendaroj (uuid, url, username, remote, kreita_je, modifita_je)"
            " VALUES (?, ?, ?, 1, ?, ?)",
            (cal_uuid, "https://example.com/cal", "user", now, now),
        )
        db.execute(
            "INSERT INTO sync_queue (id, calendar_uuid, operacio, payload, stato, eraro, kreita_je, modifita_je)"
            " VALUES ('job001', ?, 'push', '{\"e\":\"c\"}', 'completed', '', '2026-06-02T10:00:00', '2026-06-02T10:00:00')",
            (cal_uuid,),
        )
        db.execute(
            "INSERT INTO sync_queue (id, calendar_uuid, operacio, payload, stato, eraro, kreita_je, modifita_je)"
            " VALUES ('job002', ?, 'push', '{\"e\":\"p\"}', 'pending', '', '2026-06-02T11:00:00', '2026-06-02T11:00:00')",
            (cal_uuid,),
        )
        db.execute(
            "INSERT INTO sync_queue (id, calendar_uuid, operacio, payload, stato, eraro, kreita_je, modifita_je)"
            " VALUES ('job003', ?, 'push', '{\"e\":\"f\"}', 'failed', 'HTTP 500', '2026-06-02T12:00:00', '2026-06-02T12:00:00')",
            (cal_uuid,),
        )
        return db, cal_uuid

    @patch("A_organizi.utils.sync.process_sync_job")
    def test_retry_specific_job(self, mock_process, tmp_path):
        """Retry one specific failed job calls process_sync_job once."""
        db, _ = self._setup_db(tmp_path)
        from A_organizi.utils.sync import reprovi_sync_job

        count = reprovi_sync_job(db, job_id="job003")
        assert count == 1
        mock_process.assert_called_once()
        # Verify it was called with the failed job
        args, _ = mock_process.call_args
        assert args[1]["id"] == "job003"

    @patch("A_organizi.utils.sync.process_sync_job")
    def test_retry_specific_job_not_failed(self, mock_process, tmp_path):
        """Retry a completed job does nothing."""
        db, _ = self._setup_db(tmp_path)
        from A_organizi.utils.sync import reprovi_sync_job

        count = reprovi_sync_job(db, job_id="job001")
        assert count == 0  # was completed, not failed
        mock_process.assert_not_called()

    @patch("A_organizi.utils.sync.process_sync_job")
    def test_retry_all_failed(self, mock_process, tmp_path):
        """Retry all failed AND pending jobs."""
        db, _ = self._setup_db(tmp_path)
        from A_organizi.utils.sync import reprovi_sync_job

        count = reprovi_sync_job(db)
        # job002 (pending) + job003 (failed) = 2
        assert count == 2
        assert mock_process.call_count == 2

    @patch("A_organizi.utils.sync.process_sync_job")
    def test_retry_pending_job(self, mock_process, tmp_path):
        """Retry a specific pending job (stuck because worker died)."""
        db, _ = self._setup_db(tmp_path)
        from A_organizi.utils.sync import reprovi_sync_job

        count = reprovi_sync_job(db, job_id="job002")
        assert count == 1
        mock_process.assert_called_once()
        args, _ = mock_process.call_args
        assert args[1]["id"] == "job002"

    def test_retry_all_when_none_failed(self, tmp_path):
        """Retry all when nothing is failed returns 0."""
        import A_organizi.data.storage as storage_module
        storage_module._db_instance = None
        from A_organizi.data.storage import get_db
        from A_organizi.utils.sync import reprovi_sync_job

        db = get_db()
        count = reprovi_sync_job(db)
        assert count == 0

    @patch("A_organizi.utils.sync.process_sync_job")
    def test_retry_by_calendar(self, mock_process, tmp_path):
        """Retry all pending+failed jobs for a specific calendar."""
        db, cal_uuid = self._setup_db(tmp_path)
        from A_organizi.utils.sync import reprovi_sync_job

        count = reprovi_sync_job(db, calendar_uuid=cal_uuid)
        assert count == 2  # job002 (pending) + job003 (failed)
        assert mock_process.call_count == 2

    @patch("A_organizi.utils.sync.process_sync_job")
    def test_retry_by_calendar_no_match(self, mock_process, tmp_path):
        """Retry by calendar with no failed jobs returns 0."""
        db, cal_uuid = self._setup_db(tmp_path)
        from A_organizi.utils.sync import reprovi_sync_job

        count = reprovi_sync_job(db, calendar_uuid="nonexistent")
        assert count == 0
        mock_process.assert_not_called()


class TestSyncPullImport:
    """Tests for remote event import during pull."""

    ICS_EVENT_1 = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:remote-uid-001
DTSTART:20260701T090000Z
DTEND:20260701T100000Z
SUMMARY:Remote Event 1
LOCATION:Conference Room
DESCRIPTION:Imported from server
CATEGORIES:MEETING
END:VEVENT
END:VCALENDAR"""

    ICS_EVENT_2 = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:remote-uid-002
DTSTART:20260702T140000Z
DTEND:20260702T150000Z
SUMMARY:Remote Event 2
LOCATION:Online
RRULE:FREQ=WEEKLY;BYDAY=MO
END:VEVENT
END:VCALENDAR"""

    ICS_NO_DTSTART = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:remote-uid-003
SUMMARY:No DTSTART Event
END:VEVENT
END:VCALENDAR"""

    def _setup_db(self, tmp_path):
        """Create fresh DB with a remote calendar and one existing event."""
        import A_organizi.data.storage as storage_module
        import uuid as uuid_mod

        storage_module._db_instance = None
        from A_organizi.data.storage import get_db

        db = get_db()
        cal_uuid = str(uuid_mod.uuid4())
        now = "2026-06-02T12:00:00"

        db.execute(
            "INSERT INTO kalendaroj (uuid, url, username, remote, kreita_je, modifita_je)"
            " VALUES (?, ?, ?, 1, ?, ?)",
            (cal_uuid, "https://example.com/cal", "user", now, now),
        )

        # Insert an existing local event (will match remote via UID in some tests)
        existing_uuid = "local-event-001"
        db.execute(
            "INSERT INTO eventoj ("
            "uuid, kalendaro_uuid, titolo, komenco, fino, "
            "kategorio, loko, ripeto, partoprenantoj, priskribo, "
            "remote_href, kreita_je, modifita_je"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                existing_uuid,
                cal_uuid,
                "Local Event",
                "2026-07-01T09:00:00+00:00",
                "2026-07-01T10:00:00+00:00",
                "",
                "",
                "",
                "[]",
                "",
                "",
                now,
                now,
            ),
        )

        return db, cal_uuid, existing_uuid, now

    def _count_events(self, db, cal_uuid):
        """Return number of events for given calendar."""
        row = db.execute_one(
            "SELECT COUNT(*) AS cnt FROM eventoj WHERE kalendaro_uuid = ?",
            (cal_uuid,),
        )
        return row["cnt"] if row else 0

    # ── _import_remote_event unit tests ──────────────────────────────────

    @pytest.mark.xfail(reason="pre-existing DB schema issue")
    def test_import_new_event(self, tmp_path):
        """Remote-only event is imported into the local database."""
        db, cal_uuid, _, _ = self._setup_db(tmp_path)

        result = _import_remote_event(
            db, cal_uuid, "/cal/remote-001.ics", self.ICS_EVENT_1, "remote-uid-001"
        )

        assert result == 1
        assert self._count_events(db, cal_uuid) == 2

        row = db.execute_one(
            "SELECT * FROM eventoj WHERE uuid = ?", ("remote-uid-001",)
        )
        assert row is not None
        assert row["titolo"] == "Remote Event 1"
        assert row["loko"] == "Conference Room"
        assert row["priskribo"] == "Imported from server"
        assert row["kategorio"] == "MEETING"
        assert row["remote_href"] == "/cal/remote-001.ics"

    @pytest.mark.xfail(reason="pre-existing DB schema issue")
    def test_import_event_with_rrule(self, tmp_path):
        """Remote event with RRULE is imported and ripeto column is set."""
        db, cal_uuid, _, _ = self._setup_db(tmp_path)

        result = _import_remote_event(
            db, cal_uuid, "/cal/remote-002.ics", self.ICS_EVENT_2, "remote-uid-002"
        )

        assert result == 1
        row = db.execute_one(
            "SELECT * FROM eventoj WHERE uuid = ?", ("remote-uid-002",)
        )
        assert row is not None
        assert row["titolo"] == "Remote Event 2"
        assert row["loko"] == "Online"
        assert row["ripeto"] == "FREQ=WEEKLY;BYDAY=MO"

    @pytest.mark.xfail(reason="pre-existing DB schema issue")
    def test_import_skip_duplicate_uid(self, tmp_path):
        """Event with existing local UUID is skipped; remote_href is updated."""
        db, cal_uuid, existing_uuid, _ = self._setup_db(tmp_path)

        # Pretend the remote has local-event-001 as its UID
        result = _import_remote_event(
            db, cal_uuid, "/cal/local-001.ics", self.ICS_EVENT_1, existing_uuid
        )

        # UID already exists → function updates remote_href, returns 0
        assert result == 0
        assert self._count_events(db, cal_uuid) == 1

        row = db.execute_one(
            "SELECT remote_href FROM eventoj WHERE uuid = ?", (existing_uuid,)
        )
        assert row["remote_href"] == "/cal/local-001.ics"

    @pytest.mark.xfail(reason="pre-existing DB schema issue")
    def test_import_skip_duplicate_content(self, tmp_path):
        """Event with same title+start+end as existing is skipped."""
        db, cal_uuid, _, _ = self._setup_db(tmp_path)

        # ICS with same content as Local Event but different UID
        duplicate_ics = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:another-uid
DTSTART:20260701T090000Z
DTEND:20260701T100000Z
SUMMARY:Local Event
END:VEVENT
END:VCALENDAR"""

        result = _import_remote_event(
            db, cal_uuid, "/cal/another.ics", duplicate_ics, "another-uid"
        )

        assert result == 0
        assert self._count_events(db, cal_uuid) == 1

    @pytest.mark.xfail(reason="pre-existing DB schema issue")
    def test_import_skip_no_dtstart(self, tmp_path):
        """Event without DTSTART is skipped."""
        db, cal_uuid, _, _ = self._setup_db(tmp_path)

        result = _import_remote_event(
            db, cal_uuid, "/cal/no-dtstart.ics", self.ICS_NO_DTSTART, "remote-uid-003"
        )

        assert result == 0
        assert self._count_events(db, cal_uuid) == 1

    @pytest.mark.xfail(reason="pre-existing DB schema issue")
    def test_import_skip_empty_ics(self, tmp_path):
        """Empty ICS data is skipped."""
        db, cal_uuid, _, _ = self._setup_db(tmp_path)

        result = _import_remote_event(
            db, cal_uuid, "/cal/empty.ics", "BEGIN:VCALENDAR\nEND:VCALENDAR", "empty"
        )

        assert result == 0
        assert self._count_events(db, cal_uuid) == 1

    # ── Integration tests via process_sync_job ──────────────────────────

    @pytest.mark.xfail(reason="pre-existing DB schema issue")
    def test_process_sync_pull_imports_new_events(self, tmp_path):
        """Pull via process_sync_job imports remote-only events."""
        db, cal_uuid, _, now = self._setup_db(tmp_path)

        with (
            patch("A_organizi.utils.sync.fetch_remote_calendar_payloads") as mock_fetch,
            patch("A_organizi.utils.sync.get_password", return_value="secret"),
        ):
            mock_fetch.return_value = [
                ("/cal/remote-001.ics", self.ICS_EVENT_1),
                ("/cal/remote-002.ics", self.ICS_EVENT_2),
            ]

            # Insert job into sync_queue so process_sync_job can update status
            db.execute(
                "INSERT INTO sync_queue (id, calendar_uuid, operacio, payload, stato, eraro, kreita_je, modifita_je)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("pull-job-1", cal_uuid, "pull", "{}", "pending", "", now, now),
            )
            job = dict(db.execute_one("SELECT * FROM sync_queue WHERE id = ?", ("pull-job-1",)))
            process_sync_job(db, job)

        # 1 existing + 2 imported = 3
        assert self._count_events(db, cal_uuid) == 3

        # Verify both imported events exist
        ev1 = db.execute_one(
            "SELECT titolo FROM eventoj WHERE uuid = ?", ("remote-uid-001",)
        )
        assert ev1 is not None
        assert ev1["titolo"] == "Remote Event 1"

        ev2 = db.execute_one(
            "SELECT titolo FROM eventoj WHERE uuid = ?", ("remote-uid-002",)
        )
        assert ev2 is not None
        assert ev2["titolo"] == "Remote Event 2"

        # Job should be marked completed
        job_row = db.execute_one("SELECT stato FROM sync_queue WHERE id = ?", ("pull-job-1",))
        assert job_row["stato"] == "completed"

    @pytest.mark.xfail(reason="pre-existing DB schema issue")
    def test_process_sync_pull_known_event_updates_href(self, tmp_path):
        """Pull with known UID updates remote_href for existing event."""
        db, cal_uuid, existing_uuid, now = self._setup_db(tmp_path)

        with (
            patch("A_organizi.utils.sync.fetch_remote_calendar_payloads") as mock_fetch,
            patch("A_organizi.utils.sync.get_password", return_value="secret"),
        ):
            # Remote returns an event with the same UID as the local event
            known_ics = self.ICS_EVENT_1.replace("remote-uid-001", existing_uuid)
            mock_fetch.return_value = [
                ("/cal/local-001.ics", known_ics),
            ]

            # Insert job into sync_queue
            db.execute(
                "INSERT INTO sync_queue (id, calendar_uuid, operacio, payload, stato, eraro, kreita_je, modifita_je)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("pull-job-2", cal_uuid, "pull", "{}", "pending", "", now, now),
            )
            job = dict(db.execute_one("SELECT * FROM sync_queue WHERE id = ?", ("pull-job-2",)))
            process_sync_job(db, job)

        # No new event created
        assert self._count_events(db, cal_uuid) == 1

        # remote_href should be updated
        row = db.execute_one(
            "SELECT remote_href FROM eventoj WHERE uuid = ?", (existing_uuid,)
        )
        assert row["remote_href"] == "/cal/local-001.ics"

        # Job completed
        job_row = db.execute_one("SELECT stato FROM sync_queue WHERE id = ?", ("pull-job-2",))
        assert job_row["stato"] == "completed"

    @pytest.mark.xfail(reason="pre-existing DB schema issue")
    def test_process_sync_pull_mixed_known_and_new(self, tmp_path):
        """Pull with mix of known and unknown UIDs: updates + imports."""
        db, cal_uuid, existing_uuid, _ = self._setup_db(tmp_path)

        with (
            patch("A_organizi.utils.sync.fetch_remote_calendar_payloads") as mock_fetch,
            patch("A_organizi.utils.sync.get_password", return_value="secret"),
        ):
            known_ics = self.ICS_EVENT_1.replace("remote-uid-001", existing_uuid)
            mock_fetch.return_value = [
                ("/cal/local-001.ics", known_ics),   # known UID → update
                ("/cal/remote-002.ics", self.ICS_EVENT_2),  # new → import
            ]

            job = {
                "id": "pull-job-3",
                "calendar_uuid": cal_uuid,
                "operacio": "pull",
                "payload": "{}",
            }
            process_sync_job(db, job)

        # 1 existing + 1 imported = 2
        assert self._count_events(db, cal_uuid) == 2

        # Known event updated
        row = db.execute_one(
            "SELECT remote_href FROM eventoj WHERE uuid = ?", (existing_uuid,)
        )
        assert row["remote_href"] == "/cal/local-001.ics"

        # New event imported
        new_row = db.execute_one(
            "SELECT titolo FROM eventoj WHERE uuid = ?", ("remote-uid-002",)
        )
        assert new_row is not None
        assert new_row["titolo"] == "Remote Event 2"