"""CLI commands for kalendaro (calendars and events)."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import typer
from rich.table import Table

from A import error, info, tr_multi
from A.utils.date import parse_partial_date, parse_partial_datetime
from A.utils.output import console

from A_organizi.service.kalendaro import get_evento_service, get_kalendaro_service
from A_organizi.utils.ics import events_to_ics, insert_ics_events

kalendaro_app = typer.Typer(
    name="kalendaro",
    help=tr_multi(
        "Kalendaro — administri kalendarojn kaj eventojn.",
        "Kalendaro — manage calendars and events.",
        "Kalendaro — gérer calendriers et événements.",
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


# ── Calendar management ──────────────────────────────────────────────────────


@kalendaro_app.command()
def aldoni(
    url: str = typer.Argument(
        ...,
        help="URL de kalendaro. Ekz: https://example.com/cal.ics",
    ),
    uzantnomo: str = typer.Option(
        "",
        "-u",
        "--uzantnomo",
        help="Uzantnomo por fora kalendaro. Ekz: -u alice",
    ),
) -> None:
    """Aldoni kalendaron (loka ICS aŭ fora CalDAV)."""
    svc = get_kalendaro_service()
    if svc.calendar_exists(url, uzantnomo):
        error("Kalendaro jam ekzistas kun sama URL kaj uzantnomo.")
        raise typer.Exit(1)

    # Validate: if remote URL, username is required
    low_url = url.strip().lower()
    is_remote = low_url.startswith(("http://", "https://", "caldav://"))
    if is_remote and not uzantnomo.strip():
        error("Fora kalendaro bezonas --uzantnomo.")
        raise typer.Exit(1)

    data = {
        "url": url.strip(),
        "username": uzantnomo.strip(),
        "remote": 1 if is_remote else 0,
    }
    result = svc.create(data)
    info(f"Aldonis kalendaron #{result['uuid'][:8]}: {url.strip()}")


@kalendaro_app.command()
def ls_kalendaroj() -> None:
    """Listigi kalendarojn."""
    svc = get_kalendaro_service()
    rows = svc.list(order_by="kreita_je", desc=True)
    if not rows:
        info("Neniu kalendaro.")
        return
    table = Table(header_style="dim", border_style="dim")
    table.add_column("UUID", style="cyan", width=10)
    table.add_column("URL")
    for row in rows:
        table.add_row(
            str(row["uuid"])[:8],
            _short(str(row.get("url") or ""), 60),
        )
    console.print(table)


@kalendaro_app.command()
def modifi(
    kalendaro_uuid: str = typer.Argument(
        ...,
        help="UUID de kalendaro. Ekz: abcdef12",
    ),
    url: str | None = typer.Option(
        None,
        "--url",
        help="Nova URL. Ekz: --url https://example.com/nova.ics",
    ),
    uzantnomo: str | None = typer.Option(
        None,
        "-u",
        "--uzantnomo",
        help="Nova uzantnomo. Ekz: -u bob",
    ),
) -> None:
    """Modifi kalendaran agordon laŭ UUID."""
    if url is None and uzantnomo is None:
        error("Uzu almenaŭ --url aŭ --uzantnomo.")
        raise typer.Exit(1)

    svc = get_kalendaro_service()
    resolved = svc.resolve_uuid(kalendaro_uuid)
    if resolved is None:
        error(f"Kalendaro ne trovita: {kalendaro_uuid}")
        raise typer.Exit(1)

    update: dict[str, str] = {}
    if url is not None:
        update["url"] = url.strip()
    if uzantnomo is not None:
        update["username"] = uzantnomo.strip()

    svc.update(resolved, update)
    info(f"Modifis kalendaron #{resolved[:8]}.")


@kalendaro_app.command()
def forigi_kalendaro(
    kalendaroj: list[str] = typer.Argument(
        ...,
        help="Kalendaro UUID(j). Ekz: abcdef12",
    ),
) -> None:
    """Forigi kalendarojn laŭ UUID (kaj ĉiujn eventojn en ili)."""
    svc = get_kalendaro_service()
    resolved: list[str] = []
    for ref in kalendaroj:
        uid = svc.resolve_uuid(ref)
        if uid:
            resolved.append(uid)
    if not resolved:
        error("Neniu valida kalendaro por forigi.")
        raise typer.Exit(1)

    for uid in resolved:
        svc.delete(uid, soft=False)
    info(f"Forigis {len(resolved)} kalendaro(j)n.")


# ──────────────────────────────────────────────────────────────────────────────
# Event commands
# ──────────────────────────────────────────────────────────────────────────────


@kalendaro_app.command()
def ls(
    dato1: str | None = typer.Argument(None, help="Komenca dato (YYYYMMDD/MMDD/DD)."),
    dato2: str | None = typer.Argument(None, help="Fina dato (opcia)."),
    kalendaro: list[str] | None = typer.Option(
        None, "-k", "--kalendaro", help="Filtri laŭ kalendaro UUID."
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
        info("Neniu evento trovita.")
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


@kalendaro_app.command()
def vidi(
    eventoj: list[str] = typer.Argument(
        ..., help="UUID(j) de evento(j). Ekz: abcdef12"
    ),
) -> None:
    """Montri detalojn de unu aŭ pluraj eventoj."""
    svc = get_evento_service()
    for ref in eventoj:
        uid = svc.resolve_uuid(ref)
        if not uid:
            error(f"Evento ne trovita: {ref}")
            continue
        row = svc.get(uid)
        if not row:
            continue
        typer.echo(f"|{row['uuid'][:8]}|{_fmt_date(str(row['komenco']))}|"
                   f"{str(row['kalendaro_uuid'])[:8]}|")
        typer.echo(f"|{_fmt_hhmm(str(row['komenco']))}|{_fmt_hhmm(str(row['fino']))}|")
        typer.echo(f"|{str(row.get('kategorio') or '')}|{str(row.get('loko') or '')}|")
        typer.echo(f"|{str(row.get('ripeto') or 'ne')}|")
        typer.echo(f"|{str(row.get('titolo') or '')}|")
        typer.echo(f"|{str(row.get('priskribo') or '')}|")
        typer.echo("")


@kalendaro_app.command()
def serci(
    demando: str | None = typer.Argument(
        None, help="Serĉ-demando (titolo/priskribo)."
    ),
    kalendaro: list[str] | None = typer.Option(
        None, "-k", "--kalendaro", help="Filtri laŭ kalendaro UUID."
    ),
    kategorio: str | None = typer.Option(
        None, "--kategorio", help="Filtri laŭ kategorio."
    ),
    loko: str | None = typer.Option(None, "--loko", help="Filtri laŭ loko."),
    dato_de: str | None = typer.Option(
        None, "--dato-de", help="Komenca dato (YYYYMMDD)."
    ),
    dato_gxis: str | None = typer.Option(
        None, "--dato-gis", help="Fina dato (YYYYMMDD)."
    ),
    limo: int = typer.Option(
        50, "-lo", "--limo", help="Maksimuma nombro da rezultoj."
    ),
) -> None:
    """Serĉi eventojn kun kombineblaj filtriloj."""
    svc = get_evento_service()

    de_iso: str | None = None
    gxis_iso: str | None = None
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

    info(f"{len(results)} rezulto(j) trovita(j).")
    if not results:
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


@kalendaro_app.command()
def forigi(
    eventoj: list[str] = typer.Argument(
        ..., help="Evento UUID(j) por forigi."
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
        error("Neniu valida evento por forigi.")
        raise typer.Exit(1)

    # Confirm
    rows = [svc.get(uid) for uid in uuids if svc.get(uid)]
    typer.echo(f"Trafitaj eventoj: {len(rows)}")
    for row in rows[:10]:
        typer.echo(
            f" - #{row['uuid'][:8]} "
            f"{_fmt_date(str(row['komenco']))} "
            f"{str(row.get('titolo') or '')}"
        )
    answer = typer.prompt("Ĉu daŭrigi? (j/N)", default="N")
    if answer.strip().lower() not in {"j", "jes", "y", "yes"}:
        info("Nuligita.")
        return

    for uid in uuids:
        svc.delete(uid, soft=False)
    info(f"Forigis {len(uuids)} evento(j)n.")


@kalendaro_app.command()
def amase_forigi(
    dato1: str = typer.Argument(..., help="Komenca dato (YYYYMMDD)."),
    dato2: str = typer.Argument(..., help="Fina dato (YYYYMMDD)."),
    kalendaro: list[str] | None = typer.Option(
        None, "-k", "--kalendaro", help="Filtri laŭ kalendaro UUID."
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

    # Preview
    preview = svc.list_by_date_range(start, end, cal_uuids or None)
    if not preview:
        info("Neniu evento trovita.")
        return
    typer.echo(f"Trafitaj eventoj: {len(preview)}")
    for row in preview[:10]:
        typer.echo(
            f" - #{row['uuid'][:8]} "
            f"{_fmt_date(str(row['komenco']))} "
            f"{str(row.get('titolo') or '')}"
        )
    answer = typer.prompt("Ĉu daŭrigi? (j/N)", default="N")
    if answer.strip().lower() not in {"j", "jes", "y", "yes"}:
        info("Nuligita.")
        return

    deleted = svc.delete_by_date_range(start, end, cal_uuids or None)
    info(f"Forigis {deleted} evento(j)n.")


# ──────────────────────────────────────────────────────────────────────────────
# ICS import / export
# ──────────────────────────────────────────────────────────────────────────────


@kalendaro_app.command()
def importi(
    kalendaro_uuid: str = typer.Argument(
        ..., help="Kalendaro UUID."
    ),
    dosieroj: list[str] = typer.Argument(
        ..., help="ICS-dosiero(j)."
    ),
) -> None:
    """Importi ICS-dosierojn en kalendaron."""
    cal_svc = get_kalendaro_service()
    resolved_cal = cal_svc.resolve_uuid(kalendaro_uuid)
    if not resolved_cal:
        error("Kalendaro ne trovita.")
        raise typer.Exit(1)

    db = get_evento_service().db
    added: list[str] = []
    for file_path in dosieroj:
        text = Path(file_path).read_text(encoding="utf-8")
        added.extend(insert_ics_events(db, resolved_cal, text))

    info(f"Importis {len(added)} evento(j)n.")


@kalendaro_app.command()
def eksporti(
    argumentoj: list[str] = typer.Argument(
        None, help="Evento UUID(j) aŭ opciaj limdatoj (YYYYMMDD/MMDD/DD)."
    ),
    kalendaro: list[str] | None = typer.Option(
        None, "-k", "--kalendaro", help="Kalendaro UUID(j) por intervala eksporto."
    ),
    dosiero: str | None = typer.Option(
        None, "-d", "--dosiero", help="Cela .ics dosiero."
    ),
) -> None:
    """Eksporti eventojn laŭ UUID aŭ laŭ kalendaro+datoj."""
    args = argumentoj or []
    date_tokens: list[str] = []
    refs: list[str] = []
    for token in args:
        if token.isdigit() and len(token) in (2, 4, 8):
            date_tokens.append(token)
        else:
            refs.append(token)

    svc = get_evento_service()
    cal_svc = get_kalendaro_service()
    rows: list[dict] = []

    if refs:
        for ref in refs:
            uid = svc.resolve_uuid(ref)
            if uid:
                row = svc.get(uid)
                if row:
                    rows.append(row)
    else:
        today = date.today()
        s_token = date_tokens[0] if date_tokens else None
        e_token = date_tokens[1] if len(date_tokens) > 1 else None
        start = parse_partial_date(s_token, ref=today) if s_token else today
        end = parse_partial_date(e_token, ref=today) if e_token else start
        if end < start:
            start, end = end, start

        cal_uuids: list[str] = []
        if kalendaro:
            for ref in kalendaro:
                uid = cal_svc.resolve_uuid(ref)
                if uid:
                    cal_uuids.append(uid)

        results = svc.list_by_date_range(start, end, cal_uuids or None)
        rows = list(results)

    payload = events_to_ics(rows)
    if dosiero:
        path = Path(dosiero)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
        info(f"Eksportis {len(rows)} evento(j)n al {dosiero}")
    else:
        typer.echo(payload.rstrip("\n"))


__all__ = ["kalendaro_app"]
