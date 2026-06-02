"""CLI commands for okazajo (event management within calendars).

Kept under 500 lines by splitting CRUD commands into okazajo_crud.py
and RRULE utilities into okazajo_rrule.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import typer

from A import error, info, tr_multi
from A.utils.output import console

from A_organizi.service.kalendaro import (
    CalendarService,
    get_evento_service,
    get_kalendaro_service,
)

# ── Typer app ────────────────────────────────────────────────────────────────

okazajo_app = typer.Typer(
    name="okazajo",
    help=tr_multi(
        "Okazajo — administri eventojn en kalendaroj.",
        "Okazajo — manage events in calendars.",
        "Okazajo — gérer les événements dans les calendriers.",
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)

# ── Display helpers ──────────────────────────────────────────────────────────


def _fmt_date(value: str) -> str:
    """Format ISO datetime to YYYY-MM-DD."""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime(
            "%Y-%m-%d"
        )
    except (ValueError, AttributeError):
        return str(value)[:10]


def _fmt_hhmm(value: str) -> str:
    """Format ISO datetime to HHMM."""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime(
            "%H%M"
        )
    except (ValueError, AttributeError):
        return str(value)[:4]


def _short(text: str, limit: int = 40) -> str:
    """Truncate text with ellipsis if longer than limit."""
    if not text:
        return ""
    return text if len(text) <= limit else text[: limit - 1] + "…"


# ── Event helpers ────────────────────────────────────────────────────────────


def _resolve_calendar(
    cal_svc: CalendarService,
    ref: str | None,
) -> str | None:
    """Resolve calendar reference or auto-select interactively.

    Args:
        cal_svc: CalendarService instance.
        ref: User-provided reference (UUID or prefix), or None for auto.

    Returns:
        Calendar UUID string, or None if not found / no selection.
    """
    if ref:
        cal_uuid = cal_svc.resolve_uuid(ref)
        if not cal_uuid:
            error(tr_multi(
                f"Kalendaro ne trovita: {ref}",
                f"Calendar not found: {ref}",
                f"Calendrier non trouvé: {ref}",
            ))
        return cal_uuid

    calendars = cal_svc.list()
    if not calendars:
        error(tr_multi(
            "Neniu kalendaro. Unue kreu kalendaron per "
            "'A organizi kalendaro aldoni'.",
            "No calendar. First create one with "
            "'A organizi kalendaro aldoni'.",
            "Aucun calendrier. Créez-en un avec "
            "'A organizi kalendaro aldoni'.",
        ))
        return None

    if len(calendars) == 1:
        c = calendars[0]
        info(tr_multi(
            f"Uzas kalendaron #{c['uuid'][:8]}",
            f"Using calendar #{c['uuid'][:8]}",
            f"Utilise le calendrier #{c['uuid'][:8]}",
        ))
        return c["uuid"]

    # Multiple calendars — interactive selection
    from A.utils.interactive import select_candidate as _sel

    result = _sel(
        calendars,
        columns=[
            {"header": "UUID", "style": "cyan", "width": 10},
            {"header": "URL"},
        ],
        row_formatter=lambda c, i: [
            str(c["uuid"])[:8], str(c.get("url", ""))[:60]
        ],
        prompt_text=tr_multi(
            "Elektu kalendaron por la evento:",
            "Select calendar for the event:",
            "Choisissez le calendrier pour l'événement :",
        ),
    )
    if result is None:
        error(tr_multi(
            "Neniu kalendaro elektita.",
            "No calendar selected.",
            "Aucun calendrier sélectionné.",
        ))
        return None
    _, cal = result
    return cal["uuid"]


def _combine_date_time(
    dato: str,
    komenco: str | None,
    fino: str | None,
    dato_gis: str | None,
) -> tuple[str, str]:
    """Combine date and time strings into ISO 8601 datetimes (UTC).

    ``dato_gis`` is an optional explicit end date for multi-day events.
    When ``fino < komenco`` and no ``dato_gis`` is given, the end date
    is automatically advanced to the next day (cross-midnight).

    Args:
        dato: Start date (YYYYMMDD or YYYY-MM-DD).
        komenco: Start time (HHMM, default ``"0000"``).
        fino: End time (HHMM, default ``"2359"``).
        dato_gis: Optional end date for multi-day events.

    Returns:
        Tuple of (komenco_iso, fino_iso) ISO 8601 strings.

    Raises:
        ValueError: If date or time format is invalid.
    """
    from datetime import datetime as _dt, timedelta

    from A.utils.date import parse_partial_datetime

    dato_clean = dato.strip().replace("-", "")
    km = (komenco or "0000").strip()
    fn = (fino or "2359").strip()

    start_token = f"{dato_clean}_{km}"

    if dato_gis:
        dg = dato_gis.strip().replace("-", "")
        end_token = f"{dg}_{fn}"
    elif fn < km:
        # Cross-midnight — advance end date by one day
        d = _dt.strptime(dato_clean, "%Y%m%d")
        d2 = d + timedelta(days=1)
        end_token = f"{d2.strftime('%Y%m%d')}_{fn}"
    else:
        end_token = f"{dato_clean}_{fn}"

    return (
        parse_partial_datetime(start_token),
        parse_partial_datetime(end_token),
    )


# ── aldoni (event creation) ──────────────────────────────────────────────────


@okazajo_app.command()
def aldoni(
    # Positional arguments (must precede Options in Typer)
    titolo: Optional[str] = typer.Argument(
        None,
        help=tr_multi(
            "Titolo de evento (aŭ superregado por -R).",
            "Event title (or override for -R).",
            "Titre de l'événement (ou remplacement pour -R).",
        ),
    ),
    komenco: Optional[str] = typer.Argument(
        None,
        help=tr_multi(
            "Komenca horo (HHMM, defaŭlte 0000).",
            "Start time (HHMM, default 0000).",
            "Heure de début (HHMM, défaut 0000).",
        ),
    ),
    fino: Optional[str] = typer.Argument(
        None,
        help=tr_multi(
            "Fina horo (HHMM, defaŭlte 2359).",
            "End time (HHMM, default 2359).",
            "Heure de fin (HHMM, défaut 2359).",
        ),
    ),
    # Options
    kalendaro: Optional[str] = typer.Option(
        None, "--kalendaro", "-k",
        help=tr_multi("Kalendaro UUID.", "Calendar UUID.", "UUID du calendrier."),
    ),
    dato: Optional[str] = typer.Option(
        None, "--dato", "-d",
        help=tr_multi(
            "Dato (YYYYMMDD aŭ YYYY-MM-DD).",
            "Date (YYYYMMDD or YYYY-MM-DD).",
            "Date (AAAAMMJJ ou AAAA-MM-JJ).",
        ),
    ),
    dato_gis: Optional[str] = typer.Option(
        None, "--dato-gis",
        help=tr_multi(
            "Fina dato por plurtaga evento.",
            "End date for multi-day event.",
            "Date de fin pour événement multi-jours.",
        ),
    ),
    loko: Optional[str] = typer.Option(
        None, "--loko", "-l",
        help=tr_multi("Loko.", "Location.", "Lieu."),
    ),
    kategorio: Optional[str] = typer.Option(
        None, "--kategorio", "-c",
        help=tr_multi("Kategorio.", "Category.", "Catégorie."),
    ),
    priskribo: Optional[str] = typer.Option(
        None, "--priskribo", "-p",
        help=tr_multi("Priskribo.", "Description.", "Description."),
    ),
    ripeto: Optional[str] = typer.Option(
        None, "--ripeto", "-r",
        help=tr_multi(
            "Ripeto (RRULE). Mallongigoj: daily, weekly, monthly, yearly, "
            "weekdays, weekends. Ekz: FREQ=DAILY, "
            "FREQ=WEEKLY;BYDAY=MO,WE,FR, FREQ=MONTHLY;BYDAY=1MO.",
            "Recurrence (RRULE). Shorthands: daily, weekly, monthly, yearly, "
            "weekdays, weekends. Examples: FREQ=DAILY, "
            "FREQ=WEEKLY;BYDAY=MO,WE,FR, FREQ=MONTHLY;BYDAY=1MO.",
            "Récurrence (RRULE). Raccourcis: daily, weekly, monthly, yearly, "
            "weekdays, weekends. Ex: FREQ=DAILY, "
            "FREQ=WEEKLY;BYDAY=MO,WE,FR, FREQ=MONTHLY;BYDAY=1MO.",
        ),
    ),
    retposto: Optional[list[str]] = typer.Option(
        None, "--retposto", "-R",
        help=tr_multi(
            "Retpoŝtaj mesaĝoj UUID(j) por importi .ics el aldonaĵoj.",
            "Email message UUID(s) to import .ics from attachments.",
            "UUID de messages email pour importer .ics des pièces jointes.",
        ),
    ),
) -> None:
    """Aldoni novan eventon al kalendaro.

    Ekzemploj:
        A okazajo aldoni \"Standup\" 0900 0915 --dato 20260602
        A okazajo aldoni \"All-day\" --dato 20260602
        A okazajo aldoni \"Override\" -R mesaĝa_uuid
    """
    cal_svc = get_kalendaro_service()
    cal_uuid = _resolve_calendar(cal_svc, kalendaro)
    if not cal_uuid:
        raise typer.Exit(1)

    # ── Retposto workflow: import .ics from email attachments ────────────
    if retposto:
        _import_from_retposto(
            cal_uuid=cal_uuid,
            message_uuids=retposto,
            overrides=_build_overrides(
                titolo, loko, kategorio, priskribo, ripeto,
            ),
        )
        return

    # ── Traditional single-event workflow ─────────────────────────────────
    if titolo is None or dato is None:
        error(tr_multi(
            "Bezonata titolo kaj --dato (aŭ uzu --retposto/-R).",
            "Title and --dato required (or use --retposto/-R).",
            "Titre et --dato requis (ou utilisez --retposto/-R).",
        ))
        raise typer.Exit(1)

    try:
        komenco_dt, fino_dt = _combine_date_time(dato, komenco, fino, dato_gis)
    except ValueError as exc:
        error(str(exc))
        raise typer.Exit(1) from exc

    data: dict[str, str] = {
        "kalendaro_uuid": cal_uuid,
        "titolo": titolo.strip(),
        "komenco": komenco_dt,
        "fino": fino_dt,
    }
    if loko:
        data["loko"] = loko.strip()
    if kategorio:
        data["kategorio"] = kategorio.strip()
    if priskribo:
        data["priskribo"] = priskribo.strip()
    if ripeto:
        from A_organizi.cli.okazajo_rrule import normalize_rrule as _norm

        try:
            data["ripeto"] = _norm(ripeto)
        except ValueError as exc:
            error(str(exc))
            raise typer.Exit(1) from exc

    svc = get_evento_service()
    result = svc.create(data)
    info(f"Aldonis eventon #{result['uuid'][:8]}: {titolo}")


# ── Import from sub-modules ──────────────────────────────────────────────────

# Retposto import helpers
from A_organizi.cli.okazajo_retposto import _build_overrides, _import_from_retposto

# CRUD commands (ls, vidi, serci, modifi, forigi, amase_forigi)
from A_organizi.cli.okazajo_crud import register_crud_commands

register_crud_commands(okazajo_app)

# Extended commands (ICS import/export, sync, undo)
from A_organizi.cli.okazajo_util import register_extra_commands

register_extra_commands(okazajo_app)

__all__ = ["okazajo_app"]
