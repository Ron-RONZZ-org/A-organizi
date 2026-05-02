"""Service layer for A-organizi using CRUDService."""

from __future__ import annotations

from A.core.service import CRUDService

from A_organizi.data.storage import get_db
from A_organizi.service.etikedo import EtikedoService, get_etikedo_service
from A_organizi.service.taglibro import TaglibroService, get_taglibro_service
from A_organizi.service.todo import TodoService, get_todo_service

_kalendaro_service: CRUDService | None = None


def get_kalendaro_service() -> CRUDService:
    """Get the singleton CRUDService for kalendaroj table."""
    global _kalendaro_service
    if _kalendaro_service is None:
        _kalendaro_service = CRUDService(get_db(), "kalendaroj", undo_size=30)
    return _kalendaro_service


__all__ = [
    "EtikedoService",
    "TaglibroService",
    "TodoService",
    "get_kalendaro_service",
    "get_todo_service",
    "get_taglibro_service",
    "get_etikedo_service",
]
