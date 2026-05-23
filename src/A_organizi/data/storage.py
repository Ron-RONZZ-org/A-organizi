"""Organizi data layer - SQLite storage for kalendaro, todo, taglibro."""

from __future__ import annotations

from pathlib import Path

from A.core.paths import data_dir
from A.data.base import SQLiteDB, backup_db, health_check

_DATA_DIR: Path = data_dir()
_DB_FILE: Path = _DATA_DIR / "organizi.db"

# ──────────────────────────────────────────────────────────────────────────────
# Calendars (kalendaro)
# ──────────────────────────────────────────────────────────────────────────────

_CREATE_KALENDAROJ = """
CREATE TABLE IF NOT EXISTS kalendaroj (
    uuid TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    username TEXT NOT NULL DEFAULT '',
    remote INTEGER NOT NULL DEFAULT 1,
    kreita_je TEXT NOT NULL,
    modifita_je TEXT NOT NULL
);
"""

_CREATE_EVENTOJ = """
CREATE TABLE IF NOT EXISTS eventoj (
    uuid TEXT PRIMARY KEY,
    kalendaro_uuid TEXT NOT NULL,
    titolo TEXT NOT NULL DEFAULT '',
    komenco TEXT NOT NULL,
    fino TEXT NOT NULL,
    kategorio TEXT NOT NULL DEFAULT '',
    loko TEXT NOT NULL DEFAULT '',
    ripeto TEXT NOT NULL DEFAULT '',
    partoprenantoj TEXT NOT NULL DEFAULT '[]',
    priskribo TEXT NOT NULL DEFAULT '',
    kreita_je TEXT NOT NULL,
    modifita_je TEXT NOT NULL
);
"""

# ──────────────────────────────────────────────────────────────────────────────
# Tasks (todo)
# ──────────────────────────────────────────────────────────────────────────────

_CREATE_TODOJ = """
CREATE TABLE IF NOT EXISTS todoj (
    uuid TEXT PRIMARY KEY,
    titolo TEXT NOT NULL,
    titolo_norm TEXT NOT NULL,
    priskribo TEXT NOT NULL DEFAULT '',
    priskribo_norm TEXT NOT NULL DEFAULT '',
    prioritato TEXT NOT NULL DEFAULT '0',
    stato TEXT NOT NULL DEFAULT 'malfermita',
    kreita_je TEXT NOT NULL,
    modifita_je TEXT NOT NULL
);
"""

# ──────────────────────────────────────────────────────────────────────────────
# Shared labels (etikedoj)
# ──────────────────────────────────────────────────────────────────────────────

_CREATE_ETIKEDOJ = """
CREATE TABLE IF NOT EXISTS etikedoj (
    uuid TEXT PRIMARY KEY,
    teksto TEXT NOT NULL,
    teksto_norm TEXT NOT NULL UNIQUE,
    koloro TEXT NOT NULL DEFAULT '',
    kreita_je TEXT NOT NULL,
    modifita_je TEXT NOT NULL
);
"""

_CREATE_TODOJ_ETIKEDO = """
CREATE TABLE IF NOT EXISTS todoj_etikedo (
    todo_uuid TEXT NOT NULL,
    etikedo_uuid TEXT NOT NULL,
    PRIMARY KEY (todo_uuid, etikedo_uuid)
);
"""

# ──────────────────────────────────────────────────────────────────────────────
# Journal (taglibro)
# ──────────────────────────────────────────────────────────────────────────────

_CREATE_TAGLIBRO = """
CREATE TABLE IF NOT EXISTS taglibro (
    uuid TEXT PRIMARY KEY,
    titolo TEXT NOT NULL,
    titolo_norm TEXT NOT NULL,
    priskribo TEXT NOT NULL DEFAULT '',
    priskribo_norm TEXT NOT NULL DEFAULT '',
    tempo TEXT NOT NULL,
    kreita_je TEXT NOT NULL,
    modifita_je TEXT NOT NULL
);
"""

_CREATE_TAGLIBRO_ETIKEDO = """
CREATE TABLE IF NOT EXISTS taglibro_etikedo (
    taglibro_uuid TEXT NOT NULL,
    etikedo_uuid TEXT NOT NULL,
    PRIMARY KEY (taglibro_uuid, etikedo_uuid)
);
"""

# ──────────────────────────────────────────────────────────────────────────────
# Sync queue (CalDAV sync)
# ──────────────────────────────────────────────────────────────────────────────

_CREATE_SYNC_QUEUE = """
CREATE TABLE IF NOT EXISTS sync_queue (
    id TEXT PRIMARY KEY,
    calendar_uuid TEXT NOT NULL,
    operacio TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    stato TEXT NOT NULL DEFAULT 'pending',
    eraro TEXT NOT NULL DEFAULT '',
    kreita_je TEXT NOT NULL,
    modifita_je TEXT NOT NULL
);
"""

_CREATE_UNDO_CHANGES = """
CREATE TABLE IF NOT EXISTS undo_changes (
    id TEXT PRIMARY KEY,
    operacio TEXT NOT NULL,
    payload TEXT NOT NULL,
    kreita_je TEXT NOT NULL
);
"""

# ──────────────────────────────────────────────────────────────────────────────
# Indexes
# ──────────────────────────────────────────────────────────────────────────────

_CREATE_STMTS = [
    _CREATE_KALENDAROJ,
    _CREATE_EVENTOJ,
    _CREATE_TODOJ,
    _CREATE_ETIKEDOJ,
    _CREATE_TODOJ_ETIKEDO,
    _CREATE_TAGLIBRO,
    _CREATE_TAGLIBRO_ETIKEDO,
    _CREATE_SYNC_QUEUE,
    _CREATE_UNDO_CHANGES,
]

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_eventoj_kalendaro ON eventoj(kalendaro_uuid);",
    "CREATE INDEX IF NOT EXISTS idx_eventoj_komenco ON eventoj(komenco);",
    "CREATE INDEX IF NOT EXISTS idx_todoj_stato ON todoj(stato);",
    "CREATE INDEX IF NOT EXISTS idx_todoj_titolo_norm ON todoj(titolo_norm);",
    "CREATE INDEX IF NOT EXISTS idx_todoj_priskribo_norm ON todoj(priskribo_norm);",
    "CREATE INDEX IF NOT EXISTS idx_taglibro_tempo ON taglibro(tempo);",
    "CREATE INDEX IF NOT EXISTS idx_taglibro_titolo_norm ON taglibro(titolo_norm);",
    "CREATE INDEX IF NOT EXISTS idx_taglibro_priskribo_norm ON taglibro(priskribo_norm);",
    "CREATE INDEX IF NOT EXISTS idx_etikedoj_teksto_norm ON etikedoj(teksto_norm);",
]


def ensure_dirs() -> None:
    """Ensure data directory exists."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_db() -> SQLiteDB:
    """Get database connection with all tables and indexes created."""
    ensure_dirs()
    if not health_check(_DB_FILE):
        from A.data.base import repair_db as _repair
        _repair(_DB_FILE)
    backup_db(_DB_FILE)
    db = SQLiteDB(_DB_FILE)

    for stmt in _CREATE_STMTS:
        db.execute(stmt)
    for stmt in _CREATE_INDEXES:
        db.execute(stmt)

    return db


__all__ = [
    "ensure_dirs",
    "get_db",
    "_CREATE_STMTS",
    "_CREATE_INDEXES",
    "_CREATE_SYNC_QUEUE",
    "_CREATE_UNDO_CHANGES",
]
