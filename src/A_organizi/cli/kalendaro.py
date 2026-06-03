"""CLI commands for kalendaro (calendar management)."""

from __future__ import annotations

from typing import Optional

import typer

from A import error, info, tr_multi
from A.utils.output import console, print_table

from A_organizi.service.kalendaro import get_kalendaro_service
from A_organizi.utils.sync import (
    http_error,
    http_fetch_text,
    probe_calendar_config,
    remote_http_url,
    set_password,
)


def _short(text: str, limit: int = 40) -> str:
    """Truncate text with ellipsis if longer than limit."""
    if not text:
        return ""
    return text if len(text) <= limit else text[: limit - 1] + "…"


kalendaro_app = typer.Typer(
    name="kalendaro",
    help=tr_multi(
        "Kalendaro — administri kalendarojn.",
        "Kalendaro — manage calendars.",
        "Kalendaro — gérer les calendriers.",
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)


@kalendaro_app.command()
def aldoni(
    url: str = typer.Argument(
        ...,
        help=tr_multi("URL de kalendaro. Ekz: https://example.com/cal.ics", "Calendar URL. E.g. https://example.com/cal.ics", "URL du calendrier. Ex: https://example.com/cal.ics"),
    ),
    uzantnomo: str = typer.Option(
        "",
        "-u",
        "--uzantnomo",
        help=tr_multi("Uzantnomo por fora kalendaro.", "Username for remote calendar.", "Nom d'utilisateur pour calendrier distant."),
    ),
    pasvorto: str = typer.Option(
        "",
        "-p",
        "--pasvorto",
        help=tr_multi("Pasvorto por fora kalendaro.", "Password for remote calendar.", "Mot de passe pour calendrier distant."),
    ),
) -> None:
    """Aldoni kalendaron (loka ICS au fora CalDAV)."""
    svc = get_kalendaro_service()
    if svc.calendar_exists(url, uzantnomo):
        error(tr_multi("Kalendaro jam ekzistas.", "Calendar already exists.", "Calendrier existe déjà."))
        raise typer.Exit(1)

    low_url = url.strip().lower()
    is_remote = low_url.startswith(("http://", "https://", "caldav://"))
    if is_remote:
        if not uzantnomo.strip():
            error(tr_multi("Fora kalendaro bezonas --uzantnomo.", "Remote calendar needs --uzantnomo.", "Calendrier distant nécessite --uzantnomo."))
            raise typer.Exit(1)
        if not pasvorto.strip():
            error(tr_multi("Fora kalendaro bezonas --pasvorto.", "Remote calendar needs --pasvorto.", "Calendrier distant nécessite --pasvorto."))
            raise typer.Exit(1)
        try:
            probe_info = probe_calendar_config(url, uzantnomo, pasvorto)
            info(f"Provo: {probe_info['description']}")
        except ValueError as exc:
            error(f"Ne povis aliri kalendaron: {exc}")
            raise typer.Exit(1)

    data = {
        "url": url.strip(),
        "username": uzantnomo.strip(),
        "remote": 1 if is_remote else 0,
    }
    result = svc.create(data)

    if is_remote and pasvorto.strip():
        try:
            set_password(result["uuid"], pasvorto.strip())
        except Exception as exc:
            error(f"Kalendaro kreita, sed pasvorto ne stokita: {exc}")

    info(f"Aldonis kalendaron #{result['uuid'][:8]}: {url.strip()}")


@kalendaro_app.command("ls")
def ls_kalendaroj() -> None:
    """Listigi kalendarojn."""
    svc = get_kalendaro_service()
    rows = svc.list(order_by="kreita_je", desc=True)
    if not rows:
        info(tr_multi("Neniu kalendaro.", "No calendars.", "Aucun calendrier."))
        return

    processed = [
        {"uuid": str(row["uuid"])[:8], "url": _short(str(row.get("url") or ""), 60)}
        for row in rows
    ]
    print_table(
        [
            {"header": "UUID", "key": "uuid", "style": "cyan", "width": 10},
            {"header": "URL", "key": "url"},
        ],
        processed,
        title=tr_multi("Kalendaroj", "Calendars", "Calendriers"),
    )


@kalendaro_app.command()
def modifi(
    kalendaro_uuid: str = typer.Argument(
        ..., help=tr_multi("UUID de kalendaro.", "Calendar UUID.", "UUID du calendrier."),
    ),
    url: Optional[str] = typer.Option(
        None, "--url", help=tr_multi("Nova URL.", "New URL.", "Nouvelle URL."),
    ),
    uzantnomo: Optional[str] = typer.Option(
        None, "-u", "--uzantnomo", help=tr_multi("Nova uzantnomo.", "New username.", "Nouveau nom d'utilisateur."),
    ),
    pasvorto: Optional[str] = typer.Option(
        None, "-p", "--pasvorto", help=tr_multi("Nova pasvorto (malplena por forigi).", "New password (empty to remove).", "Nouveau mot de passe (vide pour supprimer)."),
    ),
) -> None:
    """Modifi kalendaran agordon lau UUID."""
    if url is None and uzantnomo is None and pasvorto is None:
        error(tr_multi("Uzu almenau --url, --uzantnomo au --pasvorto.", "Use at least --url, --uzantnomo or --pasvorto.", "Utilisez au moins --url, --uzantnomo ou --pasvorto."))
        raise typer.Exit(1)

    svc = get_kalendaro_service()
    resolved = svc.resolve_uuid(kalendaro_uuid)
    if not resolved:
        error(tr_multi(f"Kalendaro ne trovita: {kalendaro_uuid}", f"Calendar not found: {kalendaro_uuid}", f"Calendrier non trouvé: {kalendaro_uuid}"))
        raise typer.Exit(1)

    update: dict[str, str] = {}
    if url is not None:
        low_url = url.strip().lower()
        is_remote = low_url.startswith(("http://", "https://", "caldav://"))
        new_username = uzantnomo.strip() if uzantnomo else ""
        if is_remote and pasvorto:
            status, resp_body = http_fetch_text(remote_http_url(url), new_username, pasvorto)
            if status not in (200, 207, 404):
                error(http_error(status, "Calendar access", resp_body))
                raise typer.Exit(1)
        update["url"] = url.strip()
        update["remote"] = "1" if is_remote else "0"
    if uzantnomo is not None:
        update["username"] = uzantnomo.strip()

    svc.update(resolved, update)

    if pasvorto is not None:
        if pasvorto.strip():
            set_password(resolved, pasvorto.strip())
        else:
            from A_organizi.utils.sync import delete_password
            delete_password(resolved)

    info(f"Modifis kalendaron #{resolved[:8]}.")


@kalendaro_app.command()
def forigi(
    kalendaroj: list[str] = typer.Argument(
        ..., help=tr_multi("Kalendaro UUID(j).", "Calendar UUID(s).", "UUID du calendrier."),
    ),
) -> None:
    """Forigi kalendarojn lau UUID (kaj cxiujn eventojn en ili)."""
    svc = get_kalendaro_service()
    resolved = [uid for ref in kalendaroj if (uid := svc.resolve_uuid(ref))]
    if not resolved:
        error(tr_multi("Neniu valida kalendaro.", "No valid calendar.", "Aucun calendrier valide."))
        raise typer.Exit(1)

    for uid in resolved:
        svc.delete(uid, soft=False)
    info(f"Forigis {len(resolved)} kalendaro(j)n.")


__all__ = ["kalendaro_app"]
