# A-organizi

Calendar, todo, and journal plugin for the A-ecosystem.

- **CLI entry**: `A organizi okazajo aldoni ...` etc.
- **Tech stack**: Python 3.11+, Typer, Rich, SQLite (WAL mode), A-core framework
- **Package mgr**: uv
- **Tests**: pytest via `uv run pytest tests/ -v`
- **Style**: Ruff linting
- **Structure**: `cli/` package (<500 lines each), `service/` singleton pattern, `utils/` utilities, `data/storage.py` SQLite
