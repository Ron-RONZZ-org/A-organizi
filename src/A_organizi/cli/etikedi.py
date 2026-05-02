"""CLI commands for etikedoj (shared labels)."""

from __future__ import annotations

import typer
from rich.table import Table

from A import error, info, tr_multi
from A.utils.output import console
from A_organizi.service import get_etikedo_service
from A_organizi.utils.labels import list_etikedoj, resolve_reference
from A_organizi.utils.markdown import render_markdown_links_plain

etikedoj_app = typer.Typer(
    name="etikedo",
    help=tr_multi(
        "Etikedo — administri etikedojn (labelojn).",
        "Etikedo — manage labels.",
        "Etikedo — gérer des étiquettes.",
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)


def _render_text(text: str, *, show_ref: bool = False) -> str:
    """Render markdown text for display."""
    return render_markdown_links_plain(text, show_ref=show_ref)


def _show_detail(item: dict) -> None:
    """Print full details of a single label."""
    typer.echo(f"uuid: {item['uuid']}")
    typer.echo(
        f"teksto: {_render_text(str(item.get('teksto') or ''), show_ref=True)}"
    )
    typer.echo(f"teksto_norm: {item.get('teksto_norm', '')}")
    typer.echo(f"koloro: {item.get('koloro', '') or '-'}")
    typer.echo(f"kreita_je: {item.get('kreita_je', '')}")
    typer.echo(f"modifita_je: {item.get('modifita_je', '')}")


def _print_results(items: list[dict]) -> None:
    """Print labels in a Rich table."""
    table = Table(show_header=True, header_style="bold", box=None)
    table.add_column("UUID", style="cyan", no_wrap=True)
    table.add_column("TEKSTO")
    table.add_column("KOLORO")
    for item in items:
        table.add_row(
            f"#{str(item.get('uuid') or '')[:8]}",
            _render_text(str(item.get("teksto") or "")),
            str(item.get("koloro") or ""),
        )
    console.print(table)


# ── Commands ─────────────────────────────────────────────────────────────────


@etikedoj_app.command()
def aldoni(
    teksto: str = typer.Argument(
        ...,
        help=(
            "Etikeda teksto (subtenas Markdown-ligilojn). "
            "Ekz: etikedo aldoni urga"
        ),
    ),
    koloro: str = typer.Option(
        "",
        "-k",
        "--koloro",
        help='Kolorkodo (ekz: "#ff0000"). Ekz: -k "#ff0000"',
    ),
) -> None:
    """Aldoni novan etikedon."""
    svc = get_etikedo_service()
    data = {"teksto": teksto.strip(), "koloro": koloro.strip()}
    try:
        result = svc.create(data)
    except Exception as exc:
        error(f"Ne povis aldoni etikedon: {exc}")
        raise typer.Exit(1) from exc
    rendered = _render_text(result["teksto"], show_ref=True)
    info(f"Aldonis etikedon: {rendered}")


@etikedoj_app.command()
def vidi(
    referenco: str = typer.Argument(
        ...,
        help="Etikedo UUID aŭ teksto. Ekz: etikedo vidi urga",
    ),
) -> None:
    """Montri unu etikedon laŭ UUID aŭ teksto."""
    db = get_etikedo_service().db
    labels = list_etikedoj(db)
    item = resolve_reference(
        labels,
        referenco,
        text_getter=lambda i: str(i.get("teksto") or ""),
        kind_label="etikedo",
        allow_fuzzy=True,
        interactive=True,
    )
    if item is None:
        error(f"Etikedo ne trovita: {referenco}")
        raise typer.Exit(1)
    _show_detail(item)


@etikedoj_app.command()
def modifi(
    referenco: str = typer.Argument(
        ...,
        help="Etikedo UUID aŭ teksto. Ekz: etikedo modifi urga nova_teksto",
    ),
    teksto: str = typer.Argument(
        ...,
        help="Nova etikeda teksto. Ekz: etikedo modifi urga tre_urga",
    ),
    koloro: str = typer.Option(
        None,
        "-k",
        "--koloro",
        help='Nova kolorkodo. Ekz: -k "#00ff00"',
    ),
) -> None:
    """Modifi ekzistantan etikedon."""
    svc = get_etikedo_service()
    db = svc.db
    labels = list_etikedoj(db)
    item = resolve_reference(
        labels,
        referenco,
        text_getter=lambda i: str(i.get("teksto") or ""),
        kind_label="etikedo",
        allow_fuzzy=True,
        interactive=True,
    )
    if item is None:
        error(f"Etikedo ne trovita: {referenco}")
        raise typer.Exit(1)

    update: dict[str, str] = {"teksto": teksto.strip()}
    if koloro is not None:
        update["koloro"] = koloro.strip()

    try:
        svc.update(str(item["uuid"]), update)
    except Exception as exc:
        error(f"Ne povis modifi etikedon: {exc}")
        raise typer.Exit(1) from exc

    info(f"Modifis etikedon: #{str(item['uuid'])[:8]}")


@etikedoj_app.command()
def forigi(
    referenco: str = typer.Argument(
        ...,
        help="Etikedo UUID aŭ teksto. Ekz: etikedo forigi urga",
    ),
) -> None:
    """Forigi etikedon laŭ UUID aŭ teksto."""
    svc = get_etikedo_service()
    db = svc.db
    labels = list_etikedoj(db)
    item = resolve_reference(
        labels,
        referenco,
        text_getter=lambda i: str(i.get("teksto") or ""),
        kind_label="etikedo",
        allow_fuzzy=True,
        interactive=True,
    )
    if item is None:
        error(f"Etikedo ne trovita: {referenco}")
        raise typer.Exit(1)

    uid = str(item["uuid"])
    rendered = _render_text(str(item.get("teksto") or ""))
    answer = typer.prompt(
        f"Forigi etikedon #{uid[:8]} \"{rendered}\"? (j/N)",
        default="N",
    )
    if answer.strip().lower() not in {"j", "jes", "y", "yes"}:
        info("Nuligita.")
        return

    # Hard-delete labels (no soft-delete — labels are shared references)
    svc.delete(uid, soft=False)
    info(f"Forigis etikedon: #{uid[:8]}")


@etikedoj_app.command()
def serci(
    teksto: str | None = typer.Argument(
        None,
        help="Serĉa teksto. Ekz: etikedo serci urga",
    ),
    limo: int = typer.Option(
        50,
        "-lo",
        "--limo",
        help="Maksimumaj rezultoj. Ekz: --limo 20",
    ),
) -> None:
    """Serĉi etikedojn laŭ teksto."""
    svc = get_etikedo_service()
    if teksto:
        results = svc.search("teksto", teksto, case_sensitive=False)
        # Also search in teksto_norm for normalized matching
        norm_results = svc.search("teksto_norm", teksto, case_sensitive=False)
        seen: set[str] = set()
        combined: list[dict] = []
        for item in [*results, *norm_results]:
            uid = str(item.get("uuid") or "")
            if uid not in seen:
                seen.add(uid)
                combined.append(item)
        results = combined[:limo]
    else:
        results = svc.list(order_by="teksto", desc=False, limit=limo)

    info(f"Rezultoj: {len(results)}")
    if results:
        _print_results(results)


__all__ = ["etikedoj_app"]
