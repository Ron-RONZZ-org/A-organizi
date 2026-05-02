"""TaglibroService — journal CRUD with label management."""

from __future__ import annotations

from typing import Any

from A.core.service import CRUDService
from A.utils.normalize import fold_search_text

from A_organizi.data.storage import get_db
from A_organizi.utils.labels import parse_label_blob, search_items

_taglibro_service: TaglibroService | None = None


class TaglibroService(CRUDService):
    """CRUDService for taglibro (journal) with label attachment."""

    def set_labels(self, uuid: str, etikedo_uuids: list[str]) -> None:
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM taglibro_etikedo WHERE taglibro_uuid = ?", (uuid,))
            for etikedo_uuid in etikedo_uuids:
                conn.execute(
                    "INSERT OR IGNORE INTO taglibro_etikedo "
                    "(taglibro_uuid, etikedo_uuid) VALUES (?, ?)",
                    (uuid, etikedo_uuid),
                )

    def get_labels(self, uuid: str) -> list[tuple[str, str]]:
        rows = self.db.execute(
            "SELECT e.uuid, e.teksto FROM etikedoj e "
            "JOIN taglibro_etikedo te ON te.etikedo_uuid = e.uuid "
            "WHERE te.taglibro_uuid = ?", (uuid,)
        )
        return [(str(r["uuid"]), str(r.get("teksto") or "")) for r in rows]

    def _load_with_labels(self, uuid: str | None = None) -> list[dict[str, Any]]:
        where = ""
        params: tuple = ()
        if uuid:
            where = "WHERE t.uuid = ?"
            params = (uuid,)
        rows = self.db.execute(
            f"SELECT t.*, GROUP_CONCAT(e.uuid || ':' || e.teksto, '|') AS etikedoj_blob "
            f"FROM {self.table} t "
            f"LEFT JOIN taglibro_etikedo te ON te.taglibro_uuid = t.uuid "
            f"LEFT JOIN etikedoj e ON e.uuid = te.etikedo_uuid "
            f"{where} GROUP BY t.uuid ORDER BY t.tempo DESC, t.kreita_je DESC",
            params,
        )
        result = []
        for row in rows:
            item = dict(row)
            item["etikedoj"] = parse_label_blob(item.get("etikedoj_blob"))
            result.append(item)
        return result

    def get_with_labels(self, uuid: str) -> dict[str, Any] | None:
        entries = self._load_with_labels(uuid)
        return entries[0] if entries else None

    def list_with_labels(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._load_with_labels()[:limit]

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        etikedo_uuids: list[str] = data.pop("etikedo", [])
        result = super().create(data)
        if etikedo_uuids:
            self.set_labels(result["uuid"], etikedo_uuids)
        return self.get_with_labels(result["uuid"]) or result

    def update(self, uuid: str, data: dict[str, Any]) -> dict[str, Any]:
        etikedo_uuids: list[str] | None = data.pop("etikedo", None)
        result = super().update(uuid, data)
        if etikedo_uuids is not None:
            self.set_labels(uuid, etikedo_uuids)
        return self.get_with_labels(uuid) or result

    def search_taglibro(
        self, query: str | None = None, *, titolo=None, priskribo=None,
        etikedo=None, de_tempo=None, gxis_tempo=None, limit: int = 50,
    ) -> tuple[list[dict[str, Any]], bool]:
        entries = self._load_with_labels()
        results = list(entries)
        fuzzy_used = False
        if query:
            results, fuzzy_used = search_items(
                results, query,
                text_getter=lambda i: f"{i.get('titolo') or ''} {i.get('priskribo') or ''}",
                limit=max(limit, 1),
            )
        if titolo:
            n = fold_search_text(titolo)
            results = [i for i in results if n in fold_search_text(str(i.get("titolo") or ""))]
        if priskribo:
            n = fold_search_text(priskribo)
            results = [i for i in results if n in fold_search_text(str(i.get("priskribo") or ""))]
        if etikedo:
            wanted = set(etikedo)
            results = [i for i in results if wanted.issubset({u for u, _ in (i.get("etikedoj") or [])})]
        if de_tempo:
            results = [i for i in results if str(i.get("tempo") or "") >= de_tempo]
        if gxis_tempo:
            results = [i for i in results if str(i.get("tempo") or "") <= gxis_tempo]
        if limit > 0:
            results = results[:limit]
        return results, fuzzy_used


def get_taglibro_service() -> TaglibroService:
    """Get the singleton TaglibroService for taglibro table."""
    global _taglibro_service
    if _taglibro_service is None:
        _taglibro_service = TaglibroService(get_db(), "taglibro", undo_size=30)
    return _taglibro_service


__all__ = ["TaglibroService", "get_taglibro_service"]
