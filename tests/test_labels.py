"""Tests for A-organizi label utilities, service, and CLI."""

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
def mock_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Create a temporary database for label tests."""
    import A_organizi.data.storage as storage_module


    # Use get_db() after patching
    return storage_module.get_db()


# ──────────────────────────────────────────────────────────────────────────────
# Utility tests (pure functions, no DB)
# ──────────────────────────────────────────────────────────────────────────────


class TestParseLabelBlob:
    """Tests for parse_label_blob."""

    def test_empty(self):
        from A_organizi.utils.labels import parse_label_blob

        assert parse_label_blob(None) == []
        assert parse_label_blob("") == []

    def test_single_pair(self):
        from A_organizi.utils.labels import parse_label_blob

        result = parse_label_blob("abc123:urgxa")
        assert result == [("abc123", "urgxa")]

    def test_multiple_pairs(self):
        from A_organizi.utils.labels import parse_label_blob

        result = parse_label_blob("abc123:urgxa|def456:persona")
        assert result == [("abc123", "urgxa"), ("def456", "persona")]

    def test_trailing_pipe(self):
        from A_organizi.utils.labels import parse_label_blob

        result = parse_label_blob("abc123:urgxa|")
        assert result == [("abc123", "urgxa")]


class TestRenderLabelPairs:
    """Tests for render_label_pairs."""

    def test_empty(self):
        from A_organizi.utils.labels import render_label_pairs

        assert render_label_pairs([]) == "-"

    def test_single(self):
        from A_organizi.utils.labels import render_label_pairs

        assert render_label_pairs([("uuid", "urgxa")]) == "urgxa"

    def test_multiple(self):
        from A_organizi.utils.labels import render_label_pairs

        result = render_label_pairs([("u1", "urgxa"), ("u2", "persona")])
        assert result == "urgxa, persona"


class TestMarkdownLinkHelpers:
    """Tests for markdown link normalization and rendering."""

    def test_normalize_simple(self):
        from A_organizi.utils.labels import normalize_markdown_links

        result = normalize_markdown_links("[Temo](ec#abc123)")
        assert "[Temo](ec#abc123)" in result

    def test_normalize_no_links(self):
        from A_organizi.utils.labels import normalize_markdown_links

        assert normalize_markdown_links("plain text") == "plain text"

    def test_render_plain_no_ref(self):
        from A_organizi.utils.labels import render_markdown_links_plain

        result = render_markdown_links_plain("[Temo](ec#abc123)")
        assert "Temo" in result

    def test_render_plain_with_ref(self):
        from A_organizi.utils.labels import render_markdown_links_plain

        result = render_markdown_links_plain("[Temo](ec#abc123)", show_ref=True)
        assert "Temo" in result
        assert "ec#" in result

    def test_render_plain_vt_link(self):
        from A_organizi.utils.labels import render_markdown_links_plain

        result = render_markdown_links_plain("[Vorto](vt#def456)")
        assert "Vorto" in result


class TestFuzzyMatches:
    """Tests for fuzzy matching."""

    def test_exact_match(self):
        from A_organizi.utils.labels import fuzzy_matches

        items = [{"uuid": "1", "name": "urgxa"}, {"uuid": "2", "name": "persona"}]
        result = fuzzy_matches(items, "urgxa", text_getter=lambda x: x["name"])
        assert len(result) == 1
        assert result[0]["uuid"] == "1"

    def test_no_match_below_threshold(self):
        from A_organizi.utils.labels import fuzzy_matches

        items = [{"uuid": "1", "name": "urgxa"}]
        result = fuzzy_matches(items, "zzzzz", text_getter=lambda x: x["name"])
        assert result == []


class TestSearchItems:
    """Tests for search_items."""

    def test_substring_match(self):
        from A_organizi.utils.labels import search_items

        items = [{"uuid": "1", "name": "urgxa"}, {"uuid": "2", "name": "persona"}]
        results, fuzzy = search_items(items, "urg", text_getter=lambda x: x["name"])
        assert len(results) == 1
        assert not fuzzy

    def test_fuzzy_fallback(self):
        from A_organizi.utils.labels import search_items

        items = [{"uuid": "1", "name": "urgxa"}]
        results, fuzzy = search_items(items, "urgx", text_getter=lambda x: x["name"])
        # Should match via substring or fuzzy
        assert len(results) >= 1


class TestResolveReference:
    """Tests for resolve_reference."""

    def test_by_uuid(self):
        from A_organizi.utils.labels import resolve_reference

        items = [
            {"uuid": "abc12345-1111-2222-3333-444444444444", "name": "urgxa"},
        ]
        result = resolve_reference(
            items,
            "abc12345-1111-2222-3333-444444444444",
            text_getter=lambda x: x["name"],
            kind_label="test",
            allow_fuzzy=False,
            interactive=False,
        )
        assert result is not None
        assert result["name"] == "urgxa"

    def test_by_uuid_prefix(self):
        from A_organizi.utils.labels import resolve_reference

        items = [
            {"uuid": "abc12345-1111-2222-3333-444444444444", "name": "urgxa"},
            {"uuid": "def67890-1111-2222-3333-444444444444", "name": "persona"},
        ]
        result = resolve_reference(
            items,
            "abc12345",
            text_getter=lambda x: x["name"],
            kind_label="test",
            allow_fuzzy=False,
            interactive=False,
        )
        assert result is not None
        assert result["name"] == "urgxa"

    def test_by_text_exact(self):
        from A_organizi.utils.labels import resolve_reference

        items = [
            {"uuid": "abc12345-1111-2222-3333-444444444444", "name": "urgxa"},
            {"uuid": "def67890-1111-2222-3333-444444444444", "name": "persona"},
        ]
        result = resolve_reference(
            items,
            "urgxa",
            text_getter=lambda x: x["name"],
            kind_label="test",
            allow_fuzzy=False,
            interactive=False,
        )
        assert result is not None
        assert result["uuid"] == "abc12345-1111-2222-3333-444444444444"

    def test_not_found(self):
        from A_organizi.utils.labels import resolve_reference

        items = [{"uuid": "abc12345-1111-2222-3333-444444444444", "name": "urgxa"}]
        result = resolve_reference(
            items,
            "nonexistent",
            text_getter=lambda x: x["name"],
            kind_label="test",
            allow_fuzzy=False,
            interactive=False,
        )
        assert result is None


# ──────────────────────────────────────────────────────────────────────────────
# EtikedoService tests
# ──────────────────────────────────────────────────────────────────────────────


class TestEtikedoService:
    """Tests for EtikedoService."""

    def test_create_and_get(self, mock_db):
        from A.core.service import CRUDService

        svc = CRUDService(mock_db, "etikedoj")
        data = svc.create({"teksto": "urgxa", "teksto_norm": "urgxa"})
        assert data["teksto"] == "urgxa"
        retrieved = svc.get(data["uuid"])
        assert retrieved is not None
        assert retrieved["teksto"] == "urgxa"

    def test_create_rejects_duplicate_teksto_norm(self, mock_db):
        from A.core.service import CRUDService

        svc = CRUDService(mock_db, "etikedoj")
        svc.create({"teksto": "urgxa", "teksto_norm": "urgxa"})
        with pytest.raises(Exception):
            svc.create({"teksto": "Urgxa", "teksto_norm": "urgxa"})

    def test_list_labels(self, mock_db):
        from A_organizi.utils.labels import list_etikedoj

        from A.core.service import CRUDService

        svc = CRUDService(mock_db, "etikedoj")
        svc.create({"teksto": "a", "teksto_norm": "a"})
        svc.create({"teksto": "b", "teksto_norm": "b"})
        labels = list_etikedoj(mock_db)
        assert len(labels) == 2

    def test_etikedo_text_map(self, mock_db):
        from A_organizi.utils.labels import etikedo_text_map

        from A.core.service import CRUDService

        svc = CRUDService(mock_db, "etikedoj")
        d1 = svc.create({"teksto": "urgxa", "teksto_norm": "urgxa"})
        d2 = svc.create({"teksto": "persona", "teksto_norm": "persona"})
        mapping = etikedo_text_map(mock_db)
        assert mapping[d1["uuid"]] == "urgxa"
        assert mapping[d2["uuid"]] == "persona"


# ──────────────────────────────────────────────────────────────────────────────
# Service layer tests
# ──────────────────────────────────────────────────────────────────────────────


class TestServiceLayer:
    """Tests for service singletons."""

    def test_get_etikedo_service(self, monkeypatch, tmp_path):
        """Verify etikedo service is an EtikedoService instance."""
        import A_organizi.data.storage as storage_module

        
        from A_organizi.service import get_etikedo_service, EtikedoService

        svc = get_etikedo_service()
        assert isinstance(svc, EtikedoService)

    def test_etikedo_service_is_singleton(self, monkeypatch, tmp_path):
        """Verify get_etikedo_service returns the same instance."""
        import A_organizi.data.storage as storage_module

        
        from A_organizi.service import get_etikedo_service

        s1 = get_etikedo_service()
        s2 = get_etikedo_service()
        assert s1 is s2


# ──────────────────────────────────────────────────────────────────────────────
# CLI tests
# ──────────────────────────────────────────────────────────────────────────────


class TestEtikedoCLI:
    """Tests for etikedoj CLI commands via CliRunner."""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, tmp_path):
        """Patch data dir and reset service singletons."""
        import A_organizi.data.storage as storage_module

        
        # Reset service singletons for each test
        monkeypatch.setattr("A_organizi.service.etikedo._etikedo_service", None)

    def test_aldoni(self):
        """Create a label via CLI."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["etikedo", "aldoni", "urgxa"])
        assert result.exit_code == 0, result.output
        assert "Aldonis etikedon" in result.output

    def test_aldoni_with_color(self):
        """Create a label with color option."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        result = runner.invoke(
            app, ["etikedo", "aldoni", "grava", "-k", "#ff0000"]
        )
        assert result.exit_code == 0, result.output

    def test_vidi_by_text(self):
        """View a label by its text."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        runner.invoke(app, ["etikedo", "aldoni", "persona"])
        result = runner.invoke(app, ["etikedo", "vidi", "persona"])
        assert result.exit_code == 0, result.output
        assert "uuid:" in result.output
        assert "teksto:" in result.output

    def test_vidi_not_found(self):
        """View non-existent label returns error."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["etikedo", "vidi", "nonexistent"])
        assert result.exit_code != 0

    def test_modifi(self):
        """Modify a label's text."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        runner.invoke(app, ["etikedo", "aldoni", "old"])
        result = runner.invoke(app, ["etikedo", "modifi", "old", "new"])
        assert result.exit_code == 0, result.output
        assert "Modifis etikedon" in result.output

    def test_forigi_confirmed(self):
        """Delete a label with confirmation."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        runner.invoke(app, ["etikedo", "aldoni", "forigota"])
        result = runner.invoke(app, ["etikedo", "forigi", "forigota"], input="j\n")
        assert result.exit_code == 0, result.output
        assert "Forigis etikedon" in result.output

    def test_forigi_cancelled(self):
        """Cancel label deletion."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        runner.invoke(app, ["etikedo", "aldoni", "konservota"])
        result = runner.invoke(
            app, ["etikedo", "forigi", "konservota"], input="N\n"
        )
        assert result.exit_code == 0
        assert "Nuligita" in result.output

    def test_serci_all(self):
        """List all labels."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        runner.invoke(app, ["etikedo", "aldoni", "urgxa"])
        runner.invoke(app, ["etikedo", "aldoni", "persona"])
        result = runner.invoke(app, ["etikedo", "serci"])
        assert result.exit_code == 0, result.output
        assert "urgxa" in result.output
        assert "persona" in result.output

    def test_serci_filter(self):
        """Search labels by text."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        runner.invoke(app, ["etikedo", "aldoni", "urgxa"])
        runner.invoke(app, ["etikedo", "aldoni", "persona"])
        result = runner.invoke(app, ["etikedo", "serci", "urg"])
        assert result.exit_code == 0, result.output
        assert "urgxa" in result.output

    def test_serci_with_limit(self):
        """Search with limit option."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        runner.invoke(app, ["etikedo", "aldoni", "a"])
        result = runner.invoke(app, ["etikedo", "serci", "--limo", "10"])
        assert result.exit_code == 0, result.output

    def test_help_shows_commands(self):
        """Verify help text lists etikedo subcommands."""
        from typer.testing import CliRunner
        from A_organizi.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["etikedo", "--help"])
        assert result.exit_code == 0
        assert "aldoni" in result.output
        assert "vidi" in result.output
        assert "modifi" in result.output
        assert "forigi" in result.output
        assert "serci" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
