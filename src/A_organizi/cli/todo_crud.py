"""CRUD commands for todo (tasks) — ls, vidi, modifi, forigi, serci.

Split from todo.py to keep each file under 500 lines.
"""

from __future__ import annotations

from typing import Annotated

import typer

from A import error, info, tr_multi
from A.utils.normalize import fold_search_text

from A_organizi.priority import (
    compute_priority,
    validate_formula,
)
from A_organizi.service import get_etikedo_service, get_todo_service
from A_organizi.cli.todo import _print_results, _show_detail, todo_app
from A_organizi.utils.labels import (
    normalize_markdown_links,
    render_markdown_links_plain as render_text,
    resolve_etikedo_refs,
    resolve_reference,
)


# ── Commands ─────────────────────────────────────────────────────────────────


@todo_app.command()
def ls(
    priority: bool = typer.Option(
        False,
        "-p",
        "--priority",
        help=tr_multi(
            "Ordigi la\u016d prioritato (desc).",
            "Sort by priority (descending).",
            "Trier par priorit\u00e9 (d\u00e9croissante).",
        ),
    ),
    reverse: bool = typer.Option(
        False,
        "-r",
        "--reverse",
        help=tr_multi(
            "Inversigi la ordon.",
            "Reverse sort order.",
            "Inverser l'ordre de tri.",
        ),
    ),
) -> None:
    """Listi \u0109iujn taskojn."""
    svc = get_todo_service()
    items = svc.list_with_labels(limit=200)

    if not items:
        info(tr_multi(
            "Neniuj taskoj.",
            "No tasks.",
            "Aucune t\u00e2che.",
        ))
        return

    if priority:
        for item in items:
            item["_priority_value"] = compute_priority(
                str(item.get("prioritato") or "0"),
                str(item.get("kreita_je") or ""),
            )
        items.sort(key=lambda x: x["_priority_value"], reverse=not reverse)
    elif reverse:
        items.reverse()

    _print_results(items)


@todo_app.command()
def vidi(
    referenco: str = typer.Argument(
        ...,
        help=tr_multi(
            "Todo UUID a\u016d titolo. Ekz: todo vidi #abc123",
            "Todo UUID or title. E.g. todo view #abc123",
            "UUID ou titre du todo. Ex: todo voir #abc123",
        ),
    ),
) -> None:
    """Montri unu taskon la\u016d UUID a\u016d titolo."""
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
        help=tr_multi(
            "Todo UUID a\u016d titolo. Ekz: todo modifi #abc --stato farita",
            "Todo UUID or title. E.g. todo modify #abc --stato farita",
            "UUID ou titre du todo. Ex: todo modifier #abc --stato farita",
        ),
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
            "Nova etikedo-listo (anstata\u016digas); ripetu por pluraj. "
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
        error("Nenio por modifi. Uzu almena\u016d unu opcion.")
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
    info(f"Modifis todo {uid[:8]}.")
    _show_detail(updated)


@todo_app.command()
def forigi(
    referencoj: Annotated[list[str], typer.Argument(
        ...,
        help=tr_multi(
            "Todo UUID a\u016d titolo (pluraj). Ekz: todo forigi #abc123 #def456",
            "Todo UUID or title (multiple). E.g. todo delete #abc123 #def456",
            "UUID ou titre du todo (plusieurs). Ex: todo supprimer #abc123 #def456",
        ),
    )],
) -> None:
    """Forigi taskojn la\u016d UUID a\u016d titolo."""
    svc = get_todo_service()
    entries = svc.list_with_labels(limit=200)

    deleted = 0
    errors: list[tuple[str, str]] = []

    for ref in referencoj:
        item = resolve_reference(
            entries,
            ref,
            text_getter=lambda i: str(i.get("titolo") or ""),
            kind_label="todo",
            allow_fuzzy=True,
            interactive=True,
        )
        if item is None:
            errors.append((ref, tr_multi("ne trovita", "not found", "non trouv\u00e9")))
            continue

        uid = str(item.get("uuid") or "")
        rendered = render_text(str(item.get("titolo") or ""))
        answer = typer.prompt(
            f"Forigi todo {uid[:8]} \"{rendered}\"? (j/N)",
            default="N",
        )
        if answer.strip().lower() not in {"j", "jes", "y", "yes"}:
            info(tr_multi(
                f"Preterlasis {ref}.", f"Skipped {ref}.", f"Ignor\u00e9 {ref}.",
            ))
            continue

        svc.delete(uid, soft=False)
        deleted += 1
        entries = [e for e in entries if str(e.get("uuid") or "") != uid]
        info(f"Forigis todo {uid[:8]}.")

    for ref, reason in errors:
        error(tr_multi(
            "Forigi {i}: {r}", "Delete {i}: {r}", "Supprimer {i} : {r}",
        ).format(i=ref, r=reason))

    if deleted:
        info(tr_multi(
            f"Forigis {deleted} el {len(referencoj)} todo.",
            f"Deleted {deleted} of {len(referencoj)} todos.",
            f"Supprim\u00e9 {deleted} sur {len(referencoj)} todos.",
        ))


@todo_app.command()
def serci(
    teksto: str = typer.Argument(
        "",
        help=tr_multi(
            "Ser\u0109a teksto. Ekz: todo serci legi",
            "Search text. E.g. todo search read",
            "Texte de recherche. Ex: todo rechercher lire",
        ),
    ),
    titolo: str | None = typer.Option(
        None,
        "--titolo",
        help=tr_multi(
            "Filtri la\u016d titolo. Ekz: --titolo raporto",
            "Filter by title. E.g. --titolo report",
            "Filtrer par titre. Ex: --titolo rapport",
        ),
    ),
    priskribo: str | None = typer.Option(
        None,
        "--priskribo",
        help=tr_multi(
            "Filtri la\u016d priskribo. Ekz: --priskribo [temo](ec#uuid)",
            "Filter by description. E.g. --priskribo [topic](ec#uuid)",
            "Filtrer par description. Ex: --priskribo [sujet](ec#uuid)",
        ),
    ),
    stato: str | None = typer.Option(
        None,
        "-s",
        "--stato",
        help=(
            "Filtri la\u016d stato. "
            "Validaj: malfermita, farita, prokrastita, nuligita. "
            "Ekz: -s farita"
        ),
    ),
    etikedo: list[str] | None = typer.Option(
        None,
        "-e",
        "--etikedo",
        help=(
            "Filtri la\u016d etikedo; ripetu por pluraj. "
            "Ekz: -e urga -e #abc"
        ),
    ),
    prioritato: str | None = typer.Option(
        None,
        "-P",
        "--prioritato",
        help=tr_multi(
            "Filtri la\u016d prioritato MIN,MAX a\u016d nur MIN. Ekz: -P 30,80 a\u016d -P 50",
            "Filter by priority MIN,MAX or just MIN. E.g. -P 30,80 or -P 50",
            "Filtrer par priorit\u00e9 MIN,MAX ou juste MIN. Ex: -P 30,80 ou -P 50",
        ),
    ),
    limo: int = typer.Option(
        50,
        "-lo",
        "--limo",
        help=tr_multi(
            "Maksimumaj rezultoj. Ekz: --limo 20",
            "Maximum results. E.g. --limo 20",
            "R\u00e9sultats maximum. Ex: --limo 20",
        ),
    ),
) -> None:
    """Ser\u0109i taskojn per kombineblaj filtriloj."""
    svc = get_todo_service()
    etikedo_ids: list[str] = []
    if etikedo:
        etikedo_ids = resolve_etikedo_refs(
            get_etikedo_service().db, etikedo, interactive=True
        )

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


__all__: list[str] = []
