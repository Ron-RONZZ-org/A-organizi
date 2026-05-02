"""Service layer for A-organizi using CRUDService."""

from __future__ import annotations

from typing import Any

from A.core.service import CRUDService
from A.utils.normalize import fold_search_text

from A_organizi.data.storage import get_db
from A_organizi.utils.labels import parse_label_blob

_kalendaro_service: CRUDService | None = None
_todo_service: CRUDService | None = None
_taglibro_service: TaglibroService | None = None
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


class TaglibroService(CRUDService):
    """CRUDService for taglibro (journal) with label attachment.

    Extends CRUDService with methods for managing the many-to-many
    relationship between journal entries and shared labels (etikedoj).
    """

    def set_labels(self, uuid: str, etikedo_uuids: list[str]) -> None:
        """Replace all label assignments for a journal entry.

        Args:
            uuid: Journal entry UUID.
            etikedo_uuids: List of label UUIDs to assign.
        """
        with self.db.transaction() as conn:
            conn.execute(
                "DELETE FROM taglibro_etikedo WHERE taglibro_uuid = ?",
                (uuid,),
            )
            for etikedo_uuid in etikedo_uuids:
                conn.execute(
                    "INSERT OR IGNORE INTO taglibro_etikedo "
                    "(taglibro_uuid, etikedo_uuid) VALUES (?, ?)",
                    (uuid, etikedo_uuid),
                )

    def get_labels(self, uuid: str) -> list[tuple[str, str]]:
        """Get label assignments for a journal entry.

        Args:
            uuid: Journal entry UUID.

        Returns:
            List of (uuid, text) tuples for assigned labels.
        """
        rows = self.db.execute(
            """
            SELECT e.uuid, e.teksto
            FROM etikedoj e
            JOIN taglibro_etikedo te ON te.etikedo_uuid = e.uuid
            WHERE te.taglibro_uuid = ?
            """,
            (uuid,),
        )
        return [(str(r["uuid"]), str(r.get("teksto") or "")) for r in rows]

    def _load_with_labels(
        self, uuid: str | None = None
    ) -> list[dict[str, Any]]:
        """Load entries with their labels attached.

        Args:
            uuid: If provided, load only this entry.

        Returns:
            List of entry dicts with 'etikedoj' key added.
        """
        where = ""
        params: tuple = ()
        if uuid:
            where = "WHERE t.uuid = ?"
            params = (uuid,)

        rows = self.db.execute(
            f"""
            SELECT t.*,
                   GROUP_CONCAT(e.uuid || ':' || e.teksto, '|')
                       AS etikedoj_blob
            FROM {self.table} t
            LEFT JOIN taglibro_etikedo te ON te.taglibro_uuid = t.uuid
            LEFT JOIN etikedoj e ON e.uuid = te.etikedo_uuid
            {where}
            GROUP BY t.uuid
            ORDER BY t.tempo DESC, t.kreita_je DESC
            """,
            params,
        )
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["etikedoj"] = parse_label_blob(item.get("etikedoj_blob"))
            result.append(item)
        return result

    def get_with_labels(self, uuid: str) -> dict[str, Any] | None:
        """Get a single entry with labels attached.

        Args:
            uuid: Entry UUID.

        Returns:
            Entry dict with 'etikedoj' key, or None.
        """
        entries = self._load_with_labels(uuid)
        return entries[0] if entries else None

    def list_with_labels(
        self, limit: int = 50
    ) -> list[dict[str, Any]]:
        """List entries with labels attached.

        Args:
            limit: Maximum number of entries.

        Returns:
            List of entry dicts with 'etikedoj' key.
        """
        entries = self._load_with_labels()
        return entries[:limit]

    def create(
        self, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Create entry with optional label assignment.

        If ``data`` contains an ``"etikedo"`` list of UUIDs, they
        will be assigned after creation.

        Args:
            data: Entry data. May include ``"etikedo"`` key.

        Returns:
            Created entry dict.
        """
        etikedo_uuids: list[str] = data.pop("etikedo", [])
        result = super().create(data)
        if etikedo_uuids:
            self.set_labels(result["uuid"], etikedo_uuids)
        return self.get_with_labels(result["uuid"]) or result

    def update(
        self, uuid: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Update entry with optional label reassignment.

        If ``data`` contains an ``"etikedo"`` key, labels will be
        replaced entirely.

        Args:
            uuid: Entry UUID.
            data: Entry data. May include ``"etikedo"`` key.

        Returns:
            Updated entry dict with labels.
        """
        etikedo_uuids: list[str] | None = data.pop("etikedo", None)
        result = super().update(uuid, data)
        if etikedo_uuids is not None:
            self.set_labels(uuid, etikedo_uuids)
        return self.get_with_labels(uuid) or result

    def search_taglibro(
        self,
        query: str | None = None,
        *,
        titolo: str | None = None,
        priskribo: str | None = None,
        etikedo: list[str] | None = None,
        de_tempo: str | None = None,
        gxis_tempo: str | None = None,
        limit: int = 50,
    ) -> tuple[list[dict[str, Any]], bool]:
        """Search journal entries with combinable filters.

        All filters are AND-combined. Text filters use normalized
        (folded) search on the ``_norm`` columns.

        Args:
            query: Search text (matches titolo + priskribo).
            titolo: Filter by title content (substring).
            priskribo: Filter by description content (substring).
            etikedo: Filter by label UUIDs (all must be present).
            de_tempo: ISO datetime lower bound.
            gxis_tempo: ISO datetime upper bound.
            limit: Maximum results.

        Returns:
            List of matching entry dicts with labels.
        """
        entries = self._load_with_labels()
        results: list[dict[str, Any]] = list(entries)
        fuzzy_used = False

        if query:
            from A_organizi.utils.labels import search_items

            results, fuzzy_used = search_items(
                results,
                query,
                text_getter=lambda item: (
                    f"{item.get('titolo') or ''} {item.get('priskribo') or ''}"
                ),
                limit=max(limit, 1),
            )
        if titolo:
            needle = fold_search_text(titolo)
            results = [
                item
                for item in results
                if needle
                in fold_search_text(str(item.get("titolo") or ""))
            ]
        if priskribo:
            needle = fold_search_text(priskribo)
            results = [
                item
                for item in results
                if needle
                in fold_search_text(str(item.get("priskribo") or ""))
            ]
        if etikedo:
            wanted = set(etikedo)
            results = [
                item
                for item in results
                if wanted.issubset(
                    {uid for uid, _ in (item.get("etikedoj") or [])}
                )
            ]
        if de_tempo:
            results = [
                item
                for item in results
                if str(item.get("tempo") or "") >= de_tempo
            ]
        if gxis_tempo:
            results = [
                item
                for item in results
                if str(item.get("tempo") or "") <= gxis_tempo
            ]

        if limit > 0:
            results = results[:limit]
        return results, fuzzy_used


def get_kalendaro_service() -> CRUDService:
    """Get the singleton CRUDService for kalendaroj table."""
    global _kalendaro_service
    if _kalendaro_service is None:
        _kalendaro_service = CRUDService(get_db(), "kalendaroj", undo_size=30)
    return _kalendaro_service


def get_todo_service() -> CRUDService:
    """Get the singleton CRUDService for todoj table."""
    global _todo_service
    if _todo_service is None:
        _todo_service = CRUDService(get_db(), "todoj", undo_size=30)
    return _todo_service


def get_taglibro_service() -> TaglibroService:
    """Get the singleton TaglibroService for taglibro table.

    Returns:
        TaglibroService instance with label management methods.
    """
    global _taglibro_service
    if _taglibro_service is None:
        _taglibro_service = TaglibroService(get_db(), "taglibro", undo_size=30)
    return _taglibro_service


def get_etikedo_service() -> EtikedoService:
    """Get the singleton EtikedoService for etikedoj table."""
    global _etikedo_service
    if _etikedo_service is None:
        _etikedo_service = EtikedoService(get_db(), "etikedoj", undo_size=30)
    return _etikedo_service


__all__ = [
    "EtikedoService",
    "TaglibroService",
    "get_kalendaro_service",
    "get_todo_service",
    "get_taglibro_service",
    "get_etikedo_service",
]
