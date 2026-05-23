# AGENTS.md — Rules for A-organizi
This file extends [A-workspace](./workspace/AGENTS.md).

This file extends root A-core AGENTS.md for the A-organizi plugin.

## Relationship to A-core

**A-organizi depends on A-core** for:
- `A` package imports (i18n, output, subprocess, SQLite)
- Plugin discovery via entry points
- Shared utilities
- **API Reference**: See [A-core AGENTS.md](https://github.com/Ron-RONZZ-org/A-core/blob/main/AGENTS.md#api-reference)

**All source code must import from `A`, never duplicate utilities.**

## Combined Plugin

A-organizi combines three autish commands:
- kalendaro (calendar)
- todo (tasks)
- taglibro (journal)

This is intentional — they share the same SQLite database for simplicity.

## If You Need Something in Core

If you need a utility that should be in A-core:

1. **Search existing issues** on [A-core](https://github.com/Ron-RONZZ-org/A-core/issues)
2. **Create an issue** describing the need
3. **Wait for core enhancement** before implementing locally
4. **Use feature detection** when available

## Architecture

```
src/A_organizi/
├── __init__.py       # Plugin exports
├── cli/              # CLI package (split to avoid 500+ line monoliths)
│   ├── __init__.py   # Main Typer app, sub-typer registrations
│   ├── etikedi.py    # etikedoj (labels) commands
│   ├── todo.py       # todo commands
│   ├── taglibro.py   # taglibro commands
│   ├── kalendaro.py  # kalendaro (calendar management) commands
│   ├── okazajo.py         # okazajo (event management) CRUD commands
│   ├── okazajo_retposto.py # Retposto import helpers (split from okazajo.py for 500-line limit)
│   └── okazajo_util.py    # Event utilities (ICS import/export, sync, undo)
├── utils/
│   ├── __init__.py
│   ├── labels.py          # Shared label helpers (resolve_refs, parse_blob, etc.)
│   ├── retposto_ics.py    # .ics import from A-lien email attachments
│   ├── sync.py            # CalDAV client, sync queue, password management
│   └── undo.py            # Calendar/event undo operations
├── service.kalendaro.py  # Calendar + event CRUD services
├── data/
│   └── storage.py    # SQLite (uses A.data.base)
```

## Database Schema

### Tables

| Table | PK | Key Columns | Notes |
|-------|----|-------------|-------|
| `kalendaroj` | `uuid` | `url`, `username`, `remote` | Calendar URLs |
| `eventoj` | `uuid` | `kalendaro_uuid`, `titolo`, `komenco`, `fino` | Calendar events |
| `todoj` | `uuid` | `titolo`, `titolo_norm`, `prioritato` (TEXT), `stato` | Tasks with formula priority |
| `etikedoj` | `uuid` | `teksto`, `teksto_norm` (UNIQUE), `koloro` | Shared labels |
| `todoj_etikedo` | `(todo_uuid, etikedo_uuid)` | — | Task-label junction |
| `taglibro` | `uuid` | `titolo`, `titolo_norm`, `tempo` | Journal entries (multiple per day) |
| `taglibro_etikedo` | `(taglibro_uuid, etikedo_uuid)` | — | Journal-label junction |
| `sync_queue` | `id` | `calendar_uuid`, `operacio`, `stato` | CalDAV sync jobs |
| `undo_changes` | `id` | `operacio`, `payload` | Undo history |

### Key Design Decisions

- **taglibro uses `uuid` PK** (not `dato`) — supports multiple entries per day (overrides old A-organizi schema, matches autish-legacy)
- **Labels are shared** between todo and taglibro via `etikedoj` table with junction tables (matches autish-legacy `_tasklib` design)
- **prioritato is TEXT** — stores formula strings like `"min(20+2*D,70)"` (matches autish-legacy)
- **WAL mode** enabled via `SQLiteDB`

## Service Layer

Service follows the A-vorto / A-encik singleton pattern:

```python
from A_organizi.service import (
    get_kalendaro_service,
    get_todo_service,
    get_taglibro_service,
)
```

Each returns a `CRUDService` instance with `undo_size=30`.

## Testing

```bash
cd A-organizi
PYTHONPATH=../A-core/src:src .venv/bin/python -m pytest tests/ -v
```

### Test structure

- `tests/test_storage.py` — Schema creation, CRUDService integration, service singletons
- Tests use `tmp_path` + monkeypatching of `_DATA_DIR` for isolation

## Code Standards

1. Use `tr_multi()` for multi-language help text in CLI (not `tr()` with 3 args)
2. Use `error()` for errors, `info()` for info
3. Type hints on all public functions
4. Docstrings on all public functions
5. Tests required for all modules
6. Use WAL mode for SQLite



## Package Manager: `uv` is Required

All A-ecosystem development **must** use `uv` as the package manager:

| Operation | Command |
|-----------|---------|
| Install dependencies | `uv pip install <pkg>` |
| Install project in dev mode | `uv pip install -e .` |
| Run tests | `uv run pytest tests/` |
| Install CLI tools (poetry, etc.) | `uv tool install <tool>` |
| Add dev dependency | `uv add --dev <pkg>` |

**Exceptions:**
- `pip` in README install instructions is acceptable for end users who may not have `uv`
- Readthedocs platform build may require `pip` (platform constraint)
- Runtime `install-on-confirmation` code may fall back to `pip` if `uv` is unavailable (see A-core AGENTS.md)

## What to Avoid

- Don't duplicate A-core utilities
- Don't skip i18n (use `tr_multi()` / `tr()`)
- Don't use `print()` — use `A` output functions
- Don't hardcode paths — use `A.core.paths`
- Don't implement utilities that should be in core

## Progress

| Issue | Status | Description |
|-------|--------|-------------|
| #2 | ✅ Done | Storage schema + service infrastructure |
| #3 | ✅ Done | Shared etikedoj (labels) CLI + service |
| #4 | ✅ Done | taglibro CRUD + search |
| #5 | ✅ Done | todo priority formula engine + CRUD + search |
| #6 | ✅ Done | kalendaro/okazajo split — calendar mgmt + event CRUD |
| #7 | ✅ Done | kalendaro ICS import/export |
| #8 | ✅ Done | kalendaro CalDAV sync + undo |
| #9 | ✅ Done | kalendaro --pasvorto option |
| #10 | ✅ Done | kalendaro probe_calendar_config validation |
| #18 | ✅ Done | -R/--retposto option for okazajo aldoni to import .ics from email |
| #24 | ✅ Done | todo forigi: per-item resolution and confirmation for multi-identifier input |

## Migration from autish

A-organizi supports migration from autish kalendaro.db and tasklibro.db:

| Legacy | Target | Description |
|--------|--------|-------------|
| kalendaro.db → calendars | A-organizi → kalendaroj | Calendars |
| kalendaro.db → events | A-organizi → eventoj | Calendar events (146) |
| tasklibro.db → todo | A-organizi → todoj | Tasks (1) |
| tasklibro.db → taglibro | A-organizi → taglibro | Journal entries |
| tasklibro.db → etikedo | A-organizi → etikedoj | Labels |

**CLI:**
```bash
A migri           # Run migrations
```

**Programmatic:**
```python
from A_organizi.data.migrate_from_autish import migrate
result = migrate()
```

Features:
- Normalizes text for search (titolo_norm, priskribo_norm)
- Preserves timestamps
- Idempotent

## Branch Convention
All A-* repos use `main` as the primary branch. Use `main` for all development.
