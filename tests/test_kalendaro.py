"""Tests for kalendaro (calendar) service and CLI."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_TEST_DIR = Path(__file__).parent
sys.path.insert(0, str(_TEST_DIR.parent / "src"))
sys.path.insert(0, str(_TEST_DIR.parent.parent / "A-core" / "src"))


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def setup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Patch data dir and reset service singletons."""
    import A_organizi.data.storage as storage_module

    monkeypatch.setattr(storage_module, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(storage_module, "_DB_FILE", tmp_path / "organizi.db")

    import A_organizi.service.kalendaro as kal_svc

    monkeypatch.setattr(kal_svc, "_kalendaro_service", None)
    monkeypatch.setattr(kal_svc, "_evento_service", None)


@pytest.fixture
def cal_svc(setup):
    """Get a fresh CalendarService."""
    from A_organizi.service.kalendaro import get_kalendaro_service

    return get_kalendaro_service()


@pytest.fixture
def evt_svc(setup):
    """Get a fresh EventService."""
    from A_organizi.service.kalendaro import get_evento_service

    return get_evento_service()


# ──────────────────────────────────────────────────────────────────────────────
# Calendar service tests
# ──────────────────────────────────────────────────────────────────────────────


class TestCalendarService:
    """Tests for CalendarService."""

    def test_create_and_get(self, cal_svc):
        data = cal_svc.create({
            "url": "https://example.com/cal.ics",
            "username": "alice",
            "remote": 1,
        })
        assert "uuid" in data
        assert data["url"] == "https://example.com/cal.ics"
        retrieved = cal_svc.get(data["uuid"])
        assert retrieved is not None

    def test_calendar_exists(self, cal_svc):
        cal_svc.create({
            "url": "https://example.com/cal.ics",
            "username": "alice",
        })
        assert cal_svc.calendar_exists(
            "https://example.com/cal.ics", "alice"
        ) is True
        assert cal_svc.calendar_exists(
            "https://example.com/cal.ics", "bob"
        ) is False

    def test_resolve_uuid(self, cal_svc):
        data = cal_svc.create({"url": "https://cal.com/ics", "username": "u"})
        full_uuid = data["uuid"]
        prefix = full_uuid[:8]
        resolved = cal_svc.resolve_uuid(prefix)
        assert resolved == full_uuid
        assert cal_svc.resolve_uuid("nonexistent") is None

    def test_list(self, cal_svc):
        cal_svc.create({"url": "https://cal1.com/ics", "username": "u1"})
        cal_svc.create({"url": "https://cal2.com/ics", "username": "u2"})
        rows = cal_svc.list()
        assert len(rows) >= 2

    def test_delete_cascades_events(self, cal_svc, evt_svc):
        cal = cal_svc.create({"url": "https://cal.com/ics", "username": "u"})
        evt_svc.create({
            "kalendaro_uuid": cal["uuid"],
            "titolo": "Event",
            "komenco": "2026-04-21T10:00:00+00:00",
            "fino": "2026-04-21T11:00:00+00:00",
        })
        cal_svc.delete(cal["uuid"], soft=False)
        # Event should be gone
        events = evt_svc.list()
        assert all(
            e.get("kalendaro_uuid") != cal["uuid"] for e in events
        )


# ──────────────────────────────────────────────────────────────────────────────
# Event service tests
# ──────────────────────────────────────────────────────────────────────────────


class TestEventService:
    """Tests for EventService."""

    def _make_event(self, evt_svc, cal_uuid: str, titolo: str, komenco: str):
        return evt_svc.create({
            "kalendaro_uuid": cal_uuid,
            "titolo": titolo,
            "komenco": komenco,
            "fino": "2026-04-21T11:00:00+00:00",
        })

    def test_create_and_get(self, evt_svc, cal_svc):
        cal = cal_svc.create({"url": "https://cal.com/ics", "username": "u"})
        data = evt_svc.create({
            "kalendaro_uuid": cal["uuid"],
            "titolo": "Meeting",
            "komenco": "2026-04-21T10:00:00+00:00",
            "fino": "2026-04-21T11:00:00+00:00",
            "kategorio": "laboro",
            "loko": "Oficejo",
        })
        assert data["titolo"] == "Meeting"
        assert data["kategorio"] == "laboro"
        retrieved = evt_svc.get(data["uuid"])
        assert retrieved is not None

    def test_list_by_date_range(self, evt_svc, cal_svc):
        cal = cal_svc.create({"url": "https://cal.com/ics", "username": "u"})
        self._make_event(evt_svc, cal["uuid"], "Early", "2026-04-01T10:00:00+00:00")
        self._make_event(evt_svc, cal["uuid"], "Middle", "2026-04-15T10:00:00+00:00")
        self._make_event(evt_svc, cal["uuid"], "Late", "2026-04-30T10:00:00+00:00")

        from datetime import date

        rows = evt_svc.list_by_date_range(date(2026, 4, 10), date(2026, 4, 20))
        assert len(rows) == 1
        assert rows[0]["titolo"] == "Middle"

    def test_list_by_date_range_with_calendar_filter(self, evt_svc, cal_svc):
        cal1 = cal_svc.create({"url": "https://cal1.com/ics", "username": "u1"})
        cal2 = cal_svc.create({"url": "https://cal2.com/ics", "username": "u2"})
        self._make_event(evt_svc, cal1["uuid"], "Cal1 Ev", "2026-04-15T10:00:00+00:00")
        self._make_event(evt_svc, cal2["uuid"], "Cal2 Ev", "2026-04-15T10:00:00+00:00")

        from datetime import date

        rows = evt_svc.list_by_date_range(
            date(2026, 4, 1), date(2026, 4, 30), [cal1["uuid"]]
        )
        assert len(rows) == 1
        assert rows[0]["titolo"] == "Cal1 Ev"

    def test_delete_by_date_range(self, evt_svc, cal_svc):
        cal = cal_svc.create({"url": "https://cal.com/ics", "username": "u"})
        self._make_event(evt_svc, cal["uuid"], "Del", "2026-04-15T10:00:00+00:00")
        self._make_event(evt_svc, cal["uuid"], "Keep", "2026-04-30T10:00:00+00:00")

        from datetime import date

        deleted = evt_svc.delete_by_date_range(date(2026, 4, 1), date(2026, 4, 20))
        assert deleted == 1
        remaining = evt_svc.list()
        titles = [r["titolo"] for r in remaining]
        assert "Keep" in titles
        assert "Del" not in titles

    def test_search(self, evt_svc, cal_svc):
        cal = cal_svc.create({"url": "https://cal.com/ics", "username": "u"})
        self._make_event(evt_svc, cal["uuid"], "Team Meeting", "2026-04-21T10:00:00+00:00")
        self._make_event(evt_svc, cal["uuid"], "Lunch", "2026-04-21T12:00:00+00:00")

        results = evt_svc.search(query="meeting")
        assert len(results) == 1
        assert results[0]["titolo"] == "Team Meeting"

    def test_search_by_category(self, evt_svc, cal_svc):
        cal = cal_svc.create({"url": "https://cal.com/ics", "username": "u"})
        evt_svc.create({
            "kalendaro_uuid": cal["uuid"],
            "titolo": "Work", "kategorio": "laboro",
            "komenco": "2026-04-21T10:00:00+00:00",
            "fino": "2026-04-21T11:00:00+00:00",
        })
        evt_svc.create({
            "kalendaro_uuid": cal["uuid"],
            "titolo": "Play", "kategorio": "libero",
            "komenco": "2026-04-21T12:00:00+00:00",
            "fino": "2026-04-21T13:00:00+00:00",
        })
        results = evt_svc.search(kategorio="laboro")
        assert len(results) == 1
        assert results[0]["titolo"] == "Work"

    def test_resolve_event_uuid(self, evt_svc, cal_svc):
        cal = cal_svc.create({"url": "https://cal.com/ics", "username": "u"})
        data = self._make_event(evt_svc, cal["uuid"], "Test", "2026-04-21T10:00:00+00:00")
        resolved = evt_svc.resolve_uuid(data["uuid"][:8])
        assert resolved == data["uuid"]


# ──────────────────────────────────────────────────────────────────────────────
# CLI tests
# ──────────────────────────────────────────────────────────────────────────────


class TestKalendaroCLI:
    """Tests for kalendaro CLI commands."""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, tmp_path):
        """Patch data dir and reset singletons."""
        import A_organizi.data.storage as storage_module

        monkeypatch.setattr(storage_module, "_DATA_DIR", tmp_path)
        monkeypatch.setattr(storage_module, "_DB_FILE", tmp_path / "organizi.db")

        import A_organizi.service.kalendaro as kal_svc

        monkeypatch.setattr(kal_svc, "_kalendaro_service", None)
        monkeypatch.setattr(kal_svc, "_evento_service", None)

        # Mock probe_calendar_config to avoid network calls
        import A_organizi.cli.kalendaro as kal_cli
        monkeypatch.setattr(
            kal_cli,
            "probe_calendar_config",
            lambda url, user, pw: {"count": "0", "description": "0 evento(j)"},
        )
        monkeypatch.setattr(kal_cli, "set_password", lambda uuid, pw: None)

    def _cal_uuid(self, runner, app, url="https://cal.ics", username="u", password="secret"):
        """Helper: add calendar and return its UUID prefix."""
        result = runner.invoke(
            app, ["kalendaro", "aldoni", url, "-u", username, "-p", password]
        )
        # Debug: print output if failed
        if result.exit_code != 0:
            print(f"FAIL: {result.output}", file=sys.stderr)
        assert result.exit_code == 0, result.output
        # Extract UUID from "Aldonis kalendaron #abc123: ..."
        # Output format: "...#16d92dc5 kun pasvorto.\n...#16d92dc5: https://..."
        for line in result.output.split("\n"):
            if line.startswith("Aldonis kalendaron #") and "kun pasvorto" not in line:
                return line.split("#")[1].split(":")[0].strip()
        # Fallback: find any line with #
        import re
        match = re.search(r"#([a-f0-9]{8})", result.output)
        if match:
            return match.group(1)
        return result.output.split("#")[1].split(":")[0].strip()

    def test_aldoni(self):
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        result = runner.invoke(
            app, ["kalendaro", "aldoni", "https://cal.ics", "-u", "alice", "-p", "secret"]
        )
        assert result.exit_code == 0, result.output
        assert "Aldonis kalendaron" in result.output

    def test_aldoni_duplicate(self):
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        runner.invoke(app, ["kalendaro", "aldoni", "https://cal.ics", "-u", "u", "-p", "secret"])
        result = runner.invoke(
            app, ["kalendaro", "aldoni", "https://cal.ics", "-u", "u", "-p", "secret"]
        )
        assert result.exit_code != 0

    def test_ls_kalendaroj(self):
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        runner.invoke(app, ["kalendaro", "aldoni", "https://cal.ics", "-u", "u", "-p", "secret"])
        result = runner.invoke(app, ["kalendaro", "ls"])
        assert result.exit_code == 0, result.output
        assert "cal.ics" in result.output

    def test_modifi(self):
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        cal_id = self._cal_uuid(runner, app)
        result = runner.invoke(
            app, ["kalendaro", "modifi", cal_id, "--url", "https://new.ics"]
        )
        assert result.exit_code == 0, result.output

    def test_forigi_kalendaro(self):
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        cal_id = self._cal_uuid(runner, app)
        result = runner.invoke(
            app, ["kalendaro", "forigi", cal_id]
        )
        assert result.exit_code == 0, result.output

    def test_ls_events(self):
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        cal_id = self._cal_uuid(runner, app)
        result = runner.invoke(app, ["okazajo", "ls"])
        assert result.exit_code == 0, result.output

    def test_ls_events_with_date(self):
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        self._cal_uuid(runner, app)
        result = runner.invoke(app, ["okazajo", "ls", "20260421"])
        assert result.exit_code == 0, result.output

    def test_vidi(self):
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        cal_id = self._cal_uuid(runner, app)
        from A_organizi.service.kalendaro import get_evento_service

        evt_svc = get_evento_service()
        evt = evt_svc.create({
            "kalendaro_uuid": cal_id,
            "titolo": "Meeting",
            "komenco": "2026-04-21T10:00:00+00:00",
            "fino": "2026-04-21T11:00:00+00:00",
        })
        result = runner.invoke(app, ["okazajo", "vidi", evt["uuid"][:8]])
        assert result.exit_code == 0, result.output
        assert "Meeting" in result.output

    def test_vidi_not_found(self):
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["okazajo", "vidi", "nonexistent"])
        assert result.exit_code == 0

    def test_forigi_event(self):
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        cal_id = self._cal_uuid(runner, app)
        from A_organizi.service.kalendaro import get_evento_service

        evt_svc = get_evento_service()
        evt = evt_svc.create({
            "kalendaro_uuid": cal_id,
            "titolo": "Delete Me",
            "komenco": "2026-04-21T10:00:00+00:00",
            "fino": "2026-04-21T11:00:00+00:00",
        })
        result = runner.invoke(
            app, ["okazajo", "forigi", evt["uuid"][:8]],
            input="j\n",
        )
        assert result.exit_code == 0, result.output
        assert "Forigis" in result.output

    def test_serci(self):
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        cal_id = self._cal_uuid(runner, app)
        from A_organizi.service.kalendaro import get_evento_service

        evt_svc = get_evento_service()
        evt_svc.create({
            "kalendaro_uuid": cal_id,
            "titolo": "Special Event",
            "komenco": "2026-04-21T10:00:00+00:00",
            "fino": "2026-04-21T11:00:00+00:00",
        })
        result = runner.invoke(app, ["okazajo", "serci", "special"])
        assert result.exit_code == 0, result.output
        assert "Special Event" in result.output

    def test_help_shows_kalendaro_commands(self):
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["kalendaro", "--help"])
        assert result.exit_code == 0
        for cmd in ["aldoni", "ls", "modifi", "forigi"]:
            assert cmd in result.output, f"Missing kalendaro command: {cmd}"

    def test_help_shows_okazajo_commands(self):
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["okazajo", "--help"])
        assert result.exit_code == 0
        for cmd in ["aldoni", "ls", "vidi", "serci", "modifi", "forigi", "amase-forigi"]:
            assert cmd in result.output, f"Missing okazajo command: {cmd}"




