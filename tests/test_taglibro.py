"""Tests for taglibro (journal) service and CLI."""

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


    # Reset service singletons
    import A_organizi.service as svc_module

    monkeypatch.setattr("A_organizi.service.taglibro._taglibro_service", None)
    monkeypatch.setattr("A_organizi.service.etikedo._etikedo_service", None)


@pytest.fixture
def svc(setup):
    """Get a fresh TaglibroService for testing."""
    from A_organizi.service import get_taglibro_service

    return get_taglibro_service()


@pytest.fixture
def etikedo_svc(setup):
    """Get a fresh EtikedoService for testing."""
    from A_organizi.service import get_etikedo_service

    return get_etikedo_service()


# ──────────────────────────────────────────────────────────────────────────────
# Service tests
# ──────────────────────────────────────────────────────────────────────────────


class TestTaglibroService:
    """Tests for TaglibroService."""

    def test_create_and_get(self, svc):
        """Create a journal entry and retrieve it."""
        data = svc.create({
            "titolo": "Test Entry",
            "titolo_norm": "test entry",
            "priskribo": "Description",
            "priskribo_norm": "description",
            "tempo": "2026-04-21T09:15:00+00:00",
        })
        assert "uuid" in data
        assert data["titolo"] == "Test Entry"
        assert data["tempo"] == "2026-04-21T09:15:00+00:00"

        retrieved = svc.get(data["uuid"])
        assert retrieved is not None
        assert retrieved["titolo"] == "Test Entry"

    def test_create_with_labels(self, svc, etikedo_svc):
        """Create entry with label assignments."""
        lbl1 = etikedo_svc.create({"teksto": "urgxa", "teksto_norm": "urgxa"})
        lbl2 = etikedo_svc.create({"teksto": "persona", "teksto_norm": "persona"})

        data = svc.create({
            "titolo": "Labeled Entry",
            "titolo_norm": "labeled entry",
            "tempo": "2026-04-21T10:00:00+00:00",
            "etikedo": [lbl1["uuid"], lbl2["uuid"]],
        })
        assert len(data.get("etikedoj", [])) == 2

        # Verify via get_with_labels
        with_labels = svc.get_with_labels(data["uuid"])
        assert with_labels is not None
        assert len(with_labels.get("etikedoj", [])) == 2

    def test_set_labels(self, svc, etikedo_svc):
        """Replace labels on an existing entry."""
        entry = svc.create({
            "titolo": "Test",
            "titolo_norm": "test",
            "tempo": "2026-04-21T10:00:00+00:00",
        })
        lbl = etikedo_svc.create({"teksto": "grava", "teksto_norm": "grava"})
        svc.set_labels(entry["uuid"], [lbl["uuid"]])
        labels = svc.get_labels(entry["uuid"])
        assert len(labels) == 1
        assert labels[0][1] == "grava"

    def test_update_labels(self, svc, etikedo_svc):
        """Update entry and replace labels."""
        lbl1 = etikedo_svc.create({"teksto": "a", "teksto_norm": "a"})
        entry = svc.create({
            "titolo": "Original",
            "titolo_norm": "original",
            "tempo": "2026-04-21T10:00:00+00:00",
            "etikedo": [lbl1["uuid"]],
        })
        lbl2 = etikedo_svc.create({"teksto": "b", "teksto_norm": "b"})
        updated = svc.update(entry["uuid"], {
            "titolo": "Updated",
            "titolo_norm": "updated",
            "etikedo": [lbl2["uuid"]],
        })
        assert updated["titolo"] == "Updated"
        # Should now have only label b
        uuids = {uid for uid, _ in updated.get("etikedoj", [])}
        assert lbl2["uuid"] in uuids
        assert lbl1["uuid"] not in uuids

    def test_list_with_labels(self, svc, etikedo_svc):
        """List entries with labels attached."""
        lbl = etikedo_svc.create({"teksto": "commo", "teksto_norm": "commo"})
        svc.create({
            "titolo": "E1", "titolo_norm": "e1",
            "tempo": "2026-04-21T10:00:00+00:00",
            "etikedo": [lbl["uuid"]],
        })
        svc.create({
            "titolo": "E2", "titolo_norm": "e2",
            "tempo": "2026-04-22T10:00:00+00:00",
        })
        entries = svc.list_with_labels()
        assert len(entries) >= 2
        # E1 should have 1 label
        for e in entries:
            if e["titolo"] == "E1":
                assert len(e.get("etikedoj", [])) == 1

    def test_search_by_text(self, svc):
        """Search entries by text query."""
        svc.create({
            "titolo": "Hodiaŭ mi lernis", "titolo_norm": "hodiau mi lernis",
            "tempo": "2026-04-21T10:00:00+00:00",
        })
        svc.create({
            "titolo": "Alia noto", "titolo_norm": "alia noto",
            "tempo": "2026-04-22T10:00:00+00:00",
        })
        results, fuzzy = svc.search_taglibro(query="hodiau")
        assert len(results) >= 1
        assert results[0]["titolo"] == "Hodiaŭ mi lernis"

    def test_search_by_title_filter(self, svc):
        """Search with title filter."""
        svc.create({
            "titolo": "Ideo pri projekto", "titolo_norm": "ideo pri projekto",
            "tempo": "2026-04-21T10:00:00+00:00",
        })
        results, _ = svc.search_taglibro(titolo="ideo")
        assert len(results) >= 1

    def test_search_by_label(self, svc, etikedo_svc):
        """Search with label filter."""
        lbl = etikedo_svc.create({"teksto": "filtr", "teksto_norm": "filtr"})
        svc.create({
            "titolo": "Match", "titolo_norm": "match",
            "tempo": "2026-04-21T10:00:00+00:00",
            "etikedo": [lbl["uuid"]],
        })
        svc.create({
            "titolo": "No match", "titolo_norm": "no match",
            "tempo": "2026-04-22T10:00:00+00:00",
        })
        results, _ = svc.search_taglibro(etikedo=[lbl["uuid"]])
        assert len(results) == 1
        assert results[0]["titolo"] == "Match"

    def test_search_date_range(self, svc):
        """Search with date range filter."""
        svc.create({
            "titolo": "Old", "titolo_norm": "old",
            "tempo": "2026-04-01T10:00:00+00:00",
        })
        svc.create({
            "titolo": "Middle", "titolo_norm": "middle",
            "tempo": "2026-04-15T10:00:00+00:00",
        })
        svc.create({
            "titolo": "New", "titolo_norm": "new",
            "tempo": "2026-04-30T10:00:00+00:00",
        })
        results, _ = svc.search_taglibro(
            de_tempo="2026-04-10T00:00:00+00:00",
            gxis_tempo="2026-04-20T00:00:00+00:00",
        )
        assert len(results) == 1
        assert results[0]["titolo"] == "Middle"

    def test_combined_search(self, svc, etikedo_svc):
        """Search with multiple filters combined."""
        lbl = etikedo_svc.create({"teksto": "spec", "teksto_norm": "spec"})
        svc.create({
            "titolo": "Special Day", "titolo_norm": "special day",
            "priskribo": "Something happened", "priskribo_norm": "something happened",
            "tempo": "2026-04-21T10:00:00+00:00",
            "etikedo": [lbl["uuid"]],
        })
        svc.create({
            "titolo": "Other Day", "titolo_norm": "other day",
            "tempo": "2026-04-22T10:00:00+00:00",
        })
        results, _ = svc.search_taglibro(
            query="special",
            etikedo=[lbl["uuid"]],
            de_tempo="2026-04-01T00:00:00+00:00",
        )
        assert len(results) == 1


