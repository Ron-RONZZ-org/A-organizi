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
        "calendars": {"source": 0, "migrated": 0, "keyring_migrated": 0, "errors": []},
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
        
        # Get existing UUIDs for idempotency
        existing_calendars = {
            r["uuid"] for r in target.execute("SELECT uuid FROM kalendaroj")
        }
        existing_events = {
            r["uuid"] for r in target.execute("SELECT uuid FROM eventoj")
        }
        
        rows = legacy.execute("SELECT * FROM calendars").fetchall()
        results["calendars"]["source"] = len(rows)
        
        for row in rows:
            uuid = row["uuid"]
            # Skip if already exists (idempotent)
            if uuid in existing_calendars:
                results["calendars"]["migrated"] += 1  # count as "migrated" (already there)
                continue
            
            try:
                target.execute(
                    """INSERT INTO kalendaroj (
                        uuid, url, username, remote, kreita_je, modifita_je
                    ) VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        uuid,
                        row["url"],
                        row["username"],
                        row["remote"],
                        row["kreita_je"],
                        row["modifita_je"],
                    ),
                )
                results["calendars"]["migrated"] += 1
                existing_calendars.add(uuid)  # prevent duplicates in same run
            except Exception as e:
                results["calendars"]["errors"].append(f"{uuid}: {e}")
        
        # Migrate keyring passwords for each calendar
        for row in legacy.execute("SELECT uuid FROM calendars").fetchall():
            if _migrate_calendar_keyring(row["uuid"]):
                results["calendars"]["keyring_migrated"] += 1
        
        # Migrate events
        rows = legacy.execute("SELECT * FROM events").fetchall()
        results["events"]["source"] = len(rows)
        
        for row in rows:
            uuid = row["uuid"]
            # Skip if already exists (idempotent)
            if uuid in existing_events:
                results["events"]["migrated"] += 1
                continue
            
            try:
                partoprenantoj = _parse_json_field(row, "partoprenantoj")
                target.execute(
                    """INSERT INTO eventoj (
                        uuid, kalendaro_uuid, titolo, komenco, fino,
                        kategorio, loko, ripeto, partoprenantoj, priskribo,
                        kreita_je, modifita_je
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        uuid,
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
                existing_events.add(uuid)
            except Exception as e:
                results["events"]["errors"].append(f"{uuid}: {e}")
        
        legacy.close()
    
    # Migrate tasks and journal from tasklibro.db
    if _TASKLIBRO_DB.exists():
        legacy = sqlite3.connect(str(_TASKLIBRO_DB))
        legacy.row_factory = sqlite3.Row
        
        # Migrate labels
        rows = legacy.execute("SELECT * FROM etikedo").fetchall()
        results["labels"]["source"] = len(rows)
        
        # Get existing for idempotency
        existing_labels = {r["uuid"] for r in target.execute("SELECT uuid FROM etikedoj")}
        
        for row in rows:
            uuid = row["uuid"]
            if uuid in existing_labels:
                results["labels"]["migrated"] += 1
                continue
            
            try:
                tekst = row["teksto"]
                teksto_norm = tekst.lower().strip() if tekst else ""
                
                target.execute(
                    """INSERT INTO etikedoj (
                        uuid, teksto, teksto_norm, koloro, kreita_je, modifita_je
                    ) VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        uuid,
                        tekst,
                        teksto_norm,
                        "",  # Legacy has no koloro
                        now,
                        now,
                    ),
                )
                results["labels"]["migrated"] += 1
                existing_labels.add(uuid)
            except Exception as e:
                results["labels"]["errors"].append(f"{uuid}: {e}")
        
        # Migrate tasks
        rows = legacy.execute("SELECT * FROM todo").fetchall()
        results["tasks"]["source"] = len(rows)
        
        existing_tasks = {r["uuid"] for r in target.execute("SELECT uuid FROM todoj")}
        
        for row in rows:
            uuid = row["uuid"]
            if uuid in existing_tasks:
                results["tasks"]["migrated"] += 1
                continue
            
            try:
                titolo_norm = row["titolo"].lower().strip() if row["titolo"] else ""
                priskribo_norm = row["priskribo"].lower().strip() if row["priskribo"] else ""
                
                target.execute(
                    """INSERT INTO todoj (
                        uuid, titolo, titolo_norm, priskribo, priskribo_norm,
                        prioritato, stato, kreita_je, modifita_je
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        uuid,
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
                existing_tasks.add(uuid)
            except Exception as e:
                results["tasks"]["errors"].append(f"{uuid}: {e}")
        
        # Migrate journal entries
        rows = legacy.execute("SELECT * FROM taglibro").fetchall()
        results["journal"]["source"] = len(rows)
        
        existing_journal = {r["uuid"] for r in target.execute("SELECT uuid FROM taglibro")}
        
        for row in rows:
            uuid = row["uuid"]
            if uuid in existing_journal:
                results["journal"]["migrated"] += 1
                continue
            
            try:
                titolo_norm = row["titolo"].lower().strip() if row["titolo"] else ""
                priskribo_norm = row["priskribo"].lower().strip() if row["priskribo"] else ""
                
                target.execute(
                    """INSERT INTO taglibro (
                        uuid, titolo, titolo_norm, priskribo, priskribo_norm,
                        tempo, kreita_je, modifita_je
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        uuid,
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
                existing_journal.add(uuid)
            except Exception as e:
                results["journal"]["errors"].append(f"{uuid}: {e}")
        
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


def _migrate_calendar_keyring(calendar_uuid: str) -> bool:
    """Migrate calendar password from autish keyring to A-organizi.
    
    autish uses: keyring.get_password("autish.kalendaro", calendar_uuid)
    A-organizi uses: keyring.get_password("A.kalendaro", calendar_uuid)
    
    Returns:
        True if password was migrated
    """
    from A.utils.deps import ensure_dependency

    try:
        ensure_dependency("keyring", "keyring")
        import keyring
    except ImportError:
        return False
    
    try:
        # Try to get old password
        old_password = keyring.get_password("autish.kalendaro", calendar_uuid)
        if not old_password:
            return False
        
        # Store with new service name
        keyring.set_password("A.kalendaro", calendar_uuid, old_password)
        
        # Delete old entry (ignore errors - may not exist)
        try:
            keyring.delete_password("autish.kalendaro", calendar_uuid)
        except Exception:
            pass
        
        return True
    except Exception:
        return False


__all__ = ["migrate"]