"""CLI commands for todo (tasks) — app, helpers, and aldoni.

CRUD commands (ls, vidi, modifi, forigi, serci) are in todo_crud.py.
"""

from __future__ import annotations

from typing import Optional

import typer

from A import error, info, tr_multi
from A.utils.output import console, print_table
from A.utils.normalize import fold_search_text

from A_organizi.priority import (
    format_priority,
    priority_filter_description,
    validate_formula,
)
from A_organizi.service import get_etikedo_service, get_todo_service
from A_organizi.utils.labels import (
    normalize_markdown_links,
    render_markdown_links_plain as render_text,
    resolve_etikedo_refs,
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
            "uuid": f"{str(item.get('uuid') or '')[:8]}",
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
    """Print full details of a single task using a Rich Panel."""
    from rich.panel import Panel
    from rich.text import Text

    priority = format_priority(
        str(item.get("prioritato") or "0"),
        str(item.get("kreita_je") or ""),
    )
    etikedoj = ", ".join(
        render_text(text) for _, text in (item.get("etikedoj") or []) if text
    ) or "-"

    uid = str(item.get("uuid") or "")[:8]
    titolo_raw = str(item.get("titolo") or "")
    priskribo_raw = str(item.get("priskribo") or "")
    stato = str(item.get("stato") or "")
    kreita = str(item.get("kreita_je", ""))
    modifita = str(item.get("modifita_je", ""))

    display_title = titolo_raw[:40] + "…" if len(titolo_raw) > 40 else titolo_raw
    title = Text()
    title.append(display_title, style="bold white")
    title.append(f"  {uid}", style="dim")

    lines: list[str] = []
    lines.append(f"[bold]titolo:[/] {render_text(titolo_raw, show_ref=True)}")
    if priskribo_raw:
        lines.append(f"[bold]priskribo:[/] {render_text(priskribo_raw, show_ref=True)}")
    lines.append(f"[bold]stato:[/] {stato}")
    lines.append(f"[bold]prioritato:[/] {priority}")
    lines.append(f"[bold]etikedoj:[/] {etikedoj}")
    lines.append("")
    lines.append(f"[dim]kreita_je:[/] {kreita}")
    lines.append(f"[dim]modifita_je:[/] {modifita}")

    content = "\n".join(lines)
    panel = Panel(
        content,
        title=title,
        title_align="left",
        border_style="dim",
        padding=(0, 1),
    )
    console.print(panel)


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
        f"Aldonis todo {result['uuid'][:8]}: "
        f"{render_text(titolo_text, show_ref=True)}"
    )


__all__ = ["todo_app", "_print_results", "_show_detail"]
