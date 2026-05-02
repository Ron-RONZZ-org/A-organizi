"""Tests for todo (tasks) service, priority engine, and CLI."""

from __future__ import annotations

import sys
from pathlib import Path

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

    monkeypatch.setattr("A_organizi.service.todo._todo_service", None)
    monkeypatch.setattr("A_organizi.service.etikedo._etikedo_service", None)


@pytest.fixture
def svc(setup):
    """Get a fresh TodoService for testing."""
    from A_organizi.service import get_todo_service

    return get_todo_service()


@pytest.fixture
def etikedo_svc(setup):
    """Get a fresh EtikedoService for testing."""
    from A_organizi.service import get_etikedo_service

    return get_etikedo_service()


# ──────────────────────────────────────────────────────────────────────────────
# Priority engine tests
# ──────────────────────────────────────────────────────────────────────────────


class TestPriorityEngine:
    """Tests for priority formula engine."""

    def test_plain_number(self):
        from A_organizi.priority import compute_priority

        assert compute_priority("42", "2026-04-21T10:00:00+00:00") == 42.0
        assert compute_priority("0", "2026-04-21T10:00:00+00:00") == 0.0

    def test_empty_formula(self):
        from A_organizi.priority import compute_priority

        assert compute_priority("", "2026-04-21T10:00:00+00:00") == 0.0
        assert compute_priority(None, "2026-04-21T10:00:00+00:00") == 0.0

    def test_formula_with_days(self):
        """Formula using D (days since creation)."""
        from datetime import datetime, timezone, timedelta
        from A_organizi.priority import compute_priority

        created = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        # 20 + 2*5 = 30
        result = compute_priority("20 + 2 * D", created)
        assert result == pytest.approx(30.0, abs=0.1)

    def test_formula_with_hours(self):
        """Formula using H (hours since creation)."""
        from datetime import datetime, timezone, timedelta
        from A_organizi.priority import compute_priority

        created = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        # min(30, 10 * 2) = 20
        result = compute_priority("min(30, 10 * H)", created)
        assert result == pytest.approx(20.0, abs=1.0)

    def test_formula_capped(self):
        """Formula with min() caps the value."""
        from datetime import datetime, timezone, timedelta
        from A_organizi.priority import compute_priority

        created = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        # min(20+2*100, 70) = min(220, 70) = 70
        result = compute_priority("min(20 + 2 * D, 70)", created)
        assert result == pytest.approx(70.0, abs=1.0)

    def test_invalid_formula_raises(self):
        from A_organizi.priority import compute_priority

        with pytest.raises(ValueError):
            compute_priority("__import__('os')", "2026-04-21T10:00:00+00:00")

    def test_validate_formula(self):
        from A_organizi.priority import validate_formula

        assert validate_formula("42") is True
        assert validate_formula("20 + 2 * D") is True
        assert validate_formula("") is True
        assert validate_formula("__import__('os')") is False
        assert validate_formula("open('/etc')") is False

    def test_format_priority(self):
        from A_organizi.priority import format_priority

        result = format_priority("42", "2026-04-21T10:00:00+00:00")
        assert "42.00" in result
        # Plain number: no "kruda" suffix
        assert "kruda" not in result

    def test_format_priority_formula(self):
        from A_organizi.priority import format_priority

        result = format_priority("20+2*D", "2026-04-21T10:00:00+00:00")
        assert "kruda" in result
        assert "20+2*D" in result


# ──────────────────────────────────────────────────────────────────────────────
# Service tests
# ──────────────────────────────────────────────────────────────────────────────


