"""Migration registration for A-organizi.

This module registers the migration with A.core.migration framework.
Called via entry point "A.migrations" by A-core's unified migri command.
"""

from A.core.migration import register_migration, MigrationResult
from A_organizi.data.migrate_from_autish import migrate as legacy_migrate


def _wrapper() -> MigrationResult:
    """Wrapper that converts old-style dict result to MigrationResult."""
    result = legacy_migrate()
    
    if isinstance(result, dict) and result.get("skipped"):
        return MigrationResult(
            module="A-organizi",
            source_db="kalendaro.db, tasklibro.db",
            target_table="kalendaroj, eventoj, todoj, taglibro",
            source_rows=0,
            migrated_rows=0,
            skipped=True,
            skipped_reason=result.get("reason", "unknown"),
        )
    
    # Aggregate counts from all result categories
    calendars = result.get("calendars", {})
    events = result.get("events", {})
    tasks = result.get("tasks", {})
    journal = result.get("journal", {})
    labels = result.get("labels", {})
    
    source_rows = (
        calendars.get("source", 0) +
        events.get("source", 0) +
        tasks.get("source", 0) +
        journal.get("source", 0) +
        labels.get("source", 0)
    )
    migrated_rows = (
        calendars.get("migrated", 0) +
        events.get("migrated", 0) +
        tasks.get("migrated", 0) +
        journal.get("migrated", 0) +
        labels.get("migrated", 0)
    )
    keyring_count = calendars.get("keyring_migrated", 0)
    all_errors = (
        calendars.get("errors", []) +
        events.get("errors", []) +
        tasks.get("errors", []) +
        journal.get("errors", []) +
        labels.get("errors", [])
    )
    
    # Build detail string with keyring if any migrated
    detail_parts = [
        f"calendars={calendars.get('migrated', 0)}",
        f"events={events.get('migrated', 0)}",
    ]
    if keyring_count > 0:
        detail_parts.append(f"keyring={keyring_count}")
    if all_errors:
        detail_parts.append(f"errors={len(all_errors)}")
    detail_str = ", ".join(detail_parts)
    
    return MigrationResult(
        module="A-organizi",
        source_db="kalendaro.db, tasklibro.db",
        target_table="kalendaroj, eventoj, todoj, taglibro",
        source_rows=source_rows,
        migrated_rows=migrated_rows,
        errors=all_errors,
        detail=detail_str,
    )


def register() -> None:
    """Register migration with A-core migration framework."""
    register_migration(
        module="A-organizi",
        legacy_db="kalendaro.db",
        target_table="kalendaroj, eventoj, todoj, taglibro",
        migrator=_wrapper,
    )


__all__ = ["register"]