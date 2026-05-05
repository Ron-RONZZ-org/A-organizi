"""Test isolation for A-organizi — prevents writes to real database."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolate_organizi(monkeypatch, tmp_path):
    """Isolate database to tmp_path to prevent real data pollution."""
    import A_organizi.data.storage as storage_module

    monkeypatch.setattr(storage_module, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(storage_module, "_DB_FILE", tmp_path / "organizi.db")