class TestTodoService:
    """Tests for TodoService."""

    def test_create_and_get(self, svc):
        """Create a task and retrieve it."""
        data = svc.create({
            "titolo": "Test task",
            "titolo_norm": "test task",
            "prioritato": "42",
            "stato": "malfermita",
        })
        assert "uuid" in data
        assert data["titolo"] == "Test task"
        assert data["prioritato"] == "42"
        assert data["stato"] == "malfermita"

        retrieved = svc.get(data["uuid"])
        assert retrieved is not None

    def test_create_with_labels(self, svc, etikedo_svc):
        """Create task with label assignments."""
        lbl = etikedo_svc.create({"teksto": "urgxa", "teksto_norm": "urgxa"})
        data = svc.create({
            "titolo": "Urgent task",
            "titolo_norm": "urgent task",
            "prioritato": "0",
            "etikedo": [lbl["uuid"]],
        })
        labels = svc.get_labels(data["uuid"])
        assert len(labels) == 1

    def test_create_with_formula_priority(self, svc):
        """Create task with formula priority."""
        data = svc.create({
            "titolo": "Formula task",
            "titolo_norm": "formula task",
            "prioritato": "min(20 + 2 * D, 70)",
            "stato": "malfermita",
        })
        assert data["prioritato"] == "min(20 + 2 * D, 70)"

    def test_create_invalid_formula_raises(self, svc):
        """Creating with unsafe formula raises."""
        with pytest.raises(ValueError):
            svc.create({
                "titolo": "Bad",
                "titolo_norm": "bad",
                "prioritato": "__import__('os')",
            })

    def test_normalize_stato(self, svc):
        """Status normalization works for aliases."""
        assert svc.normalize_stato("done") == "farita"
        assert svc.normalize_stato("open") == "malfermita"
        assert svc.normalize_stato("cancelled") == "nuligita"
        assert svc.normalize_stato("farita") == "farita"
        with pytest.raises(ValueError):
            svc.normalize_stato("invalid_status")

    def test_update_status(self, svc):
        """Update task status."""
        data = svc.create({
            "titolo": "Do something",
            "titolo_norm": "do something",
            "stato": "malfermita",
        })
        svc.update(data["uuid"], {"stato": "farita"})
        retrieved = svc.get(data["uuid"])
        assert retrieved["stato"] == "farita"

    def test_search_by_text(self, svc):
        """Search tasks by text."""
        svc.create({
            "titolo": "Read a book",
            "titolo_norm": "read a book",
            "prioritato": "10",
        })
        svc.create({
            "titolo": "Write report",
            "titolo_norm": "write report",
            "prioritato": "20",
        })
        results, fuzzy = svc.search_todo(query="read")
        assert len(results) >= 1
        assert results[0]["titolo"] == "Read a book"

    def test_search_by_status(self, svc):
        """Search by status."""
        svc.create({
            "titolo": "Open task",
            "titolo_norm": "open task",
            "stato": "malfermita",
        })
        svc.create({
            "titolo": "Done task",
            "titolo_norm": "done task",
            "stato": "farita",
        })
        results, _ = svc.search_todo(stato="farita")
        assert len(results) == 1
        assert results[0]["titolo"] == "Done task"

    def test_search_by_label(self, svc, etikedo_svc):
        """Search by label."""
        lbl = etikedo_svc.create({"teksto": "filtro", "teksto_norm": "filtro"})
        svc.create({
            "titolo": "Filtered",
            "titolo_norm": "filtered",
            "etikedo": [lbl["uuid"]],
        })
        svc.create({
            "titolo": "Unfiltered",
            "titolo_norm": "unfiltered",
        })
        results, _ = svc.search_todo(etikedo=[lbl["uuid"]])
        assert len(results) == 1
        assert results[0]["titolo"] == "Filtered"

    def test_search_priority_range(self, svc):
        """Search by priority range."""
        svc.create({
            "titolo": "Low",
            "titolo_norm": "low",
            "prioritato": "10",
        })
        svc.create({
            "titolo": "High",
            "titolo_norm": "high",
            "prioritato": "90",
        })
        results, _ = svc.search_todo(
            prioritato_min=50.0, prioritato_max=100.0
        )
        assert len(results) == 1
        assert results[0]["titolo"] == "High"


# ──────────────────────────────────────────────────────────────────────────────
# CLI tests
# ──────────────────────────────────────────────────────────────────────────────


