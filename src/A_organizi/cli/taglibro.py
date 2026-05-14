"""CLI commands for taglibro (journal)."""

from __future__ import annotations

from typing import Annotated, Optional

import typer
from rich.table import Table

from A import error, info, tr_multi
from A.utils.output import console
from A.utils.date import parse_partial_datetime
from A.utils.normalize import fold_search_text

from A_organizi.service import get_etikedo_service, get_taglibro_service
from A_organizi.utils.labels import (
    normalize_markdown_links,
    render_markdown_links_plain,
    resolve_reference,
    resolve_etikedo_refs,
)
from A_organizi.utils.markdown import render_markdown_links_plain as render_text

taglibro_app = typer.Typer(
    name="taglibro",
    help=tr_multi(
        "Taglibro — administri taglibrajn enirojn kun etikedoj.",
        "Taglibro — manage journal entries with labels.",
        "Taglibro — gérer des entrées de journal avec étiquettes.",
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)


def _print_results(items: list[dict]) -> None:
    """Print journal entries in a Rich table."""
    table = Table(show_header=True, header_style="bold", box=None)
    table.add_column("UUID", style="cyan", no_wrap=True)
    table.add_column("TEMPO", no_wrap=True)
    table.add_column("TITOLO")
    table.add_column("ETIKEDOJ")
    for item in items:
        etikedoj = ", ".join(
            render_text(text) for _, text in (item.get("etikedoj") or []) if text
        ) or "-"
        table.add_row(
            f"#{str(item.get('uuid') or '')[:8]}",
            str(item.get("tempo", ""))[:16],
            render_text(str(item.get("titolo") or "")),
            etikedoj,
        )
    console.print(table)


def _show_detail(item: dict) -> None:
    """Print full details of a single journal entry."""
    etikedoj = ", ".join(
        render_text(text) for _, text in (item.get("etikedoj") or []) if text
    ) or "-"
    typer.echo(f"uuid: #{str(item.get('uuid') or '')[:8]}")
    typer.echo(
        f"titolo: {render_text(str(item.get('titolo') or ''), show_ref=True)}"
    )
    typer.echo(
        f"priskribo: {render_text(str(item.get('priskribo') or ''), show_ref=True)}"
    )
    typer.echo(f"tempo: {str(item.get('tempo', ''))}")
    typer.echo(f"etikedoj: {etikedoj}")
    typer.echo(f"kreita_je: {str(item.get('kreita_je', ''))}")
    typer.echo(f"modifita_je: {str(item.get('modifita_je', ''))}")


# ── Commands ─────────────────────────────────────────────────────────────────


@taglibro_app.command()
def aldoni(
    titolo: str = typer.Argument(
        ...,
        help='Titolo. Ekz: taglibro aldoni "Hodiaŭ"',
    ),
    priskribo: str = typer.Option(
        "",
        "-p",
        "--priskribo",
        help='Priskribo (markdown). Ekz: -p "Rimarko pri [koncepto](ec#uuid)"',
    ),
    tempo: str | None = typer.Option(
        None,
        "-t",
        "--tempo",
        help=(
            "Tempo en YYYYMMDD_HHMM aŭ parta dato. "
            "Ekz: -t 20260421_0915 aŭ -t 0421_0915"
        ),
    ),
    etikedo: list[str] | None = typer.Option(
        None,
        "-e",
        "--etikedo",
        help=(
            "Etikedo UUID/teksto; ripetu por pluraj. "
            "Ekz: -e #abc123 -e persona"
        ),
    ),
) -> None:
    """Aldoni taglibran eniron."""
    titolo_text = normalize_markdown_links(titolo).strip()
    if not titolo_text:
        error("Malplena titolo ne permesata.")
        raise typer.Exit(1)
    priskribo_text = normalize_markdown_links(priskribo).strip()

    try:
        tempo_iso = parse_partial_datetime(tempo)
    except ValueError as exc:
        error(str(exc))
        raise typer.Exit(1) from exc

    svc = get_taglibro_service()
    etikedo_ids = resolve_etikedo_refs(
        get_etikedo_service().db,
        etikedo,
        interactive=True,
        prompt_on_missing=True,
    )

    data = {
        "titolo": titolo_text,
        "titolo_norm": fold_search_text(titolo_text),
        "priskribo": priskribo_text,
        "priskribo_norm": fold_search_text(priskribo_text),
        "tempo": tempo_iso,
        "etikedo": etikedo_ids,
    }
    result = svc.create(data)
    info(
        f"Aldonis taglibran eniron "
        f"#{result['uuid'][:8]}: {render_text(titolo_text)}"
    )


@taglibro_app.command()
def vidi(
    referenco: str = typer.Argument(
        ...,
        help="Taglibro UUID aŭ titolo. Ekz: taglibro vidi #abc123",
    ),
) -> None:
    """Montri unu taglibran eniron laŭ UUID aŭ titolo."""
    svc = get_taglibro_service()
    entries = svc.list_with_labels(limit=200)
    item = resolve_reference(
        entries,
        referenco,
        text_getter=lambda i: str(i.get("titolo") or ""),
        kind_label="taglibro",
        allow_fuzzy=True,
        interactive=True,
    )
    if item is None:
        error(f"Taglibro-eniro ne trovita: {referenco}")
        raise typer.Exit(1)
    _show_detail(item)


@taglibro_app.command()
def modifi(
    referenco: str = typer.Argument(
        ...,
        help="Taglibro UUID aŭ titolo. Ekz: taglibro modifi #abc --titolo Nova",
    ),
    titolo: str | None = typer.Option(
        None,
        "-T",
        "--titolo",
        help='Nova titolo. Ekz: --titolo "Nova tago"',
    ),
    priskribo: str | None = typer.Option(
        None,
        "-p",
        "--priskribo",
        help='Nova priskribo. Ekz: -p "Vidu [nodo](ec#uuid)"',
    ),
    tempo: str | None = typer.Option(
        None,
        "-t",
        "--tempo",
        help="Nova tempo. Ekz: -t 20260421_0830",
    ),
    etikedo: list[str] | None = typer.Option(
        None,
        "-e",
        "--etikedo",
        help=(
            "Nova etikedo-listo (anstataŭigas); ripetu por pluraj. "
            "Ekz: -e #abc -e grava"
        ),
    ),
) -> None:
    """Modifi ekzistantan taglibran eniron."""
    svc = get_taglibro_service()
    entries = svc.list_with_labels(limit=200)
    item = resolve_reference(
        entries,
        referenco,
        text_getter=lambda i: str(i.get("titolo") or ""),
        kind_label="taglibro",
        allow_fuzzy=True,
        interactive=True,
    )
    if item is None:
        error(f"Taglibro-eniro ne trovita: {referenco}")
        raise typer.Exit(1)

    if all(v is None for v in (titolo, priskribo, tempo, etikedo)):
        error("Nenio por modifi. Uzu almenaŭ unu opcion.")
        raise typer.Exit(1)

    uid = str(item.get("uuid") or "")
    update: dict = {}

    if titolo is not None:
        new_titolo = normalize_markdown_links(titolo).strip()
        if not new_titolo:
            error("Malplena titolo ne permesata.")
            raise typer.Exit(1)
        update["titolo"] = new_titolo
        update["titolo_norm"] = fold_search_text(new_titolo)

    if priskribo is not None:
        update["priskribo"] = normalize_markdown_links(priskribo).strip()
        update["priskribo_norm"] = fold_search_text(update["priskribo"])

    if tempo is not None:
        try:
            update["tempo"] = parse_partial_datetime(tempo)
        except ValueError as exc:
            error(str(exc))
            raise typer.Exit(1) from exc

    if etikedo is not None:
        etikedo_ids = resolve_etikedo_refs(
            get_etikedo_service().db,
            etikedo,
            interactive=True,
            prompt_on_missing=True,
        )
        update["etikedo"] = etikedo_ids

    svc.update(uid, update)
    updated = svc.get_with_labels(uid)
    if updated is None:
        error("Ne povis relegi modifitan eniron.")
        raise typer.Exit(1)
    info(f"Modifis taglibro-eniron #{uid[:8]}.")
    _show_detail(updated)


@taglibro_app.command()
def forigi(
    referencoj: Annotated[list[str], typer.Argument(
        ...,
        help="Taglibro UUID aŭ titolo (pluraj). Ekz: taglibro forigi #abc123 #def456",
    )],
) -> None:
    """Forigi taglibran eniron laŭ UUID aŭ titolo."""
    svc = get_taglibro_service()
    entries = svc.list_with_labels(limit=200)
    item = resolve_reference(
        entries,
        referenco,
        text_getter=lambda i: str(i.get("titolo") or ""),
        kind_label="taglibro",
        allow_fuzzy=True,
        interactive=True,
    )
    if item is None:
        error(f"Taglibro-eniro ne trovita: {referenco}")
        raise typer.Exit(1)

    uid = str(item.get("uuid") or "")
    rendered = render_text(str(item.get("titolo") or ""))
    answer = typer.prompt(
        f"Forigi taglibro-eniron #{uid[:8]} \"{rendered}\"? (j/N)",
        default="N",
    )
    if answer.strip().lower() not in {"j", "jes", "y", "yes"}:
        info("Nuligita.")
        return

    svc.delete(uid, soft=False)
    info(f"Forigis taglibro-eniron #{uid[:8]}.")


@taglibro_app.command()
def serci(
    teksto: str = typer.Argument(
        "",
        help="Serĉa teksto. Ekz: taglibro serci hodiaŭ",
    ),
    titolo: str | None = typer.Option(
        None,
        "--titolo",
        help="Filtri laŭ titolo. Ekz: --titolo ideo",
    ),
    priskribo: str | None = typer.Option(
        None,
        "--priskribo",
        help="Filtri laŭ priskribo. Ekz: --priskribo [vorto](vt#uuid)",
    ),
    etikedo: list[str] | None = typer.Option(
        None,
        "-e",
        "--etikedo",
        help="Filtri laŭ etikedo; ripetu por pluraj. Ekz: -e #abc -e persona",
    ),
    de: str | None = typer.Option(
        None,
        "--de",
        help='Filtri ekde tempo (YYYYMMDD_HHMM). Ekz: --de 20260401',
    ),
    gis: str | None = typer.Option(
        None,
        "--gis",
        help='Filtri ĝis tempo (YYYYMMDD_HHMM). Ekz: --gis 20260430',
    ),
    limo: int = typer.Option(
        50,
        "-lo",
        "--limo",
        help="Maksimumaj rezultoj. Ekz: --limo 20",
    ),
) -> None:
    """Serĉi taglibrajn enirojn per kombineblaj filtriloj."""
    svc = get_taglibro_service()
    etikedo_ids: list[str] = []
    if etikedo:
        etikedo_ids = resolve_etikedo_refs(
            get_etikedo_service().db,
            etikedo,
            interactive=True,
        )

    de_iso: str | None = None
    gis_iso: str | None = None
    ...
        if gis:
            gis_iso = parse_partial_datetime(gis)
    ...
        gis_tempo=gis_iso,
        limit=limo,
    )

    if fuzzy_used:
        info("Neniu preciza rezulto; montrante similajn kongruojn.")
    info(f"{len(results)} rezulto(j) trovita(j).")
    if results:
        _print_results(results)


__all__ = ["taglibro_app"]