# ──────────────────────────────────────────────────────────────────────────────
# Okazajo CLI tests (new UX: optional -k, date+time split, RRULE)
# ──────────────────────────────────────────────────────────────────────────────


class TestOkazajoAldoniCLI:
    """Tests for okazajo aldoni with new UX (date+time split, RRULE)."""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, tmp_path):
        """Patch data dir, reset singletons, mock network calls."""
        import A_organizi.data.storage as storage_module
        import A_organizi.service.kalendaro as kal_svc

        monkeypatch.setattr(storage_module, "_DATA_DIR", tmp_path)
        monkeypatch.setattr(storage_module, "_DB_FILE", tmp_path / "organizi.db")
        monkeypatch.setattr(kal_svc, "_kalendaro_service", None)
        monkeypatch.setattr(kal_svc, "_evento_service", None)

        import A_organizi.cli.kalendaro as kal_cli
        monkeypatch.setattr(kal_cli, "probe_calendar_config",
                            lambda url, user, pw: {"count": "0", "description": "0 evento(j)"})
        monkeypatch.setattr(kal_cli, "set_password", lambda uuid, pw: None)

    def _add_calendar(self, runner, app, url="https://cal.ics"):
        """Add a calendar and return its full UUID from DB."""
        from A_organizi.service.kalendaro import get_kalendaro_service
        svc = get_kalendaro_service()
        result = svc.create({"url": url, "username": "u", "remote": 0})
        return result["uuid"]

    def test_aldoni_requires_titolo_and_dato(self):
        """Without --titolo and --dato, should fail."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        cal_uuid = self._add_calendar(runner, app)

        # With -k but no titolo or --dato
        result = runner.invoke(app, [
            "okazajo", "aldoni", "-k", cal_uuid[:8],
        ])
        assert result.exit_code != 0
        assert "titolo" in result.output.lower() or "dato" in result.output.lower()

    def test_aldoni_positional_titolo(self):
        """Titolo can be given as positional argument (new UX)."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        cal_uuid = self._add_calendar(runner, app)

        result = runner.invoke(app, [
            "okazajo", "aldoni",
            "Meeting",       # positional titolo
            "1000",           # positional komenco
            "1130",           # positional fino
            "-k", cal_uuid[:8],
            "--dato", "20260602",
        ])
        assert result.exit_code == 0, result.output
        assert "Aldonis" in result.output
        assert "Meeting" in result.output

    def test_aldoni_with_explicit_calendar(self):
        """Basic event creation with explicit -k, --dato and --komenco/--fino."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        cal_uuid = self._add_calendar(runner, app)

        result = runner.invoke(app, [
            "okazajo", "aldoni",
            "Test Event",     # positional titolo
            "1000",           # positional komenco
            "1130",           # positional fino
            "-k", cal_uuid[:8],
            "--dato", "20260602",
        ])
        assert result.exit_code == 0, result.output
        assert "Aldonis" in result.output
        assert "Test Event" in result.output

    def test_aldoni_with_single_calendar_auto(self):
        """With exactly one calendar, -k should be optional (auto-select)."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        self._add_calendar(runner, app)

        result = runner.invoke(app, [
            "okazajo", "aldoni",
            "Auto Event",     # positional titolo
            "--dato", "20260602",
        ])
        assert result.exit_code == 0, result.output
        assert "Aldonis" in result.output

    def test_aldoni_with_rrule_shorthand(self):
        """RRULE shorthand 'daily' should expand to FREQ=DAILY."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        cal_uuid = self._add_calendar(runner, app)

        result = runner.invoke(app, [
            "okazajo", "aldoni",
            "Daily Standup",  # positional titolo
            "0900",           # positional komenco
            "0915",           # positional fino
            "-k", cal_uuid[:8],
            "--dato", "20260602",
            "--ripeto", "daily",
        ])
        assert result.exit_code == 0, result.output

        # Verify RRULE was stored
        from A_organizi.service.kalendaro import get_evento_service
        events = get_evento_service().list()
        assert len(events) == 1
        assert events[0]["ripeto"] == "FREQ=DAILY"

    def test_aldoni_with_invalid_rrule(self):
        """Invalid RRULE should be rejected."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        cal_uuid = self._add_calendar(runner, app)

        result = runner.invoke(app, [
            "okazajo", "aldoni",
            "Bad RRULE",     # positional titolo
            "-k", cal_uuid[:8],
            "--dato", "20260602",
            "--ripeto", "FREQ=HOURLY",
        ])
        assert result.exit_code != 0

    def test_aldoni_cross_midnight(self):
        """When fino < komenco, end date auto-advances (cross-midnight).

        The `fino` ISO string must be strictly greater than `komenco`
        in UTC, confirming the date was advanced.
        """
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        cal_uuid = self._add_calendar(runner, app)

        result = runner.invoke(app, [
            "okazajo", "aldoni",
            "Late Event",    # positional titolo
            "2200",          # positional komenco
            "0100",          # positional fino
            "-k", cal_uuid[:8],
            "--dato", "20260602",
        ])
        assert result.exit_code == 0, result.output

        from A_organizi.service.kalendaro import get_evento_service
        events = get_evento_service().list()
        assert len(events) == 1
        # Both are UTC — fino must be > komenco (cross-midnight worked)
        assert events[0]["fino"] > events[0]["komenco"], (
            f"Expected fino > komenco, got komenco={events[0]['komenco']} "
            f"fino={events[0]['fino']}"
        )

    def test_aldoni_multi_day(self):
        """Multi-day event with explicit --dato-gis."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        cal_uuid = self._add_calendar(runner, app)

        result = runner.invoke(app, [
            "okazajo", "aldoni",
            "Multi-Day",     # positional titolo
            "1000",          # positional komenco
            "1800",          # positional fino
            "-k", cal_uuid[:8],
            "--dato", "20260602",
            "--dato-gis", "20260605",
        ])
        assert result.exit_code == 0, result.output

        from A_organizi.service.kalendaro import get_evento_service
        events = get_evento_service().list()
        assert len(events) == 1
        assert "2026-06-05" in events[0]["fino"]

    def test_help_shows_new_options(self):
        """Help text should show positional TITOLO, KOMENCO, FINO and the new --ripeto with RRULE."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["okazajo", "aldoni", "--help"])
        assert result.exit_code == 0
        # Positional args shown in help
        assert "TITOLO" in result.output
        assert "KOMENCO" in result.output
        assert "FINO" in result.output
        # Options
        assert "--dato" in result.output
        assert "--dato-gis" in result.output
        assert "--ripeto" in result.output
        # RRULE examples in help
        assert "FREQ=DAILY" in result.output
        assert "FREQ=WEEKLY" in result.output