class TestTodoCLI:
    """Tests for todo CLI commands via CliRunner."""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, tmp_path):
        """Patch data dir and reset singletons."""
        import A_organizi.data.storage as storage_module

        monkeypatch.setattr(storage_module, "_DATA_DIR", tmp_path)
        monkeypatch.setattr(storage_module, "_DB_FILE", tmp_path / "organizi.db")

        monkeypatch.setattr("A_organizi.service.todo._todo_service", None)
        monkeypatch.setattr("A_organizi.service.etikedo._etikedo_service", None)

    def test_aldoni(self):
        """Create a task via CLI."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["todo", "aldoni", "Testa tasko", "-P", "42", "-s", "malfermita"],
        )
        assert result.exit_code == 0, result.output
        assert "Aldonis todo" in result.output

    def test_aldoni_with_formula(self):
        """Create task with formula priority."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "todo", "aldoni", "Formula tasko",
                "-P", "min(20 + 2 * D, 70)",
            ],
        )
        assert result.exit_code == 0, result.output

    def test_aldoni_with_label(self):
        """Create task with label."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        runner.invoke(app, ["etikedo", "aldoni", "grava"])
        result = runner.invoke(
            app, ["todo", "aldoni", "Tasko kun etikedo", "-e", "grava"]
        )
        assert result.exit_code == 0, result.output

    def test_vidi(self):
        """View a task."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        runner.invoke(app, ["todo", "aldoni", "Videbla tasko", "-P", "10"])
        result = runner.invoke(app, ["todo", "vidi", "Videbla tasko"])
        assert result.exit_code == 0, result.output
        assert "uuid:" in result.output

    def test_vidi_not_found(self):
        """View non-existent task returns error."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["todo", "vidi", "nonexistent"])
        assert result.exit_code != 0

    def test_modifi(self):
        """Modify a task."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        runner.invoke(app, ["todo", "aldoni", "Malnova"])
        result = runner.invoke(
            app, ["todo", "modifi", "Malnova", "--stato", "farita"]
        )
        assert result.exit_code == 0, result.output

    def test_forigi_confirmed(self):
        """Delete task with confirmation."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        runner.invoke(app, ["todo", "aldoni", "Forigota"])
        result = runner.invoke(
            app, ["todo", "forigi", "Forigota"], input="j\n"
        )
        assert result.exit_code == 0, result.output
        assert "Forigis todo" in result.output

    def test_forigi_cancelled(self):
        """Cancel task deletion."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        runner.invoke(app, ["todo", "aldoni", "Konservota"])
        result = runner.invoke(
            app, ["todo", "forigi", "Konservota"], input="N\n"
        )
        assert result.exit_code == 0
        assert "Nuligita" in result.output

    def test_serci(self):
        """Search tasks."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        runner.invoke(app, ["todo", "aldoni", "Unua", "-P", "10"])
        runner.invoke(app, ["todo", "aldoni", "Dua", "-P", "20"])
        result = runner.invoke(app, ["todo", "serci"])
        assert result.exit_code == 0, result.output

    def test_serci_filtered(self):
        """Search with text filter."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        runner.invoke(app, ["todo", "aldoni", "Speciala raporto"])
        result = runner.invoke(app, ["todo", "serci", "speciala"])
        assert result.exit_code == 0, result.output

    def test_serci_by_status(self):
        """Search by status."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        runner.invoke(app, ["todo", "aldoni", "Farenda", "-s", "malfermita"])
        runner.invoke(app, ["todo", "aldoni", "Farita", "-s", "farita"])
        result = runner.invoke(app, ["todo", "serci", "-s", "farita"])
        assert result.exit_code == 0, result.output
        assert "Farita" in result.output

    def test_serci_priority_range(self):
        """Search by priority range."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        runner.invoke(app, ["todo", "aldoni", "Malgranda", "-P", "10"])
        runner.invoke(app, ["todo", "aldoni", "Granda", "-P", "90"])
        result = runner.invoke(
            app, ["todo", "serci", "-P", "50,100"]
        )
        assert result.exit_code == 0, result.output
        assert "Granda" in result.output

    def test_help_shows_commands(self):
        """Verify help lists todo subcommands."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["todo", "--help"])
        assert result.exit_code == 0
        assert "aldoni" in result.output
        assert "vidi" in result.output
        assert "modifi" in result.output
        assert "forigi" in result.output
        assert "serci" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
