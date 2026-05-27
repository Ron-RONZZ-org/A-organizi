"""Tests for A-organizi storage and service layers."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add src directories to path for imports
_TEST_DIR = Path(__file__).parent
sys.path.insert(0, str(_TEST_DIR.parent / "src"))
sys.path.insert(0, str(_TEST_DIR.parent.parent / "A-core" / "src"))


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Mock data directory to temporary path."""
    import A_organizi.data.storage as storage_module

    data_dir = tmp_path / ".local" / "share" / "A"
    monkeypatch.setattr(storage_module, "_DATA_DIR", data_dir)
    monkeypatch.setattr(storage_module, "_DB_FILE", data_dir / "organizi.db")
    return data_dir


# ──────────────────────────────────────────────────────────────────────────────
# Storage schema tests
# ──────────────────────────────────────────────────────────────────────────────


class TestSchema:
    """Tests for database schema creation."""

    def test_get_db_creates_all_tables(self, mock_data_dir):
        """Verify all required tables are created."""
        from A_organizi.data.storage import get_db

        db = get_db()

        tables = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        table_names = {r["name"] for r in tables}

        expected = {
            "kalendaroj",
            "eventoj",
            "todoj",
            "etikedoj",
            "todoj_etikedo",
            "taglibro",
            "taglibro_etikedo",
        }
        assert expected.issubset(table_names), (
            f"Missing tables: {expected - table_names}"
        )

    def test_get_db_creates_indexes(self, mock_data_dir):
        """Verify all required indexes are created."""
        from A_organizi.data.storage import get_db

        db = get_db()

        indexes = db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
        )
        index_names = {r["name"] for r in indexes}

        expected = {
            "idx_eventoj_kalendaro",
            "idx_eventoj_komenco",
            "idx_todoj_stato",
            "idx_todoj_titolo_norm",
            "idx_todoj_priskribo_norm",
            "idx_taglibro_tempo",
            "idx_taglibro_titolo_norm",
            "idx_taglibro_priskribo_norm",
            "idx_etikedoj_teksto_norm",
        }
        missing = expected - index_names
        assert not missing, f"Missing indexes: {missing}"

    def test_kalendaroj_schema(self, mock_data_dir):
        """Verify kalendaroj table columns."""
        from A_organizi.data.storage import get_db

        db = get_db()
        cols = {r["name"] for r in db.execute("PRAGMA table_info(kalendaroj)")}
        assert {"uuid", "url", "username", "remote", "kreita_je", "modifita_je"}.issubset(cols)

    def test_eventoj_schema(self, mock_data_dir):
        """Verify eventoj table columns."""
        from A_organizi.data.storage import get_db

        db = get_db()
        cols = {r["name"] for r in db.execute("PRAGMA table_info(eventoj)")}
        expected = {
            "uuid", "kalendaro_uuid", "titolo", "komenco", "fino",
            "kategorio", "loko", "ripeto", "partoprenantoj", "priskribo",
            "kreita_je", "modifita_je",
        }
        assert expected.issubset(cols)

    def test_todoj_schema(self, mock_data_dir):
        """Verify todoj table has correct columns (stato, not estado)."""
        from A_organizi.data.storage import get_db

        db = get_db()
        cols = {r["name"] for r in db.execute("PRAGMA table_info(todoj)")}
        expected = {
            "uuid", "titolo", "titolo_norm", "priskribo", "priskribo_norm",
            "prioritato", "stato", "kreita_je", "modifita_je",
        }
        assert expected.issubset(cols), f"Missing columns: {expected - cols}"
        # Verify prioritato is TEXT (formula string), not REAL
        info = {r["name"]: r for r in db.execute("PRAGMA table_info(todoj)")}
        assert info["prioritato"]["type"].upper() == "TEXT", (
            f"prioritato should be TEXT, got {info['prioritato']['type']}"
        )

    def test_etikedoj_schema_has_teksto_norm(self, mock_data_dir):
        """Verify etikedoj table has teksto_norm UNIQUE column."""
        from A_organizi.data.storage import get_db

        db = get_db()
        cols = {r["name"] for r in db.execute("PRAGMA table_info(etikedoj)")}
        assert "teksto_norm" in cols, "Missing teksto_norm column"

    def test_taglibro_schema(self, mock_data_dir):
        """Verify taglibro table has uuid PK (not dato)."""
        from A_organizi.data.storage import get_db

        db = get_db()
        cols = {r["name"]: r for r in db.execute("PRAGMA table_info(taglibro)")}
        expected = {
            "uuid", "titolo", "titolo_norm", "priskribo", "priskribo_norm",
            "tempo", "kreita_je", "modifita_je",
        }
        assert expected.issubset(cols.keys()), f"Missing columns: {expected - set(cols.keys())}"
        # Verify uuid is PK
        assert cols["uuid"]["pk"] == 1, "uuid should be PRIMARY KEY"
        # Verify dato does not exist
        assert "dato" not in cols, "dato column should not exist (was replaced by uuid PK)"

    def test_junction_tables_exist(self, mock_data_dir):
        """Verify both junction tables exist."""
        from A_organizi.data.storage import get_db

        db = get_db()
        tables = {r["name"] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        assert "todoj_etikedo" in tables
        assert "taglibro_etikedo" in tables

    def test_ensure_dirs_creates_directory(self, mock_data_dir):
        """Verify ensure_dirs creates the data directory."""
        from A_organizi.data.storage import ensure_dirs

        ensure_dirs()
        assert mock_data_dir.exists()
        assert mock_data_dir.is_dir()

    def test_wal_mode_enabled(self, mock_data_dir):
        """Verify WAL journal mode is active."""
        from A_organizi.data.storage import get_db

        db = get_db()
        result = db.execute_one("PRAGMA journal_mode")
        assert result is not None
        assert "wal" in str(result.get("journal_mode", "")).lower()

    def test_get_db_is_singleton(self, mock_data_dir):
        """Verify get_db() returns the same instance on repeated calls."""
        from A_organizi.data.storage import get_db

        db1 = get_db()
        db2 = get_db()
        assert db1 is db2


# ──────────────────────────────────────────────────────────────────────────────
# CRUDService integration tests
# ──────────────────────────────────────────────────────────────────────────────


class TestCRUDService:
    """Tests for CRUDService integration with organizi tables."""

    @pytest.fixture(autouse=True)
    def setup_db(self, mock_data_dir):
        """Initialize database before each test."""
        from A_organizi.data.storage import get_db

        self.db = get_db()

    def test_kalendaroj_create_and_get(self):
        """Create a calendar entry and retrieve it."""
        from A.core.service import CRUDService

        svc = CRUDService(self.db, "kalendaroj")
        data = svc.create({
            "url": "https://example.com/cal.ics",
            "username": "alice",
            "remote": 1,
        })
        assert "uuid" in data
        assert data["url"] == "https://example.com/cal.ics"
        assert data["username"] == "alice"

        retrieved = svc.get(data["uuid"])
        assert retrieved is not None
        assert retrieved["url"] == data["url"]
        assert retrieved["uuid"] == data["uuid"]

    def test_todoj_create_and_update(self):
        """Create and update a task entry."""
        from A.core.service import CRUDService

        svc = CRUDService(self.db, "todoj")
        data = svc.create({
            "titolo": "Legi libron",
            "titolo_norm": "legi libron",
            "prioritato": "min(20+2*D,70)",
            "stato": "malfermita",
        })
        uuid = data["uuid"]
        assert data["titolo"] == "Legi libron"
        assert data["prioritato"] == "min(20+2*D,70)"
        assert data["stato"] == "malfermita"

        updated = svc.update(uuid, {"stato": "farita", "prioritato": "0"})
        retrieved = svc.get(uuid)
        assert retrieved["stato"] == "farita"
        assert retrieved["prioritato"] == "0"

    def test_todoj_delete_soft(self):
        """Soft-delete a task and verify it moves to trash."""
        from A.core.service import CRUDService

        svc = CRUDService(self.db, "todoj")
        data = svc.create({"titolo": "Task for delete", "titolo_norm": "task for delete"})
        uuid = data["uuid"]

        svc.delete(uuid, soft=True)
        # Should not be in main table
        assert svc.get(uuid) is None
        # Should be in trash table
        trash = svc.get_trash()
        uuids_in_trash = {e["uuid"] for e in trash}
        assert uuid in uuids_in_trash

    def test_todoj_restore_from_trash(self):
        """Restore a soft-deleted task."""
        from A.core.service import CRUDService

        svc = CRUDService(self.db, "todoj")
        data = svc.create({"titolo": "Restore me", "titolo_norm": "restore me"})
        uuid = data["uuid"]

        svc.delete(uuid, soft=True)
        restored = svc.restore(uuid)
        assert restored is not None
        assert restored["titolo"] == "Restore me"
        # Should be back in main table
        assert svc.get(uuid) is not None

    def test_taglibro_create_and_list(self):
        """Create journal entries and list them."""
        from A.core.service import CRUDService

        svc = CRUDService(self.db, "taglibro")
        svc.create({
            "titolo": "Taglibra eniro",
            "titolo_norm": "taglibra eniro",
            "tempo": "2026-04-21T09:15:00+00:00",
        })
        svc.create({
            "titolo": "Alia eniro",
            "titolo_norm": "alia eniro",
            "tempo": "2026-04-22T10:00:00+00:00",
        })
        entries = svc.list(order_by="tempo", desc=True)
        assert len(entries) >= 2

    def test_etikedoj_unique_teksto_norm(self):
        """Verify duplicate teksto_norm is rejected."""
        from A.core.service import CRUDService

        svc = CRUDService(self.db, "etikedoj")
        svc.create({
            "teksto": "Urgxa",
            "teksto_norm": "urgxa",
        })
        with pytest.raises(Exception):
            svc.create({
                "teksto": "urgxa",
                "teksto_norm": "urgxa",
            })

    def test_kalendaroj_list_and_delete(self):
        """List and hard-delete calendar entries."""
        from A.core.service import CRUDService

        svc = CRUDService(self.db, "kalendaroj")
        svc.create({"url": "https://cal1.com/ics", "username": "u1"})
        svc.create({"url": "https://cal2.com/ics", "username": "u2"})

        all_cals = svc.list()
        assert len(all_cals) >= 2

        # Hard delete one
        svc.delete(all_cals[0]["uuid"], soft=False)
        remaining = svc.list()
        assert len(remaining) == len(all_cals) - 1


# ──────────────────────────────────────────────────────────────────────────────
# Service layer tests
# ──────────────────────────────────────────────────────────────────────────────


class TestServiceLayer:
    """Tests for the singleton service layer."""

    def test_get_kalendaro_service(self, mock_data_dir):
        """Verify kalendaro service is a CRUDService instance."""
        from A_organizi.service import get_kalendaro_service

        svc = get_kalendaro_service()
        from A.core.service import CRUDService

        assert isinstance(svc, CRUDService)

    def test_get_todo_service(self, mock_data_dir):
        """Verify todo service is a CRUDService instance."""
        from A_organizi.service import get_todo_service

        svc = get_todo_service()
        from A.core.service import CRUDService

        assert isinstance(svc, CRUDService)

    def test_get_taglibro_service(self, mock_data_dir):
        """Verify taglibro service is a CRUDService instance."""
        from A_organizi.service import get_taglibro_service

        svc = get_taglibro_service()
        from A.core.service import CRUDService

        assert isinstance(svc, CRUDService)

    def test_services_are_singletons(self, mock_data_dir):
        """Verify each service returns the same instance on repeated calls."""
        from A_organizi.service import (
            get_kalendaro_service,
            get_todo_service,
            get_taglibro_service,
        )

        k1 = get_kalendaro_service()
        k2 = get_kalendaro_service()
        assert k1 is k2

        t1 = get_todo_service()
        t2 = get_todo_service()
        assert t1 is t2

        tg1 = get_taglibro_service()
        tg2 = get_taglibro_service()
        assert tg1 is tg2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
