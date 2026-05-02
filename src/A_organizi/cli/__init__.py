"""CLI for A-organizi (kalendaro, todo, taglibro, etikedoj)."""

from __future__ import annotations

import typer

from A import info, tr_multi
from A_organizi.cli.etikedi import etikedoj_app

app = typer.Typer(
    name="organizi",
    help=tr_multi(
        "Organizi — kalendaro, todo, taglibro.",
        "Organizi — calendar, todo, journal.",
        "Organizi — calendrier, tâches, journal.",
    ),
    no_args_is_help=False,
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)

# ── Sub-typers ──────────────────────────────────────────────────────────────

kalendaro = typer.Typer(
    name="kalendaro",
    help=tr_multi(
        "Kalendaro — administri kalendarojn kaj eventojn.",
        "Kalendaro — manage calendars and events.",
        "Kalendaro — gérer calendriers et événements.",
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)
app.add_typer(kalendaro, name="kalendaro")

todo = typer.Typer(
    name="todo",
    help=tr_multi(
        "Todo — administri taskojn kun etikedoj.",
        "Todo — manage tasks with labels.",
        "Todo — gérer des tâches avec étiquettes.",
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)
app.add_typer(todo, name="todo")

taglibro = typer.Typer(
    name="taglibro",
    help=tr_multi(
        "Taglibro — administri taglibrajn enirojn.",
        "Taglibro — manage journal entries.",
        "Taglibro — gérer des entrées de journal.",
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)
app.add_typer(taglibro, name="taglibro")

app.add_typer(etikedoj_app, name="etikedo")

# ── Stub commands (to be implemented in future issues) ───────────────────────


@kalendaro.command()
def ls() -> None:
    """List calendars."""
    info("[dim]TODO: implement kalendaro ls[/dim]")


@kalendaro.command()
def nun() -> None:
    """Show upcoming events."""
    info("[dim]TODO: implement kalendaro nun[/dim]")


@todo.command()
def ls() -> None:
    """List tasks."""
    info("[dim]TODO: implement todo ls[/dim]")


@todo.command()
def aldoni(teksto: str) -> None:
    """Add a task."""
    info(f"[dim]TODO: implement todo aldoni {teksto}[/dim]")


@taglibro.command()
def nun() -> None:
    """Show today's entry."""
    info("[dim]TODO: implement taglibro nun[/dim]")


@taglibro.command()
def skribi(teksto: str) -> None:
    """Add entry to today's journal."""
    info(f"[dim]TODO: implement taglibro skribi[/dim]")


__all__ = ["app", "kalendaro", "todo", "taglibro", "etikedoj_app"]