class TestOkazajoModifiCLI:
    """Tests for okazajo modifi with date+time split."""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, tmp_path):
        """Patch data dir and reset singletons."""
        import A_organizi.data.storage as storage_module
        import A_organizi.service.kalendaro as kal_svc

        monkeypatch.setattr(storage_module, "_DATA_DIR", tmp_path)
        monkeypatch.setattr(storage_module, "_DB_FILE", tmp_path / "organizi.db")
        monkeypatch.setattr(kal_svc, "_kalendaro_service", None)
        monkeypatch.setattr(kal_svc, "_evento_service", None)

        import A_organizi.cli.kalendaro as kal_cli
        monkeypatch.setattr(kal_cli, "probe_calendar_config",
                            lambda url, user, pw: {"count": "0", "description": "0 evento(j)"})
        monkeypatch.setattr(kal_cli, "set_password", lambda uuid, pw: None)

    def _create_event(self, titolo="Existing", komenco="2026-06-02T10:00:00+00:00",
                       fino="2026-06-02T11:00:00+00:00"):
        """Create a calendar + event, return event UUID."""
        from A_organizi.service.kalendaro import get_kalendaro_service, get_evento_service
        cal_svc = get_kalendaro_service()
        cal = cal_svc.create({"url": "https://cal.ics", "username": "u", "remote": 0})

        evt_svc = get_evento_service()
        evt = evt_svc.create({
            "kalendaro_uuid": cal["uuid"],
            "titolo": titolo,
            "komenco": komenco,
            "fino": fino,
        })
        return evt["uuid"]

    def test_modifi_change_date(self):
        """Change date with --dato (keeps default times 0000-2359)."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        evt_uuid = self._create_event()

        result = runner.invoke(app, [
            "okazajo", "modifi", evt_uuid[:8],
            "--dato", "20260704",
        ])
        assert result.exit_code == 0, result.output
        assert "Modifis" in result.output

    def test_modifi_change_time_only(self):
        """Change time without --dato uses event's current date."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        evt_uuid = self._create_event()

        result = runner.invoke(app, [
            "okazajo", "modifi", evt_uuid[:8],
            "--komenco", "1400",
            "--fino", "1530",
        ])
        assert result.exit_code == 0, result.output
        assert "Modifis" in result.output

    def test_modifi_change_rrule(self):
        """Change recurrence via RRULE shorthand."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        evt_uuid = self._create_event()

        result = runner.invoke(app, [
            "okazajo", "modifi", evt_uuid[:8],
            "--ripeto", "weekly",
        ])
        assert result.exit_code == 0, result.output

        from A_organizi.service.kalendaro import get_evento_service
        event = get_evento_service().get(evt_uuid)
        assert event["ripeto"] == "FREQ=WEEKLY"

    def test_modifi_invalid_rrule(self):
        """Invalid RRULE should be rejected."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        evt_uuid = self._create_event()

        result = runner.invoke(app, [
            "okazajo", "modifi", evt_uuid[:8],
            "--ripeto", "INVALID",
        ])
        assert result.exit_code != 0



