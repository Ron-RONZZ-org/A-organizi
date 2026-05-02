"""CLI for A-organizi (kalendaro, todo, taglibro, etikedoj)."""

from __future__ import annotations

import typer

from A import tr_multi
from A_organizi.cli.etikedi import etikedoj_app
from A_organizi.cli.kalendaro import kalendaro_app
from A_organizi.cli.taglibro import taglibro_app
from A_organizi.cli.todo import todo_app

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

app.add_typer(kalendaro_app, name="kalendaro")
app.add_typer(todo_app, name="todo")
app.add_typer(taglibro_app, name="taglibro")
app.add_typer(etikedoj_app, name="etikedo")

__all__ = ["app", "kalendaro_app", "todo_app", "taglibro_app", "etikedoj_app"]
