"""Service layer for A-organizi using CRUDService."""

from __future__ import annotations

from typing import Any

from A.core.service import CRUDService
from A.utils.normalize import fold_search_text

from A_organizi.data.storage import get_db

_kalendaro_service: CRUDService | None = None
_todo_service: CRUDService | None = None
_taglibro_service: CRUDService | None = None
_etikedo_service: EtikedoService | None = None


class EtikedoService(CRUDService):
    """CRUDService for etikedoj (labels) with teksto_norm dedup.

    Ensures:
    - ``teksto_norm`` is auto-computed from ``teksto`` on create/update.
    - Duplicate ``teksto_norm`` is rejected (UNIQUE constraint in schema).
    """

    def _prepare(self, data: dict[str, Any]) -> dict[str, Any]:
        """Compute teksto_norm from teksto if not provided."""
        result = dict(data)
        if "teksto" in result and "teksto_norm" not in result:
            result["teksto_norm"] = fold_search_text(result["teksto"])
        return result

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create label with auto-computed teksto_norm."""
        return super().create(self._prepare(data))

    def update(self, uuid: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update label with auto-computed teksto_norm."""
        return super().update(uuid, self._prepare(data))


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


def get_etikedo_service() -> EtikedoService:
    """Get the singleton EtikedoService for etikedoj table.

    Returns:
        EtikedoService instance for label operations with dedup.
    """
    global _etikedo_service
    if _etikedo_service is None:
        _etikedo_service = EtikedoService(get_db(), "etikedoj", undo_size=30)
    return _etikedo_service


__all__ = [
    "EtikedoService",
    "get_kalendaro_service",
    "get_todo_service",
    "get_taglibro_service",
    "get_etikedo_service",
]
