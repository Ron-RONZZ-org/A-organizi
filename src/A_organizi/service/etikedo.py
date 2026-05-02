"""EtikedoService — label CRUD with teksto_norm dedup."""

from __future__ import annotations

from typing import Any

from A.core.service import CRUDService
from A.utils.normalize import fold_search_text

from A_organizi.data.storage import get_db

_etikedo_service: EtikedoService | None = None


class EtikedoService(CRUDService):
    """CRUDService for etikedoj (labels) with teksto_norm dedup."""

    def _prepare(self, data: dict[str, Any]) -> dict[str, Any]:
        result = dict(data)
        if "teksto" in result and "teksto_norm" not in result:
            result["teksto_norm"] = fold_search_text(result["teksto"])
        return result

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        return super().create(self._prepare(data))

    def update(self, uuid: str, data: dict[str, Any]) -> dict[str, Any]:
        return super().update(uuid, self._prepare(data))


def get_etikedo_service() -> EtikedoService:
    """Get the singleton EtikedoService for etikedoj table."""
    global _etikedo_service
    if _etikedo_service is None:
        _etikedo_service = EtikedoService(get_db(), "etikedoj", undo_size=30)
    return _etikedo_service


__all__ = ["EtikedoService", "get_etikedo_service"]
