"""Retposto import helpers for okazajo aldoni.

CLI-level support functions for importing .ics calendar events
from A-lien email attachments.  Split from okazajo.py to keep
each file under 500 lines.
"""

from __future__ import annotations

import typer

from A import error, info, tr_multi, warning


def _build_overrides(
    titolo: str | None,
    loko: str | None,
    kategorio: str | None,
    priskribo: str | None,
    ripeto: str | None,
) -> dict[str, str]:
    """Build overrides dict from CLI flags, excluding None values.

    Only the fields mapped in ``retposto_ics._apply_overrides`` are
    included (``komenco`` / ``fino`` are ignored by that function).

    Returns:
        Dict with only the flags the user explicitly provided.
    """
    d: dict[str, str] = {}
    if titolo is not None:
        d["titolo"] = titolo.strip()
    if loko is not None:
        d["loko"] = loko.strip()
    if kategorio is not None:
        d["kategorio"] = kategorio.strip()
    if priskribo is not None:
        d["priskribo"] = priskribo.strip()
    if ripeto is not None:
        d["ripeto"] = ripeto.strip()
    return d


def _import_from_retposto(
    cal_uuid: str,
    message_uuids: list[str],
    overrides: dict[str, str],
) -> None:
    """Import .ics calendar events from A-lien email attachments.

    Handles runtime detection of A-lien, install prompt,
    override warning, and import reporting.

    Args:
        cal_uuid: Resolved target calendar UUID.
        message_uuids: Email message UUIDs to scan.
        overrides: Non-empty dict means user also passed traditional flags.
    """
    # ── Runtime A-lien detection ─────────────────────────────────────────
    try:
        from A_lien.service import get_retposto_service as _get_rs
    except ImportError:
        _prompt_install_alien()
        # Retry after install
        from A_lien.service import get_retposto_service as _get_rs  # type: ignore[import-untyped]

    rs = _get_rs()

    # ── Resolve UUID prefixes → full UUIDs ──────────────────────────────
    resolved = _resolve_message_uuids(rs, message_uuids)
    # resolved is a dict: user_input -> full_uuid (or raises Exit on failure)

    # ── Validate message UUIDs ───────────────────────────────────────────
    from A_organizi.utils.retposto_ics import (
        count_ics_events,
        list_ics_attachments,
        import_ics_from_messages,
    )

    full_uuids = list(resolved.values())
    msgs = list_ics_attachments(rs, full_uuids)
    if not msgs:
        error(tr_multi(
            "Neniu mesaĝo kun .ics aldonaĵo trovita.",
            "No message with .ics attachment found.",
            "Aucun message avec pièce jointe .ics trouvé.",
        ))
        raise typer.Exit(1)

    # ── Override warning (if overrides affect multiple events) ───────────
    if overrides:
        total_events = 0
        for msg_uuid, atts in msgs.items():
            for att in atts:
                try:
                    content = rs.get_attachment_content(
                        msg_uuid, att["dosiernomo"], timeout=15,
                    )
                    total_events += count_ics_events(
                        content.decode("utf-8", errors="replace"),
                    )
                except Exception:
                    pass

        if total_events > 1:
            override_names = ", ".join(f"--{k}" for k in overrides)
            warning(
                tr_multi(
                    f"Atentu: {override_names} anstataŭigos la kampojn de"
                    f" {total_events} eventoj.",
                    f"Warning: {override_names} will overwrite fields of"
                    f" {total_events} events.",
                    f"Attention : {override_names} remplacera les champs de"
                    f" {total_events} événements.",
                ),
            )

    # ── Import ───────────────────────────────────────────────────────────
    db = _get_evento_db()
    imported = import_ics_from_messages(
        db, cal_uuid, rs, full_uuids, overrides=overrides or None,
    )

    total = sum(len(uuids) for uuids in imported.values())
    if total == 0:
        info(tr_multi(
            "Neniu nova evento importita (eble jam ekzistas duplicaĵoj).",
            "No new events imported (may be duplicates).",
            "Aucun nouvel événement importé (peut-être des doublons).",
        ))
        return

    info(tr_multi(
        f"Importis {total} evento(j)n el {len(imported)} mesaĝo(j).",
        f"Imported {total} event(s) from {len(imported)} message(s).",
        f"Importé {total} événement(s) depuis {len(imported)} message(s).",
    ))


def _resolve_message_uuids(
    rs: Any, prefixes: list[str],
) -> dict[str, str]:
    """Resolve message UUID prefixes to full UUIDs.

    For each prefix, tries exact match first (get_message), then
    prefix match (find_message_by_uuid_prefix).  Requires exactly
    one match per prefix.

    Args:
        rs: A-lien RetpostoService instance.
        prefixes: User-provided message UUIDs or prefixes.

    Returns:
        Dict mapping original prefix -> resolved full UUID.

    Raises:
        typer.Exit(1) if any prefix is ambiguous or not found.
    """
    resolved: dict[str, str] = {}
    for prefix in prefixes:
        msg = rs.get_message(prefix)
        if msg:
            resolved[prefix] = msg["uuid"]
            continue

        matches = rs.find_message_by_uuid_prefix(prefix)
        if len(matches) == 1:
            resolved[prefix] = matches[0]["uuid"]
            continue

        if len(matches) > 1:
            error(tr_multi(
                f"Pluraj mesaĝoj kongruas kun '{prefix}':",
                f"Multiple messages match '{prefix}':",
                f"Plusieurs messages correspondent à '{prefix}':",
            ))
            for m in matches:
                subj = (m.get("subjekto", "") or "(sen temo)")[:50]
                info(f"  {m['uuid'][:8]}  {subj}")
        else:
            error(tr_multi(
                f"Mesaĝo ne trovita: {prefix}",
                f"Message not found: {prefix}",
                f"Message non trouvé: {prefix}",
            ))
        raise typer.Exit(1)

    return resolved


def _get_evento_db():
    """Get the SQLiteDB instance used by the EventService."""
    from A_organizi.service.kalendaro import get_evento_service
    return get_evento_service().db


def _prompt_install_alien() -> None:
    """Prompt user to install A-lien if missing."""
    from A.utils.deps import ensure_dependency

    try:
        ensure_dependency("A_lien", "A-lien")
    except ImportError:
        error(tr_multi(
            "Ne povis instali A-lien.",
            "Could not install A-lien.",
            "Impossible d'installer A-lien.",
        ))
        raise typer.Exit(1)


__all__ = [
    "_build_overrides",
    "_import_from_retposto",
]
