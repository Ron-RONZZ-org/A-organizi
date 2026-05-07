"""CLI commands for okazajo (event management within calendars)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

import typer
from rich.table import Table

from A import error, info, tr_multi
from A.utils.date import parse_partial_date, parse_partial_datetime
from A.utils.output import console, print_table

from A_organizi.service.kalendaro import get_evento_service, get_kalendaro_service

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


# ── Event CRUD ───────────────────────────────────────────────────────────────


@okazajo_app.command()
def aldoni(
    kalendaro: str = typer.Option(
        ..., "--kalendaro", "-k",
        help=tr_multi("Kalendaro UUID.", "Calendar UUID.", "UUID du calendrier."),
    ),
    titolo: str = typer.Option(
        ..., "--titolo", "-t",
        help=tr_multi("Titolo de evento.", "Event title.", "Titre de l'événement."),
    ),
    komenco: str = typer.Option(
        ..., "--komenco",
        help=tr_multi("Komenca dato (YYYYMMDD aŭ YYYY-MM-DD).", "Start date (YYYYMMDD or YYYY-MM-DD).", "Date de début (AAAAMMJJ ou AAAA-MM-JJ)."),
    ),
    fino: str = typer.Option(
        ..., "--fino",
        help=tr_multi("Fina dato (YYYYMMDD aŭ YYYY-MM-DD).", "End date (YYYYMMDD or YYYY-MM-DD).", "Date de fin (AAAAMMJJ ou AAAA-MM-JJ)."),
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
        help=tr_multi("Ripeto (ekz: daily, weekly).", "Recurrence (e.g. daily, weekly).", "Récurrence (ex: daily, weekly)."),
    ),
) -> None:
    """Aldoni novan eventon al kalendaro."""
    cal_svc = get_kalendaro_service()
    cal_uuid = cal_svc.resolve_uuid(kalendaro)
    if not cal_uuid:
        error(tr_multi(f"Kalendaro ne trovita: {kalendaro}", f"Calendar not found: {kalendaro}", f"Calendrier non trouvé: {kalendaro}"))
        raise typer.Exit(1)

    try:
        komenco_dt = parse_partial_datetime(komenco)
        fino_dt = parse_partial_datetime(fino)
    except ValueError as exc:
        error(str(exc))
        raise typer.Exit(1) from exc

    data = {
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
        data["ripeto"] = ripeto.strip()

    svc = get_evento_service()
    result = svc.create(data)
    info(f"Aldonis eventon #{result['uuid'][:8]}: {titolo}")


@okazajo_app.command()
def ls(
    dato1: Optional[str] = typer.Argument(
        None, help=tr_multi("Komenca dato (YYYYMMDD/MMDD/DD).", "Start date (YYYYMMDD/MMDD/DD).", "Date de début (AAAAMMJJ/MMJJ/JJ)."),
    ),
    dato2: Optional[str] = typer.Argument(
        None, help=tr_multi("Fina dato (opcia).", "End date (optional).", "Date de fin (optionnelle)."),
    ),
    kalendaro: Optional[list[str]] = typer.Option(
        None, "-k", "--kalendaro",
        help=tr_multi("Filtri laŭ kalendaro UUID.", "Filter by calendar UUID.", "Filtrer par UUID du calendrier."),
    ),
) -> None:
    """Montri eventojn en datintervalo."""
    today = date.today()
    start = parse_partial_date(dato1, ref=today) if dato1 else today
    end = parse_partial_date(dato2, ref=today) if dato2 else start
    if end < start:
        start, end = end, start

    svc = get_evento_service()
    cal_svc = get_kalendaro_service()
    cal_uuids: list[str] = []
    if kalendaro:
        for ref in kalendaro:
            uid = cal_svc.resolve_uuid(ref)
            if uid:
                cal_uuids.append(uid)

    rows = svc.list_by_date_range(start, end, cal_uuids or None)
    if not rows:
        info(tr_multi("Neniu evento trovita.", "No events found.", "Aucun événement trouvé."))
        return

    table = Table(header_style="dim", border_style="dim")
    table.add_column("UUID", style="cyan", width=10)
    table.add_column("Titolo")
    table.add_column("Dato", width=12)
    table.add_column("Komenco", width=8)
    table.add_column("Fino", width=8)
    table.add_column("Kalendaro", style="dim", width=10)
    for row in rows:
        table.add_row(
            str(row["uuid"])[:8],
            _short(str(row.get("titolo") or ""), 40),
            _fmt_date(str(row["komenco"])),
            _fmt_hhmm(str(row["komenco"])),
            _fmt_hhmm(str(row["fino"])),
            str(row.get("kalendaro_uuid") or "")[:8],
        )
    console.print(table)


@okazajo_app.command()
def vidi(
    eventoj: list[str] = typer.Argument(
        ..., help=tr_multi("UUID(j) de evento(j).", "Event UUID(s).", "UUID de l'événement."),
    ),
) -> None:
    """Montri detalojn de unu au pluraj eventoj."""
    svc = get_evento_service()
    for ref in eventoj:
        uid = svc.resolve_uuid(ref)
        if not uid:
            error(f"Evento ne trovita: {ref}")
            continue
        row = svc.get(uid)
        if not row:
            continue
        console.print(f"|{row['uuid'][:8]}|{_fmt_date(str(row['komenco']))}|"
                      f"{str(row['kalendaro_uuid'])[:8]}|")
        console.print(f"|{_fmt_hhmm(str(row['komenco']))}|{_fmt_hhmm(str(row['fino']))}|")
        console.print(f"|{str(row.get('kategorio') or '')}|{str(row.get('loko') or '')}|")
        console.print(f"|{str(row.get('ripeto') or 'ne')}|")
        console.print(f"|{str(row.get('titolo') or '')}|")
        console.print(f"|{str(row.get('priskribo') or '')}|")
        console.print("")


@okazajo_app.command()
def serci(
    demando: Optional[str] = typer.Argument(
        None, help=tr_multi("Serĉ-demando (titolo/priskribo).", "Search query (title/description).", "Requête de recherche (titre/description)."),
    ),
    kalendaro: Optional[list[str]] = typer.Option(
        None, "-k", "--kalendaro",
        help=tr_multi("Filtri laŭ kalendaro UUID.", "Filter by calendar UUID.", "Filtrer par UUID du calendrier."),
    ),
    kategorio: Optional[str] = typer.Option(
        None, "--kategorio", help=tr_multi("Filtri laŭ kategorio.", "Filter by category.", "Filtrer par catégorie."),
    ),
    loko: Optional[str] = typer.Option(
        None, "--loko", help=tr_multi("Filtri laŭ loko.", "Filter by location.", "Filtrer par lieu."),
    ),
    dato_de: Optional[str] = typer.Option(
        None, "--dato-de", help=tr_multi("Komenca dato (YYYYMMDD).", "Start date (YYYYMMDD).", "Date de début (AAAAMMJJ)."),
    ),
    dato_gxis: Optional[str] = typer.Option(
        None, "--dato-gis", help=tr_multi("Fina dato (YYYYMMDD).", "End date (YYYYMMDD).", "Date de fin (AAAAMMJJ)."),
    ),
    limo: int = typer.Option(
        50, "--limo", "-l", help=tr_multi("Maksimuma nombro da rezultoj.", "Max results.", "Nombre max de résultats."),
    ),
) -> None:
    """Serĉi eventojn kun kombineblaj filtriloj."""
    svc = get_evento_service()

    de_iso: Optional[str] = None
    gxis_iso: Optional[str] = None
    try:
        if dato_de:
            de_iso = parse_partial_datetime(dato_de)
        if dato_gxis:
            gxis_iso = parse_partial_datetime(dato_gxis)
    except ValueError as exc:
        error(str(exc))
        raise typer.Exit(1) from exc

    results = svc.search(
        query=demando,
        kalendaro=kalendaro,
        kategorio=kategorio,
        loko=loko,
        dato_de=de_iso,
        dato_gxis=gxis_iso,
        limit=limo,
    )

    if not results:
        info(tr_multi("Neniu rezulto.", "No results.", "Aucun résultat."))
        return

    table = Table(header_style="dim", border_style="dim")
    table.add_column("UUID", style="cyan", width=10)
    table.add_column("Titolo")
    table.add_column("Dato", width=12)
    table.add_column("Komenco", width=8)
    table.add_column("Fino", width=8)
    table.add_column("Kalendaro", style="dim", width=10)
    for row in results:
        table.add_row(
            str(row["uuid"])[:8],
            _short(str(row.get("titolo") or ""), 40),
            _fmt_date(str(row["komenco"])),
            _fmt_hhmm(str(row["komenco"])),
            _fmt_hhmm(str(row["fino"])),
            str(row.get("kalendaro_uuid") or "")[:8],
        )
    console.print(table)


@okazajo_app.command()
def modifi(
    evento_uuid: str = typer.Argument(
        ..., help=tr_multi("UUID de evento.", "Event UUID.", "UUID de l'événement."),
    ),
    titolo: Optional[str] = typer.Option(
        None, "--titolo", "-t", help=tr_multi("Nova titolo.", "New title.", "Nouveau titre."),
    ),
    komenco: Optional[str] = typer.Option(
        None, "--komenco", help=tr_multi("Nova komenca dato (YYYYMMDD).", "New start date (YYYYMMDD).", "Nouvelle date de début (AAAAMMJJ)."),
    ),
    fino: Optional[str] = typer.Option(
        None, "--fino", help=tr_multi("Nova fina dato (YYYYMMDD).", "New end date (YYYYMMDD).", "Nouvelle date de fin (AAAAMMJJ)."),
    ),
    loko: Optional[str] = typer.Option(
        None, "--loko", "-l", help=tr_multi("Nova loko.", "New location.", "Nouveau lieu."),
    ),
    kategorio: Optional[str] = typer.Option(
        None, "--kategorio", "-c", help=tr_multi("Nova kategorio.", "New category.", "Nouvelle catégorie."),
    ),
    priskribo: Optional[str] = typer.Option(
        None, "--priskribo", "-p", help=tr_multi("Nova priskribo.", "New description.", "Nouvelle description."),
    ),
    kalendaro: Optional[str] = typer.Option(
        None, "--kalendaro", "-k", help=tr_multi("Nova kalendaro UUID.", "New calendar UUID.", "Nouvel UUID du calendrier."),
    ),
) -> None:
    """Modifi eventon laŭ UUID."""
    svc = get_evento_service()
    uid = svc.resolve_uuid(evento_uuid)
    if not uid:
        error(tr_multi(f"Evento ne trovita: {evento_uuid}", f"Event not found: {evento_uuid}", f"Événement non trouvé: {evento_uuid}"))
        raise typer.Exit(1)

    data: dict[str, str] = {}
    if titolo is not None:
        data["titolo"] = titolo.strip()
    if komenco is not None:
        try:
            data["komenco"] = parse_partial_datetime(komenco)
        except ValueError as exc:
            error(str(exc))
            raise typer.Exit(1) from exc
    if fino is not None:
        try:
            data["fino"] = parse_partial_datetime(fino)
        except ValueError as exc:
            error(str(exc))
            raise typer.Exit(1) from exc
    if loko is not None:
        data["loko"] = loko.strip()
    if kategorio is not None:
        data["kategorio"] = kategorio.strip()
    if priskribo is not None:
        data["priskribo"] = priskribo.strip()
    if kalendaro is not None:
        cal_svc = get_kalendaro_service()
        cal_uid = cal_svc.resolve_uuid(kalendaro)
        if not cal_uid:
            error(tr_multi(f"Kalendaro ne trovita: {kalendaro}", f"Calendar not found: {kalendaro}", f"Calendrier non trouvé: {kalendaro}"))
            raise typer.Exit(1)
        data["kalendaro_uuid"] = cal_uid

    if not data:
        error(tr_multi("Neniu ŝanĝo specifita.", "No change specified.", "Aucun changement spécifié."))
        raise typer.Exit(1)

    svc.update(uid, data)
    info(f"Modifis eventon #{uid[:8]}.")


@okazajo_app.command()
def forigi(
    eventoj: list[str] = typer.Argument(
        ..., help=tr_multi("Evento UUID(j) por forigi.", "Event UUID(s) to delete.", "UUID de l'événement à supprimer."),
    ),
) -> None:
    """Forigi eventojn laŭ UUID."""
    svc = get_evento_service()
    uuids: list[str] = []
    for ref in eventoj:
        uid = svc.resolve_uuid(ref)
        if uid:
            uuids.append(uid)
    if not uuids:
        error(tr_multi("Neniu valida evento.", "No valid event.", "Aucun événement valide."))
        raise typer.Exit(1)

    rows = [svc.get(uid) for uid in uuids if svc.get(uid)]
    for row in rows[:10]:
        console.print(f" - #{row['uuid'][:8]} {_fmt_date(str(row['komenco']))} {str(row.get('titolo') or '')}")
    answer = typer.prompt(tr_multi("Ĉu daŭrigi? (j/N)", "Continue? (j/N)", "Continuer ? (j/N)"), default="N")
    if answer.strip().lower() not in {"j", "jes", "y", "yes"}:
        info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
        return

    for uid in uuids:
        svc.delete(uid, soft=False)
    info(f"Forigis {len(uuids)} evento(j)n.")


# ── Bulk operations ──────────────────────────────────────────────────────────


@okazajo_app.command()
def amase_forigi(
    dato1: str = typer.Argument(..., help=tr_multi("Komenca dato (YYYYMMDD).", "Start date (YYYYMMDD).", "Date de début (AAAAMMJJ).")),
    dato2: str = typer.Argument(..., help=tr_multi("Fina dato (YYYYMMDD).", "End date (YYYYMMDD).", "Date de fin (AAAAMMJJ).")),
    kalendaro: Optional[list[str]] = typer.Option(
        None, "-k", "--kalendaro",
        help=tr_multi("Filtri laŭ kalendaro UUID.", "Filter by calendar UUID.", "Filtrer par UUID du calendrier."),
    ),
) -> None:
    """Forigi eventojn en intervalo."""
    today = date.today()
    start = parse_partial_date(dato1, ref=today)
    end = parse_partial_date(dato2, ref=today)
    if end < start:
        start, end = end, start

    svc = get_evento_service()
    cal_svc = get_kalendaro_service()
    cal_uuids: list[str] = []
    if kalendaro:
        for ref in kalendaro:
            uid = cal_svc.resolve_uuid(ref)
            if uid:
                cal_uuids.append(uid)

    preview = svc.list_by_date_range(start, end, cal_uuids or None)
    if not preview:
        info(tr_multi("Neniu evento trovita.", "No events found.", "Aucun événement trouvé."))
        return

    for row in preview[:10]:
        console.print(f" - #{row['uuid'][:8]} {_fmt_date(str(row['komenco']))} {str(row.get('titolo') or '')}")
    answer = typer.prompt(tr_multi("Ĉu daŭrigi? (j/N)", "Continue? (j/N)", "Continuer ? (j/N)"), default="N")
    if answer.strip().lower() not in {"j", "jes", "y", "yes"}:
        info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
        return

    deleted = svc.delete_by_date_range(start, end, cal_uuids or None)
    info(f"Forigis {deleted} evento(j)n.")


# Register extended commands (ICS import/export, sync, undo)
from A_organizi.cli.okazajo_extra import register_extra_commands

register_extra_commands(okazajo_app)

__all__ = ["okazajo_app"]
