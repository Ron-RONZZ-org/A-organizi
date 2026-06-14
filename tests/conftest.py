"""Test isolation for A-organizi — prevents writes to real database."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolate_organizi(monkeypatch, tmp_path):
    """Isolate database to tmp_path to prevent real data pollution."""
    import A_organizi.data.storage as storage_module
    import A_organizi.service.kalendaro as kalendaro_module

    # Reset all singletons to force fresh connections on each test
    storage_module._db_instance = None
    kalendaro_module._evento_service = None
    kalendaro_module._kalendaro_service = None

    # Redirect ALL A-core paths to tmp_path (prevents LinksDB etc. hitting real ~/.local/share/A/)
    monkeypatch.setenv("A_DIR", str(tmp_path))