# ──────────────────────────────────────────────────────────────────────────────
# Vici (sync queue monitor) CLI tests
# ──────────────────────────────────────────────────────────────────────────────


class TestViciCLI:
    """Tests for okazajo vici (sync queue monitor)."""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, tmp_path):
        """Patch data dir and reset singletons."""
        import A_organizi.data.storage as storage_module
        import A_organizi.service.kalendaro as kal_svc

        monkeypatch.setattr(storage_module, "_DATA_DIR", tmp_path)
        monkeypatch.setattr(storage_module, "_DB_FILE", tmp_path / "organizi.db")
        monkeypatch.setattr(kal_svc, "_kalendaro_service", None)
        monkeypatch.setattr(kal_svc, "_evento_service", None)

        import A_organizi.cli.kalendaro as kal_cli
        monkeypatch.setattr(kal_cli, "probe_calendar_config",
                            lambda url, user, pw: {"count": "0", "description": "0 evento(j)"})
        monkeypatch.setattr(kal_cli, "set_password", lambda uuid, pw: None)

    def _add_calendar(self, runner, app):
        """Add a calendar and return its full UUID."""
        from A_organizi.service.kalendaro import get_kalendaro_service
        svc = get_kalendaro_service()
        result = svc.create({"url": "https://cal.ics", "username": "u", "remote": 1})
        return result["uuid"]

    def test_vici_empty(self):
        """No sync queue entries should show empty message."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["okazajo", "vici"])
        assert result.exit_code == 0, result.output
        assert "Neniu sinkroniga tasko trovita" in result.output

    def test_vici_shows_entries(self):
        """Entries in sync queue should be displayed."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        cal_uuid = self._add_calendar(runner, app)

        # Enqueue a sync job directly
        from A_organizi.utils.sync import queue_sync
        from A_organizi.service.kalendaro import get_evento_service

        db = get_evento_service().db
        queue_sync(db, cal_uuid, "push", {"event_uuid": "test1234"})

        result = runner.invoke(app, ["okazajo", "vici"])
        assert result.exit_code == 0, result.output
        # Check for Rich table headers that survive narrow-terminal truncation
        assert "Kreita" in result.output or "ID" in result.output

    def test_vici_filter_by_status(self):
        """Filter sync queue by status."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        cal_uuid = self._add_calendar(runner, app)

        from A_organizi.utils.sync import queue_sync
        from A_organizi.service.kalendaro import get_evento_service

        db = get_evento_service().db
        queue_sync(db, cal_uuid, "push", {"event_uuid": "e1"})
        queue_sync(db, cal_uuid, "pull", {})

        # Filter by pending — both jobs start as pending
        result = runner.invoke(app, ["okazajo", "vici", "pending"])
        assert result.exit_code == 0, result.output
        # Check for column header that survives Rich truncation in narrow terminals
        assert "Stato" in result.output

    def test_vici_filter_by_calendar(self):
        """Filter sync queue by calendar UUID (full UUID, not prefix)."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        cal_uuid = self._add_calendar(runner, app)

        from A_organizi.utils.sync import queue_sync
        from A_organizi.service.kalendaro import get_evento_service

        db = get_evento_service().db
        queue_sync(db, cal_uuid, "push", {"event_uuid": "e1"})

        # Must pass full UUID for DB filter match
        result = runner.invoke(app, [
            "okazajo", "vici", "--kalendaro", cal_uuid,
        ])
        assert result.exit_code == 0, result.output
        assert "Kreita" in result.output or "ID" in result.output

    def test_vici_help_shown(self):
        """Help text should show for vici."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["okazajo", "vici", "--help"])
        assert result.exit_code == 0
        assert "STATO" in result.output
        assert "--kalendaro" in result.output

    def test_vici_hides_completed_by_default(self):
        """Default vici hides completed jobs, shows only pending/failed."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        cal_uuid = self._add_calendar(runner, app)

        from A_organizi.service.kalendaro import get_evento_service
        db = get_evento_service().db
        now = "2026-06-03T12:00:00"
        # Insert a completed job
        db.execute(
            "INSERT INTO sync_queue (id, calendar_uuid, operacio, payload, stato, eraro, kreita_je, modifita_je)"
            " VALUES ('done-job', ?, 'push', '{}', 'completed', '', ?, ?)",
            (cal_uuid, now, now),
        )
        # Insert a pending job
        db.execute(
            "INSERT INTO sync_queue (id, calendar_uuid, operacio, payload, stato, eraro, kreita_je, modifita_je)"
            " VALUES ('pend-job', ?, 'push', '{}', 'pending', '', ?, ?)",
            (cal_uuid, now, now),
        )

        result = runner.invoke(app, ["okazajo", "vici"])
        assert result.exit_code == 0, result.output
        assert "pend-job" in result.output or "pend" in result.output
        assert "done-job" not in result.output

    def test_vici_all_shows_completed(self):
        """vici --all shows all statuses including completed."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        cal_uuid = self._add_calendar(runner, app)

        from A_organizi.service.kalendaro import get_evento_service
        db = get_evento_service().db
        now = "2026-06-03T12:00:00"
        db.execute(
            "INSERT INTO sync_queue (id, calendar_uuid, operacio, payload, stato, eraro, kreita_je, modifita_je)"
            " VALUES ('done-job', ?, 'push', '{}', 'completed', '', ?, ?)",
            (cal_uuid, now, now),
        )

        result = runner.invoke(app, ["okazajo", "vici", "--all"])
        assert result.exit_code == 0, result.output
        assert "done-job" in result.output or "done" in result.output

    def test_vici_completed_filter_still_works(self):
        """vici completed still shows only completed jobs."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        cal_uuid = self._add_calendar(runner, app)

        from A_organizi.service.kalendaro import get_evento_service
        db = get_evento_service().db
        now = "2026-06-03T12:00:00"
        db.execute(
            "INSERT INTO sync_queue (id, calendar_uuid, operacio, payload, stato, eraro, kreita_je, modifita_je)"
            " VALUES ('done-job', ?, 'push', '{}', 'completed', '', ?, ?)",
            (cal_uuid, now, now),
        )
        db.execute(
            "INSERT INTO sync_queue (id, calendar_uuid, operacio, payload, stato, eraro, kreita_je, modifita_je)"
            " VALUES ('pend-job', ?, 'push', '{}', 'pending', '', ?, ?)",
            (cal_uuid, now, now),
        )

        result = runner.invoke(app, ["okazajo", "vici", "completed"])
        assert result.exit_code == 0, result.output
        assert "done-job" in result.output or "done" in result.output
        assert "pend-job" not in result.output


