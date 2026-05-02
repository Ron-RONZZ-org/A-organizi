"""CLI for organiszi command (kalendaro, todo, taglibro)."""

from __future__ import annotations

import typer

from A import info, tr

app = typer.Typer(
    name="organizi",
    help=tr(
        "Organizi — calendar, todo, journal microapp.",
        "Organizi — calendar, todo, journal microapp.",
        "Organizi — calendar, todo, journal microapp.",
    ),
    no_args_is_help=False,
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)

kalendaro = typer.Typer(
    name="kalendaro",
    help=tr(
        "Kalendaro — manage calendars and events.",
        "Kalendaro — manage calendars and events.",
        "Kalendaro — gérer calendriers et événements.",
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)
app.add_typer(kalendaro, name="kalendaro")

todo = typer.Typer(
    name="todo",
    help=tr(
        "Todo — manage tasks with labels and priority.",
        "Todo — manage tasks with labels and priority.",
        "Todo — gérer des tâches avec étiquettes et priorité.",
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)
app.add_typer(todo, name="todo")

taglibro = typer.Typer(
    name="taglibro",
    help=tr(
        "Taglibro — daily journal microapp.",
        "Taglibro — daily journal microapp.",
        "Taglibro — journal quotidien.",
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)
app.add_typer(taglibro, name="taglibro")


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


__all__ = ["app", "kalendaro", "todo", "taglibro"]