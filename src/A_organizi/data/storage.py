"""Organizi data layer - SQLite storage for kalendaro, todo, taglibro."""

from __future__ import annotations

from pathlib import Path

from A import ensure_dirs as _ensure_dirs
from A.data.base import SQLiteDB

_DATA_DIR: Path = Path.home() / ".local" / "share" / "A"

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
    teksto TEXT NOT NULL DEFAULT '',
    estado TEXT NOT NULL DEFAULT 'malfermita',
    prioritato REAL NOT NULL DEFAULT 0.0,
    fino TEXT NOT NULL DEFAULT '',
    kreita_je TEXT NOT NULL,
    modifita_je TEXT NOT NULL
);
"""

_CREATE_TIKEDOJ = """
CREATE TABLE IF NOT EXISTS etikedoj (
    uuid TEXT PRIMARY KEY,
    teksto TEXT NOT NULL,
    koloro TEXT NOT NULL DEFAULT '',
    kreita_je TEXT NOT NULL,
    modifita_je TEXT NOT NULL
);
"""

_CREATE_TODOJ_TIKEDOJ = """
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
    dato TEXT PRIMARY KEY,
    teksto TEXT NOT NULL DEFAULT '',
    kreita_je TEXT NOT NULL,
    modifita_je TEXT NOT NULL
);
"""

# ────────────────────────────────────────────────────────────────��─────────────
# Indexes
# ──────────────────────────────────────────────────────────────────────────────

_CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_eventoj_kalendaro ON eventoj(kalendaro_uuid);
CREATE INDEX IF NOT EXISTS idx_eventoj_komenco ON eventoj(komenco);
CREATE INDEX IF NOT EXISTS idx_todoj_estado ON todoj(estado);
CREATE INDEX IF NOT EXISTS idx_taglibro_dato ON taglibro(dato);
"""


def ensure_dirs() -> None:
    """Ensure data directory exists."""
    _ensure_dirs(_DATA_DIR)


def get_db(path: Path = _DATA_DIR / "organizi.db") -> SQLiteDB:
    """Get database connection."""
    ensure_dirs()
    db = SQLiteDB(path)
    
    stmts = [
        _CREATE_KALENDAROJ, _CREATE_EVENTOJ,
        _CREATE_TODOJ, _CREATE_TIKEDOJ, _CREATE_TODOJ_TIKEDOJ,
        _CREATE_TAGLIBRO, _CREATE_INDEXES,
    ]
    for stmt in stmts:
        db.execute(stmt)
    
    return db


__all__ = ["ensure_dirs", "get_db"]