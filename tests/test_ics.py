"""Tests for ICS utility functions."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TEST_DIR = Path(__file__).parent
sys.path.insert(0, str(_TEST_DIR.parent / "src"))
sys.path.insert(0, str(_TEST_DIR.parent.parent / "A-core" / "src"))


# ──────────────────────────────────────────────────────────────────────────────
# ICS parser tests
# ──────────────────────────────────────────────────────────────────────────────


class TestIterIcsEvents:
    """Tests for iter_ics_events."""

    def test_empty_text(self):
        from A_organizi.utils.ics import iter_ics_events

        assert iter_ics_events("") == []

    def test_single_event(self):
        from A_organizi.utils.ics import iter_ics_events

        ics = "\n".join([
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "BEGIN:VEVENT",
            "UID:abc123",
            "SUMMARY:Meeting",
            "DTSTART:20260421T100000Z",
            "DTEND:20260421T110000Z",
            "END:VEVENT",
            "END:VCALENDAR",
        ])
        events = iter_ics_events(ics)
        assert len(events) == 1
        assert events[0]["SUMMARY"] == "Meeting"
        assert events[0]["DTSTART"] == "20260421T100000Z"

    def test_multiple_events(self):
        from A_organizi.utils.ics import iter_ics_events

        ics = "\n".join([
            "BEGIN:VCALENDAR",
            "BEGIN:VEVENT",
            "SUMMARY:First",
            "DTSTART:20260421T100000Z",
            "END:VEVENT",
            "BEGIN:VEVENT",
            "SUMMARY:Second",
            "DTSTART:20260422T100000Z",
            "END:VEVENT",
            "END:VCALENDAR",
        ])
        events = iter_ics_events(ics)
        assert len(events) == 2
        assert events[0]["SUMMARY"] == "First"
        assert events[1]["SUMMARY"] == "Second"

    def test_event_with_properties(self):
        from A_organizi.utils.ics import iter_ics_events

        ics = "\n".join([
            "BEGIN:VCALENDAR",
            "BEGIN:VEVENT",
            "SUMMARY:Test",
            "DTSTART:20260421T100000Z",
            "DTEND:20260421T110000Z",
            "LOCATION:Room 42",
            "CATEGORIES:meeting",
            "DESCRIPTION:Discuss project",
            "RRULE:FREQ=WEEKLY",
            "ATTENDEE:mailto:alice@example.com",
            "END:VEVENT",
            "END:VCALENDAR",
        ])
        events = iter_ics_events(ics)
        assert len(events) == 1
        e = events[0]
        assert e["LOCATION"] == "Room 42"
        assert e["CATEGORIES"] == "meeting"
        assert "Discuss" in e["DESCRIPTION"]
        assert e["RRULE"] == "FREQ=WEEKLY"

    def test_parameter_stripping(self):
        """ICS parameters after semicolons are stripped from keys."""
        from A_organizi.utils.ics import iter_ics_events

        ics = "\n".join([
            "BEGIN:VCALENDAR",
            "BEGIN:VEVENT",
            "DTSTART;VALUE=DATE:20260421",
            "SUMMARY:All Day",
            "END:VEVENT",
            "END:VCALENDAR",
        ])
        events = iter_ics_events(ics)
        assert len(events) == 1
        # Key should be "DTSTART" (parameter stripped)
        assert "DTSTART" in events[0]


class TestIcsDt:
    """Tests for ics_dt."""

    def test_utc_format(self):
        from A_organizi.utils.ics import ics_dt
        from datetime import timezone

        dt = ics_dt("20260421T100000Z")
        assert dt.year == 2026
        assert dt.month == 4
        assert dt.day == 21
        assert dt.hour == 10
        assert dt.minute == 0
        assert dt.tzinfo is not None

    def test_local_format(self):
        """Local time without Z is treated as UTC."""
        from A_organizi.utils.ics import ics_dt
        from datetime import timezone

        dt = ics_dt("20260421T100000")
        assert dt.hour == 10
        assert dt.tzinfo is not None

    def test_date_only_format(self):
        """All-day event (date only) treated as UTC midnight."""
        from A_organizi.utils.ics import ics_dt

        dt = ics_dt("20260421")
        assert dt.hour == 0
        assert dt.minute == 0


# ──────────────────────────────────────────────────────────────────────────────
# ICS generation tests
# ──────────────────────────────────────────────────────────────────────────────


class TestEventsToIcs:
    """Tests for events_to_ics."""

    def test_single_event(self):
        from A_organizi.utils.ics import events_to_ics

        rows = [{
            "uuid": "abc-123",
            "titolo": "Meeting",
            "komenco": "2026-04-21T10:00:00+00:00",
            "fino": "2026-04-21T11:00:00+00:00",
            "loko": "",
            "kategorio": "",
            "priskribo": "",
        }]
        result = events_to_ics(rows)
        assert "BEGIN:VCALENDAR" in result
        assert "END:VCALENDAR" in result
        assert "BEGIN:VEVENT" in result
        assert "END:VEVENT" in result
        assert "SUMMARY:Meeting" in result
        assert "DTSTART:20260421T100000Z" in result

    def test_roundtrip(self):
        """Export then import should produce same number of events."""
        from A_organizi.utils.ics import events_to_ics, iter_ics_events

        rows = [{
            "uuid": "abc-123",
            "titolo": "Test Event",
            "komenco": "2026-04-21T10:00:00+00:00",
            "fino": "2026-04-21T11:00:00+00:00",
            "loko": "Room 1",
            "kategorio": "meeting",
            "priskribo": "Notes",
        }]
        ics_text = events_to_ics(rows)
        parsed = iter_ics_events(ics_text)
        assert len(parsed) == 1
        assert parsed[0]["SUMMARY"] == "Test Event"
        assert parsed[0]["LOCATION"] == "Room 1"


# ──────────────────────────────────────────────────────────────────────────────
# Integration tests (ICS import into DB)
# ──────────────────────────────────────────────────────────────────────────────


class TestInsertIcsEvents:
    """Tests for insert_ics_events."""

    @pytest.fixture
    def db(self, monkeypatch, tmp_path):
        """Set up a clean database."""
        import A_organizi.data.storage as storage_module

        
        import A_organizi.service.kalendaro as kal_svc

        monkeypatch.setattr(kal_svc, "_kalendaro_service", None)
        monkeypatch.setattr(kal_svc, "_evento_service", None)

        from A_organizi.service.kalendaro import get_evento_service, get_kalendaro_service

        # Create a calendar
        cal_svc = get_kalendaro_service()
        cal = cal_svc.create({"url": "https://cal.ics", "username": "u"})
        return get_evento_service().db, cal["uuid"]

    def test_insert_single_event(self, db):
        from A_organizi.utils.ics import insert_ics_events

        db_conn, cal_uuid = db
        ics = "\n".join([
            "BEGIN:VCALENDAR",
            "BEGIN:VEVENT",
            "SUMMARY:Imported Meeting",
            "DTSTART:20260421T100000Z",
            "DTEND:20260421T110000Z",
            "END:VEVENT",
            "END:VCALENDAR",
        ])
        added = insert_ics_events(db_conn, cal_uuid, ics)
        assert len(added) == 1

        # Verify in DB
        rows = db_conn.execute(
            "SELECT titolo FROM eventoj WHERE uuid = ?", (added[0],)
        )
        assert len(rows) == 1
        assert rows[0]["titolo"] == "Imported Meeting"

    def test_dedup(self, db):
        from A_organizi.utils.ics import insert_ics_events

        db_conn, cal_uuid = db
        ics = "\n".join([
            "BEGIN:VCALENDAR",
            "BEGIN:VEVENT",
            "SUMMARY:Meeting",
            "DTSTART:20260421T100000Z",
            "DTEND:20260421T110000Z",
            "END:VEVENT",
            "END:VCALENDAR",
        ])
        added1 = insert_ics_events(db_conn, cal_uuid, ics)
        added2 = insert_ics_events(db_conn, cal_uuid, ics)
        assert len(added1) == 1
        assert len(added2) == 0  # duplicate, not inserted

    def test_multiple_events(self, db):
        from A_organizi.utils.ics import insert_ics_events

        db_conn, cal_uuid = db
        ics = "\n".join([
            "BEGIN:VCALENDAR",
            "BEGIN:VEVENT",
            "SUMMARY:First",
            "DTSTART:20260421T100000Z",
            "DTEND:20260421T110000Z",
            "END:VEVENT",
            "BEGIN:VEVENT",
            "SUMMARY:Second",
            "DTSTART:20260422T100000Z",
            "DTEND:20260422T110000Z",
            "END:VEVENT",
            "END:VCALENDAR",
        ])
        added = insert_ics_events(db_conn, cal_uuid, ics)
        assert len(added) == 2

    def test_insert_with_full_details(self, db):
        from A_organizi.utils.ics import insert_ics_events

        db_conn, cal_uuid = db
        ics = "\n".join([
            "BEGIN:VCALENDAR",
            "BEGIN:VEVENT",
            "SUMMARY:Detailed",
            "DTSTART:20260421T100000Z",
            "DTEND:20260421T110000Z",
            "LOCATION:Office",
            "CATEGORIES:work",
            "DESCRIPTION:Full description here",
            "RRULE:FREQ=DAILY",
            "END:VEVENT",
            "END:VCALENDAR",
        ])
        added = insert_ics_events(db_conn, cal_uuid, ics)
        assert len(added) == 1
        row = db_conn.execute_one(
            "SELECT * FROM eventoj WHERE uuid = ?", (added[0],)
        )
        assert row is not None
        assert row["loko"] == "Office"
        assert row["kategorio"] == "work"
        assert row["priskribo"] == "Full description here"
        assert row["ripeto"] == "FREQ=DAILY"


# ──────────────────────────────────────────────────────────────────────────────
# CLI tests
# ──────────────────────────────────────────────────────────────────────────────


class TestImportExportCLI:
    """Tests for importi and eksporti CLI commands."""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, tmp_path):
        """Patch data dir and reset singletons."""
        import A_organizi.data.storage as storage_module

        
        import A_organizi.service.kalendaro as kal_svc

        monkeypatch.setattr(kal_svc, "_kalendaro_service", None)
        monkeypatch.setattr(kal_svc, "_evento_service", None)

        # Mock probe to avoid network calls
        import A_organizi.cli.kalendaro as kal_cli
        monkeypatch.setattr(
            kal_cli,
            "probe_calendar_config",
            lambda url, user, pw: {"count": "0", "description": "0"},
        )
        monkeypatch.setattr(kal_cli, "set_password", lambda uuid, pw: None)

    def test_importi(self, tmp_path):
        """Import an ICS file via CLI."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()

        # Create a LOCAL calendar (no -u, no -p needed)
        cal_result = runner.invoke(
            app, ["kalendaro", "aldoni", "file:///tmp/test.ics"]
        )
        assert cal_result.exit_code == 0
        cal_id = cal_result.output.split("#")[1].split(":")[0].strip()

        from A_organizi.service.kalendaro import get_evento_service

        # Create an ICS file
        ics_file = tmp_path / "events.ics"
        ics_file.write_text("\n".join([
            "BEGIN:VCALENDAR",
            "BEGIN:VEVENT",
            "SUMMARY:CLI Import",
            "DTSTART:20260421T100000Z",
            "DTEND:20260421T110000Z",
            "END:VEVENT",
            "END:VCALENDAR",
        ]), encoding="utf-8")

        result = runner.invoke(
            app, ["okazajo", "importi", cal_id, str(ics_file)]
        )
        assert result.exit_code == 0, result.output

    def test_eksporti_to_file(self, tmp_path):
        """Export events to an ICS file via CLI."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()

        # Create a calendar and an event first
        cal_result = runner.invoke(
            app, ["kalendaro", "aldoni", "file:///tmp/test.ics"]
        )
        assert cal_result.exit_code == 0
        cal_id = cal_result.output.split("#")[1].split(":")[0].strip()

        from A_organizi.service.kalendaro import get_evento_service
        evt_svc = get_evento_service()
        evt_svc.create({
            "kalendaro_uuid": cal_id,
            "titolo": "Export Test",
            "komenco": "2026-04-21T10:00:00+00:00",
            "fino": "2026-04-21T11:00:00+00:00",
        })

        out_file = tmp_path / "export.ics"
        result = runner.invoke(
            app, ["okazajo", "eksporti", "20260401", "20260430", "-d", str(out_file)]
        )
        assert result.exit_code == 0, result.output
        assert out_file.exists()
        assert "Export Test" in out_file.read_text()

    def test_eksporti_stdout(self, tmp_path):
        """Export events to stdout via CLI."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()

        cal_result = runner.invoke(
            app, ["kalendaro", "aldoni", "file:///tmp/test.ics"]
        )
        assert cal_result.exit_code == 0
        cal_id = cal_result.output.split("#")[1].split(":")[0].strip()

        from A_organizi.service.kalendaro import get_evento_service
        evt_svc = get_evento_service()
        evt_svc.create({
            "kalendaro_uuid": cal_id,
            "titolo": "Stdout Test",
            "komenco": "2026-04-21T10:00:00+00:00",
            "fino": "2026-04-21T11:00:00+00:00",
        })

        result = runner.invoke(app, ["okazajo", "eksporti", "20260401", "20260430"])
        assert result.exit_code == 0, result.output
        assert "Stdout Test" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
