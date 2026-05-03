"""Migration from autish kalendaro.db and tasklibro.db to A-organizi.

Run with:
    from A_organizi.data.migrate_from_autish import migrate
    
    result = migrate()
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from A_organizi.data.storage import get_db as _get_db


# Legacy autish data path
_LEGACY_DIR = Path.home() / ".local" / "share" / "autish"
_KALENDARO_DB = _LEGACY_DIR / "kalendaro.db"
_TASKLIBRO_DB = _LEGACY_DIR / "tasklibro.db"


def migrate() -> dict:
    """Migrate from autish kalendaro.db and tasklibro.db to A-organizi.
    
    Returns:
        Dict with migration results
    """
    results = {
        "calendars": {"source": 0, "migrated": 0, "errors": []},
        "events": {"source": 0, "migrated": 0, "errors": []},
        "tasks": {"source": 0, "migrated": 0, "errors": []},
        "journal": {"source": 0, "migrated": 0, "errors": []},
        "labels": {"source": 0, "migrated": 0, "errors": []},
    }
    
    target = _get_db()
    now = datetime.now(timezone.utc).isoformat()
    
    # Migrate calendars from kalendaro.db
    if _KALENDARO_DB.exists():
        legacy = sqlite3.connect(str(_KALENDARO_DB))
        legacy.row_factory = sqlite3.Row
        
        rows = legacy.execute("SELECT * FROM calendars").fetchall()
        results["calendars"]["source"] = len(rows)
        
        for row in rows:
            try:
                target.execute(
                    """INSERT INTO kalendaroj (
                        uuid, url, username, remote, kreita_je, modifita_je
                    ) VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        row["uuid"],
                        row["url"],
                        row["username"],
                        row["remote"],
                        row["kreita_je"],
                        row["modifita_je"],
                    ),
                )
                results["calendars"]["migrated"] += 1
            except Exception as e:
                results["calendars"]["errors"].append(f"{row['uuid']}: {e}")
        
        # Migrate events
        rows = legacy.execute("SELECT * FROM events").fetchall()
        results["events"]["source"] = len(rows)
        
        for row in rows:
            try:
                partoprenantoj = _parse_json_field(row, "partoprenantoj")
                target.execute(
                    """INSERT INTO eventoj (
                        uuid, kalendaro_uuid, titolo, komenco, fino,
                        kategorio, loko, ripeto, partoprenantoj, priskribo,
                        kreita_je, modifita_je
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        row["uuid"],
                        row["calendar_uuid"],
                        row["titolo"],
                        row["komenco"],
                        row["fino"],
                        row["kategorio"],
                        row["loko"],
                        row["ripeto"],
                        json.dumps(partoprenantoj),
                        row["priskribo"],
                        row["kreita_je"],
                        row["modifita_je"],
                    ),
                )
                results["events"]["migrated"] += 1
            except Exception as e:
                results["events"]["errors"].append(f"{row['uuid']}: {e}")
        
        legacy.close()
    
    # Migrate tasks and journal from tasklibro.db
    if _TASKLIBRO_DB.exists():
        legacy = sqlite3.connect(str(_TASKLIBRO_DB))
        legacy.row_factory = sqlite3.Row
        
        # Migrate labels
        rows = legacy.execute("SELECT * FROM etikedo").fetchall()
        results["labels"]["source"] = len(rows)
        
        for row in rows:
            try:
                # Normalize text for search
                tekst = row["teksto"]
                teksto_norm = tekst.lower().strip() if tekst else ""
                
                target.execute(
                    """INSERT INTO etikedoj (
                        uuid, teksto, teksto_norm, koloro, kreita_je, modifita_je
                    ) VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        row["uuid"],
                        tekst,
                        teksto_norm,
                        row.get("koloro", ""),
                        now,
                        now,
                    ),
                )
                results["labels"]["migrated"] += 1
            except Exception as e:
                results["labels"]["errors"].append(f"{row['uuid']}: {e}")
        
        # Migrate tasks
        rows = legacy.execute("SELECT * FROM todo").fetchall()
        results["tasks"]["source"] = len(rows)
        
        for row in rows:
            try:
                titolo_norm = row["titolo"].lower().strip() if row["titolo"] else ""
                priskribo_norm = row["priskribo"].lower().strip() if row["priskribo"] else ""
                
                target.execute(
                    """INSERT INTO todoj (
                        uuid, titolo, titolo_norm, priskribo, priskribo_norm,
                        prioritato, stato, kreita_je, modifita_je
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        row["uuid"],
                        row["titolo"],
                        titolo_norm,
                        row["priskribo"],
                        priskribo_norm,
                        row["prioritato"],
                        row["stato"],
                        row["kreita_je"],
                        row["modifita_je"],
                    ),
                )
                results["tasks"]["migrated"] += 1
            except Exception as e:
                results["tasks"]["errors"].append(f"{row['uuid']}: {e}")
        
        # Migrate journal entries
        rows = legacy.execute("SELECT * FROM taglibro").fetchall()
        results["journal"]["source"] = len(rows)
        
        for row in rows:
            try:
                titolo_norm = row["titolo"].lower().strip() if row["titolo"] else ""
                priskribo_norm = row["priskribo"].lower().strip() if row["priskribo"] else ""
                
                target.execute(
                    """INSERT INTO taglibro (
                        uuid, titolo, titolo_norm, priskribo, priskribo_norm,
                        tempo, kreita_je, modifita_je
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        row["uuid"],
                        row["titolo"],
                        titolo_norm,
                        row["priskribo"],
                        priskribo_norm,
                        row["tempo"],
                        row["kreita_je"],
                        row["modifita_je"],
                    ),
                )
                results["journal"]["migrated"] += 1
            except Exception as e:
                results["journal"]["errors"].append(f"{row['uuid']}: {e}")
        
        legacy.close()
    
    return results


def _parse_json_field(row: sqlite3.Row, field: str) -> list | dict:
    """Parse a JSON field."""
    val = row[field]
    if val:
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            pass
    return []


__all__ = ["migrate"]