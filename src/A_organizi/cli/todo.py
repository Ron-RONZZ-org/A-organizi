"""CLI commands for todo (tasks)."""

from __future__ import annotations

import typer

from A import error, info, tr_multi, tr_multi
from A.utils.output import console, print_table
from A.utils.normalize import fold_search_text

from A_organizi.priority import (
    compute_priority,
    format_priority,
    priority_filter_description,
    validate_formula,
)
from A_organizi.service import get_etikedo_service, get_todo_service
from A_organizi.utils.labels import (
    normalize_markdown_links,
    render_markdown_links_plain as render_text,
    resolve_etikedo_refs,
    resolve_reference,
)

todo_app = typer.Typer(
    name="todo",
    help=tr_multi(
        "Todo — administri taskojn kun etikedoj kaj prioritato.",
        "Todo — manage tasks with labels and priority.",
        "Todo — gérer des tâches avec étiquettes et priorité.",
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)


def _print_results(items: list[dict]) -> None:
    """Print tasks using A-core generic table utility."""
    # Pre-process data for table display
    rows = []
    for item in items:
        priority = format_priority(
            str(item.get("prioritato") or "0"),
            str(item.get("kreita_je") or ""),
        )
        etikedoj = ", ".join(
            render_text(text) for _, text in (item.get("etikedoj") or []) if text
        ) or "-"
        rows.append({
            "uuid": f"#{str(item.get('uuid') or '')[:8]}",
            "titolo": render_text(str(item.get("titolo") or "")),
            "prioritato": priority,
            "stato": str(item.get("stato") or ""),
            "etikedoj": etikedoj,
        })

    columns = [
        {"header": "UUID", "key": "uuid", "style": "cyan", "no_wrap": True},
        {"header": "TITOLO", "key": "titolo"},
        {"header": "PRIORITATO", "key": "prioritato", "no_wrap": True},
        {"header": "STATO", "key": "stato", "no_wrap": True},
        {"header": "ETIKEDOJ", "key": "etikedoj"},
    ]

    print_table(columns, rows, title=tr_multi("Todoj", "Tasks", "Tâches"))


def _show_detail(item: dict) -> None:
    """Print full details of a single task."""
    priority = format_priority(
        str(item.get("prioritato") or "0"),
        str(item.get("kreita_je") or ""),
    )
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
    typer.echo(f"stato: {str(item.get('stato') or '')}")
    typer.echo(f"prioritato: {priority}")
    typer.echo(f"etikedoj: {etikedoj}")
    typer.echo(f"kreita_je: {str(item.get('kreita_je', ''))}")
    typer.echo(f"modifita_je: {str(item.get('modifita_je', ''))}")


# ── Commands ─────────────────────────────────────────────────────────────────


@todo_app.command()
def aldoni(
    titolo: str = typer.Argument(
        ...,
        help='Titolo. Ekz: todo aldoni "Legi libron"',
    ),
    priskribo: str = typer.Option(
        "",
        "-p",
        "--priskribo",
        help='Priskribo (markdown). Ekz: -p "Vidu [temon](ec#uuid)"',
    ),
    prioritato: str = typer.Option(
        "0",
        "-P",
        "--prioritato",
        help=priority_filter_description(),
    ),
    stato: str = typer.Option(
        "malfermita",
        "-s",
        "--stato",
        help=(
            "Komenca stato. "
            "Validaj valoroj: malfermita, farita, prokrastita, nuligita. "
            "Ekz: -s malfermita"
        ),
    ),
    etikedo: list[str] | None = typer.Option(
        None,
        "-e",
        "--etikedo",
        help=(
            "Etikedo UUID/teksto; ripetu por pluraj. "
            "Ekz: -e #abc -e urga"
        ),
    ),
) -> None:
    """Aldoni novan taskon."""
    titolo_text = normalize_markdown_links(titolo).strip()
    if not titolo_text:
        error("Malplena titolo ne permesata.")
        raise typer.Exit(1)
    priskribo_text = normalize_markdown_links(priskribo).strip()

    # Validate priority formula
    if not validate_formula(prioritato):
        error(f"Nevalida prioritata formulo: {prioritato!r}")
        raise typer.Exit(1)

    svc = get_todo_service()
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
        "prioritato": prioritato.strip(),
        "stato": stato,
        "etikedo": etikedo_ids,
    }
    try:
        result = svc.create(data)
    except ValueError as exc:
        error(str(exc))
        raise typer.Exit(1) from exc

    info(
        f"Aldonis todo #{result['uuid'][:8]}: "
        f"{render_text(titolo_text, show_ref=True)}"
    )