class TestReproviCLI:
    """Tests for okazajo reprovi (retry failed sync jobs)."""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, tmp_path):
        """Patch data dir and reset singletons."""
        import A_organizi.data.storage as storage_module
        import A_organizi.service.kalendaro as kal_svc

        monkeypatch.setattr(storage_module, "_DATA_DIR", tmp_path)
        monkeypatch.setattr(storage_module, "_DB_FILE", tmp_path / "organizi.db")
        monkeypatch.setattr(kal_svc, "_kalendaro_service", None)
        monkeypatch.setattr(kal_svc, "_evento_service", None)

    def test_reprovi_no_failed_jobs(self):
        """No failed jobs shows 'neniu malsukcesinta tasko'."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["okazajo", "reprovi"])
        assert result.exit_code == 0, result.output
        assert "Neniu malsukcesinta" in result.output

    @patch("A_organizi.utils.sync.process_sync_job")
    def test_reprovi_all(self, mock_process):
        """Reprovi all processes all failed jobs."""
        from typer.testing import CliRunner
        from A_organizi.cli import app
        from A_organizi.service.kalendaro import get_evento_service

        runner = CliRunner()
        db = get_evento_service().db
        db.execute(
            "INSERT INTO sync_queue (id, calendar_uuid, operacio, payload, stato, eraro, kreita_je, modifita_je)"
            " VALUES ('fjob', 'cal-uuid', 'push', '{}', 'failed', 'HTTP 500', '2026-06-02T12:00:00', '2026-06-02T12:00:00')"
        )

        result = runner.invoke(app, ["okazajo", "reprovi"])
        assert result.exit_code == 0, result.output
        mock_process.assert_called_once()

    @patch("A_organizi.utils.sync.process_sync_job")
    def test_reprovi_specific_job(self, mock_process):
        """Reprovi with job ID retries that specific job."""
        from typer.testing import CliRunner
        from A_organizi.cli import app
        from A_organizi.service.kalendaro import get_evento_service

        runner = CliRunner()
        db = get_evento_service().db
        db.execute(
            "INSERT INTO sync_queue (id, calendar_uuid, operacio, payload, stato, eraro, kreita_je, modifita_je)"
            " VALUES ('job-a', 'cal-uuid', 'push', '{}', 'failed', 'err', '2026-06-02T12:00:00', '2026-06-02T12:00:00')"
        )
        db.execute(
            "INSERT INTO sync_queue (id, calendar_uuid, operacio, payload, stato, eraro, kreita_je, modifita_je)"
            " VALUES ('job-b', 'cal-uuid', 'push', '{}', 'failed', 'err', '2026-06-02T12:00:00', '2026-06-02T12:00:00')"
        )

        result = runner.invoke(app, ["okazajo", "reprovi", "job-a"])
        assert result.exit_code == 0, result.output
        mock_process.assert_called_once()
        args, _ = mock_process.call_args
        assert args[1]["id"] == "job-a"

    def test_reprovi_help_shown(self):
        """Help text should show for reprovi."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["okazajo", "reprovi", "--help"])
        assert result.exit_code == 0
        assert "JOB_ID" in result.output or "job" in result.output.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
