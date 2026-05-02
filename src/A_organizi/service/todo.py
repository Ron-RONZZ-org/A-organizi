"""TodoService — task CRUD with labels, status, and priority."""

from __future__ import annotations

from typing import Any

from A.core.service import CRUDService
from A.utils.normalize import fold_search_text

from A_organizi.data.storage import get_db
from A_organizi.priority import compute_priority, validate_formula
from A_organizi.utils.labels import parse_label_blob, search_items

_todo_service: TodoService | None = None


class TodoService(CRUDService):
    """CRUDService for todoj (tasks) with label and priority support."""

    _VALID_STATOJ = {"malfermita", "farita", "prokrastita", "nuligita"}
    _STATO_ALIASES = {
        "open": "malfermita", "done": "farita", "deferred": "prokrastita",
        "cancelled": "nuligita", "canceled": "nuligita",
    }

    def normalize_stato(self, raw: str) -> str:
        value = str(raw or "").strip().casefold()
        result = self._STATO_ALIASES.get(value)
        if result:
            return result
        if value in self._VALID_STATOJ:
            return value
        raise ValueError(
            f"Nevalida stato: {raw!r}. Validaj: {', '.join(sorted(self._VALID_STATOJ))}"
        )

    def set_labels(self, uuid: str, etikedo_uuids: list[str]) -> None:
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM todoj_etikedo WHERE todo_uuid = ?", (uuid,))
            for etikedo_uuid in etikedo_uuids:
                conn.execute(
                    "INSERT OR IGNORE INTO todoj_etikedo (todo_uuid, etikedo_uuid) VALUES (?, ?)",
                    (uuid, etikedo_uuid),
                )

    def get_labels(self, uuid: str) -> list[tuple[str, str]]:
        rows = self.db.execute(
            "SELECT e.uuid, e.teksto FROM etikedoj e "
            "JOIN todoj_etikedo te ON te.etikedo_uuid = e.uuid WHERE te.todo_uuid = ?", (uuid,)
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
            f"LEFT JOIN todoj_etikedo te ON te.todo_uuid = t.uuid "
            f"LEFT JOIN etikedoj e ON e.uuid = te.etikedo_uuid "
            f"{where} GROUP BY t.uuid ORDER BY t.kreita_je DESC",
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
        if "stato" in data:
            data["stato"] = self.normalize_stato(data["stato"])
        if "prioritato" in data:
            prio = str(data.get("prioritato") or "0")
            if not validate_formula(prio):
                raise ValueError(f"Nevalida prioritata formulo: {prio!r}")
        etikedo_uuids: list[str] = data.pop("etikedo", [])
        result = super().create(data)
        if etikedo_uuids:
            self.set_labels(result["uuid"], etikedo_uuids)
        return self.get_with_labels(result["uuid"]) or result

    def update(self, uuid: str, data: dict[str, Any]) -> dict[str, Any]:
        if "stato" in data:
            data["stato"] = self.normalize_stato(data["stato"])
        if "prioritato" in data:
            prio = str(data.get("prioritato") or "0")
            if not validate_formula(prio):
                raise ValueError(f"Nevalida prioritata formulo: {prio!r}")
        etikedo_uuids: list[str] | None = data.pop("etikedo", None)
        result = super().update(uuid, data)
        if etikedo_uuids is not None:
            self.set_labels(uuid, etikedo_uuids)
        return self.get_with_labels(uuid) or result

    def search_todo(
        self, query=None, *, titolo=None, priskribo=None, stato=None,
        etikedo=None, prioritato_min=None, prioritato_max=None, limit=50,
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
        if stato:
            normalized = self.normalize_stato(stato)
            results = [i for i in results if str(i.get("stato") or "") == normalized]
        if etikedo:
            wanted = set(etikedo)
            results = [i for i in results if wanted.issubset({u for u, _ in (i.get("etikedoj") or [])})]
        if prioritato_min is not None or prioritato_max is not None:
            filtered = []
            for item in results:
                value = compute_priority(str(item.get("prioritato") or "0"), str(item.get("kreita_je") or ""))
                if prioritato_min is not None and value < prioritato_min:
                    continue
                if prioritato_max is not None and value > prioritato_max:
                    continue
                filtered.append(item)
            results = filtered
        if limit > 0:
            results = results[:limit]
        return results, fuzzy_used


def get_todo_service() -> TodoService:
    """Get the singleton TodoService for todoj table."""
    global _todo_service
    if _todo_service is None:
        _todo_service = TodoService(get_db(), "todoj", undo_size=30)
    return _todo_service


__all__ = ["TodoService", "get_todo_service"]
