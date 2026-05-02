"""Service layer for A-organizi using CRUDService."""

from __future__ import annotations

from A.core.service import CRUDService

from A_organizi.data.storage import get_db

_kalendaro_service: CRUDService | None = None
_todo_service: CRUDService | None = None
_taglibro_service: CRUDService | None = None


def get_kalendaro_service() -> CRUDService:
    """Get the singleton CRUDService for kalendaroj table.

    Returns:
        CRUDService instance for calendar operations.
    """
    global _kalendaro_service
    if _kalendaro_service is None:
        _kalendaro_service = CRUDService(get_db(), "kalendaroj", undo_size=30)
    return _kalendaro_service


def get_todo_service() -> CRUDService:
    """Get the singleton CRUDService for todoj table.

    Returns:
        CRUDService instance for task operations.
    """
    global _todo_service
    if _todo_service is None:
        _todo_service = CRUDService(get_db(), "todoj", undo_size=30)
    return _todo_service


def get_taglibro_service() -> CRUDService:
    """Get the singleton CRUDService for taglibro table.

    Returns:
        CRUDService instance for journal operations.
    """
    global _taglibro_service
    if _taglibro_service is None:
        _taglibro_service = CRUDService(get_db(), "taglibro", undo_size=30)
    return _taglibro_service


__all__ = [
    "get_kalendaro_service",
    "get_todo_service",
    "get_taglibro_service",
]