# ──────────────────────────────────────────────────────────────────────────────
# CLI tests
# ──────────────────────────────────────────────────────────────────────────────


class TestTaglibroCLI:
    """Tests for taglibro CLI commands via CliRunner."""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, tmp_path):
        """Patch data dir and reset singletons."""
        import A_organizi.data.storage as storage_module

        
        import A_organizi.service as svc_module

        monkeypatch.setattr("A_organizi.service.taglibro._taglibro_service", None)
        monkeypatch.setattr("A_organizi.service.etikedo._etikedo_service", None)

    def test_aldoni(self):
        """Create a journal entry via CLI."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "taglibro", "aldoni", "Hodiaŭ",
                "-p", "Bona tago",
                "-t", "20260421_0915",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Aldonis taglibran eniron" in result.output

    def test_aldoni_with_label(self):
        """Create entry with label via CLI."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        # Create label first
        runner.invoke(app, ["etikedo", "aldoni", "persona"])
        # Create entry with label
        result = runner.invoke(
            app,
            [
                "taglibro", "aldoni", "Noto",
                "-e", "persona",
            ],
        )
        assert result.exit_code == 0, result.output

    def test_vidi(self):
        """View a journal entry."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        runner.invoke(app, ["taglibro", "aldoni", "Videbla"])
        result = runner.invoke(app, ["taglibro", "vidi", "Videbla"])
        assert result.exit_code == 0, result.output
        assert "uuid:" in result.output
        assert "Videbla" in result.output

    def test_vidi_not_found(self):
        """View non-existent entry returns error."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["taglibro", "vidi", "nonexistent"])
        assert result.exit_code != 0

    def test_modifi(self):
        """Modify a journal entry."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        runner.invoke(app, ["taglibro", "aldoni", "Malnova"])
        result = runner.invoke(
            app,
            ["taglibro", "modifi", "Malnova", "--titolo", "Nova"],
        )
        assert result.exit_code == 0, result.output
        assert "Modifis taglibro-eniron" in result.output

    def test_forigi_confirmed(self):
        """Delete entry with confirmation."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        runner.invoke(app, ["taglibro", "aldoni", "Forigota"])
        result = runner.invoke(
            app, ["taglibro", "forigi", "Forigota"], input="j\n"
        )
        assert result.exit_code == 0, result.output
        assert "Forigis taglibro-eniron" in result.output

    def test_forigi_cancelled(self):
        """Cancel entry deletion."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        runner.invoke(app, ["taglibro", "aldoni", "Konservota"])
        result = runner.invoke(
            app, ["taglibro", "forigi", "Konservota"], input="N\n"
        )
        assert result.exit_code == 0
        assert "Nuligita" in result.output

    def test_serci(self):
        """Search entries."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        runner.invoke(app, ["taglibro", "aldoni", "Unua ideo"])
        runner.invoke(app, ["taglibro", "aldoni", "Dua noto"])
        result = runner.invoke(app, ["taglibro", "serci"])
        assert result.exit_code == 0, result.output
        assert "Unua ideo" in result.output

    def test_serci_filtered(self):
        """Search with text filter."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        runner.invoke(app, ["taglibro", "aldoni", "Speciala tago"])
        runner.invoke(app, ["taglibro", "aldoni", "Normala tago"])
        result = runner.invoke(app, ["taglibro", "serci", "speciala"])
        assert result.exit_code == 0, result.output
        assert "Speciala tago" in result.output

    def test_serci_date_range(self):
        """Search with date range."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        runner.invoke(
            app,
            ["taglibro", "aldoni", "Old", "-t", "20260401_1000"],
        )
        runner.invoke(
            app,
            ["taglibro", "aldoni", "New", "-t", "20260430_1000"],
        )
        result = runner.invoke(
            app,
            ["taglibro", "serci", "--de", "20260410", "--gis", "20260420"],
        )
        assert result.exit_code == 0, result.output
        # Old and new should be outside range, result may be empty — should not crash
        assert result.exit_code == 0

    def test_help_shows_commands(self):
        """Verify help lists taglibro subcommands."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["taglibro", "--help"])
        assert result.exit_code == 0
        assert "aldoni" in result.output
        assert "vidi" in result.output
        assert "modifi" in result.output
        assert "forigi" in result.output
        assert "serci" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