@todo_app.command()
def vidi(
    referenco: str = typer.Argument(
        ...,
        help=tr_multi("Todo UUID aŭ titolo. Ekz: todo vidi #abc123", "Todo UUID or title. E.g. todo view #abc123", "UUID ou titre du todo. Ex: todo voir #abc123"),
    ),
) -> None:
    """Montri unu taskon laŭ UUID aŭ titolo."""
    svc = get_todo_service()
    entries = svc.list_with_labels(limit=200)
    item = resolve_reference(
        entries,
        referenco,
        text_getter=lambda i: str(i.get("titolo") or ""),
        kind_label="todo",
        allow_fuzzy=True,
        interactive=True,
    )
    if item is None:
        error(f"Todo ne trovita: {referenco}")
        raise typer.Exit(1)
    _show_detail(item)


@todo_app.command()
def modifi(
    referenco: str = typer.Argument(
        ...,
        help=tr_multi("Todo UUID aŭ titolo. Ekz: todo modifi #abc --stato farita", "Todo UUID or title. E.g. todo modify #abc --stato farita", "UUID ou titre du todo. Ex: todo modifier #abc --stato farita"),
    ),
    titolo: str | None = typer.Option(
        None,
        "-T",
        "--titolo",
        help='Nova titolo. Ekz: --titolo "Fini raporton"',
    ),
    priskribo: str | None = typer.Option(
        None,
        "-p",
        "--priskribo",
        help='Nova priskribo. Ekz: -p "Vidu [noto](vt#uuid)"',
    ),
    prioritato: str | None = typer.Option(
        None,
        "-P",
        "--prioritato",
        help='Nova prioritato. Ekz: -P "30 + 5 * (H - 10)"',
    ),
    stato: str | None = typer.Option(
        None,
        "-s",
        "--stato",
        help=(
            "Nova stato. Validaj: malfermita, farita, prokrastita, nuligita. "
            "Ekz: -s farita"
        ),
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
    """Modifi ekzistantan taskon."""
    svc = get_todo_service()
    entries = svc.list_with_labels(limit=200)
    item = resolve_reference(
        entries,
        referenco,
        text_getter=lambda i: str(i.get("titolo") or ""),
        kind_label="todo",
        allow_fuzzy=True,
        interactive=True,
    )
    if item is None:
        error(f"Todo ne trovita: {referenco}")
        raise typer.Exit(1)

    if all(
        v is None
        for v in (titolo, priskribo, prioritato, stato, etikedo)
    ):
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

    if prioritato is not None:
        if not validate_formula(prioritato):
            error(f"Nevalida prioritata formulo: {prioritato!r}")
            raise typer.Exit(1)
        update["prioritato"] = prioritato.strip()

    if stato is not None:
        update["stato"] = stato

    if etikedo is not None:
        etikedo_ids = resolve_etikedo_refs(
            get_etikedo_service().db,
            etikedo,
            interactive=True,
            prompt_on_missing=True,
        )
        update["etikedo"] = etikedo_ids

    try:
        svc.update(uid, update)
    except ValueError as exc:
        error(str(exc))
        raise typer.Exit(1) from exc

    updated = svc.get_with_labels(uid)
    if updated is None:
        error("Ne povis relegi modifitan taskon.")
        raise typer.Exit(1)
    info(f"Modifis todo #{uid[:8]}.")
    _show_detail(updated)


@todo_app.command()
def forigi(
    referencoj: Annotated[list[str], typer.Argument(
        ...,
        help=tr_multi("Todo UUID aŭ titolo (pluraj). Ekz: todo forigi #abc123 #def456", "Todo UUID or title (multiple). E.g. todo delete #abc123 #def456", "UUID ou titre du todo (plusieurs). Ex: todo supprimer #abc123 #def456"),
    )],
) -> None:
    """Forigi taskon laŭ UUID aŭ titolo."""
    svc = get_todo_service()
    entries = svc.list_with_labels(limit=200)
    item = resolve_reference(
        entries,
        referenco,
        text_getter=lambda i: str(i.get("titolo") or ""),
        kind_label="todo",
        allow_fuzzy=True,
        interactive=True,
    )
    if item is None:
        error(f"Todo ne trovita: {referenco}")
        raise typer.Exit(1)

    uid = str(item.get("uuid") or "")
    rendered = render_text(str(item.get("titolo") or ""))
    answer = typer.prompt(
        f"Forigi todo #{uid[:8]} \"{rendered}\"? (j/N)",
        default="N",
    )
    if answer.strip().lower() not in {"j", "jes", "y", "yes"}:
        info("Nuligita.")
        return

    svc.delete(uid, soft=False)
    info(f"Forigis todo #{uid[:8]}.")


@todo_app.command()
def serci(
    teksto: str = typer.Argument(
        "",
        help=tr_multi("Serĉa teksto. Ekz: todo serci legi", "Search text. E.g. todo search read", "Texte de recherche. Ex: todo rechercher lire"),
    ),
    titolo: str | None = typer.Option(
        None,
        "--titolo",
        help=tr_multi("Filtri laŭ titolo. Ekz: --titolo raporto", "Filter by title. E.g. --titolo report", "Filtrer par titre. Ex: --titolo rapport"),
    ),
    priskribo: str | None = typer.Option(
        None,
        "--priskribo",
        help=tr_multi("Filtri laŭ priskribo. Ekz: --priskribo [temo](ec#uuid)", "Filter by description. E.g. --priskribo [topic](ec#uuid)", "Filtrer par description. Ex: --priskribo [sujet](ec#uuid)"),
    ),
    stato: str | None = typer.Option(
        None,
        "-s",
        "--stato",
        help=(
            "Filtri laŭ stato. "
            "Validaj: malfermita, farita, prokrastita, nuligita. "
            "Ekz: -s farita"
        ),
    ),
    etikedo: list[str] | None = typer.Option(
        None,
        "-e",
        "--etikedo",
        help=(
            "Filtri laŭ etikedo; ripetu por pluraj. "
            "Ekz: -e urga -e #abc"
        ),
    ),
    prioritato: str | None = typer.Option(
        None,
        "-P",
        "--prioritato",
        help=tr_multi("Filtri laŭ prioritato MIN,MAX aŭ nur MIN. Ekz: -P 30,80 aŭ -P 50", "Filter by priority MIN,MAX or just MIN. E.g. -P 30,80 or -P 50", "Filtrer par priorité MIN,MAX ou juste MIN. Ex: -P 30,80 ou -P 50"),
    ),
    limo: int = typer.Option(
        50,
        "-lo",
        "--limo",
        help=tr_multi("Maksimumaj rezultoj. Ekz: --limo 20", "Maximum results. E.g. --limo 20", "Résultats maximum. Ex: --limo 20"),
    ),
) -> None:
    """Serĉi taskojn per kombineblaj filtriloj."""
    svc = get_todo_service()
    etikedo_ids: list[str] = []
    if etikedo:
        etikedo_ids = resolve_etikedo_refs(
            get_etikedo_service().db, etikedo, interactive=True
        )

    # Parse priority range
    prioritato_min: float | None = None
    prioritato_max: float | None = None
    if prioritato:
        raw = prioritato.strip()
        if "," in raw:
            left, right = raw.split(",", 1)
            prioritato_min = float(left.strip()) if left.strip() else None
            prioritato_max = float(right.strip()) if right.strip() else None
        else:
            prioritato_min = float(raw)

    results, fuzzy_used = svc.search_todo(
        query=teksto or None,
        titolo=titolo,
        priskribo=priskribo,
        stato=stato,
        etikedo=etikedo_ids or None,
        prioritato_min=prioritato_min,
        prioritato_max=prioritato_max,
        limit=limo,
    )

    if fuzzy_used:
        info("Neniu preciza rezulto; montrante similajn kongruojn.")
    info(f"{len(results)} rezulto(j) trovita(j).")
    if results:
        _print_results(results)


__all__ = ["todo_app"]
