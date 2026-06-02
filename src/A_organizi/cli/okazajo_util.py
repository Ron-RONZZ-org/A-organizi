"""Extended event operations: ICS import/export, sync, undo."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

import typer
from rich.table import Table

from A import error, info, tr_multi
from A.utils.date import parse_partial_date
from A.utils.output import console

from A_organizi.service.kalendaro import (
    get_evento_service,
    get_kalendaro_service,
)
from A_organizi.utils.ics import events_to_ics, insert_ics_events
from A_organizi.utils.sync import list_sync_queue, queue_sync, reprovi_sync_job, start_sync_worker
from A_organizi.utils.undo import apply_undo, list_undos


def register_extra_commands(app: typer.Typer) -> None:
    """Register extended event commands on the given Typer app."""

    @app.command()
    def importi(
        kalendaro_uuid: str = typer.Argument(..., help=tr_multi("Kalendaro UUID.", "Calendar UUID.", "UUID du calendrier.")),
        dosieroj: list[str] = typer.Argument(..., help=tr_multi("ICS-dosiero(j).", "ICS file(s).", "Fichier(s) ICS.")),
    ) -> None:
        """Importi ICS-dosierojn en kalendaron."""
        cal_svc = get_kalendaro_service()
        resolved_cal = cal_svc.resolve_uuid(kalendaro_uuid)
        if not resolved_cal:
            error(tr_multi("Kalendaro ne trovita.", "Calendar not found.", "Calendrier non trouvé."))
            raise typer.Exit(1)

        db = get_evento_service().db
        added: list[str] = []
        for file_path in dosieroj:
            text = Path(file_path).read_text(encoding="utf-8")
            added.extend(insert_ics_events(db, resolved_cal, text))
        info(f"Importis {len(added)} evento(j)n.")

    @app.command()
    def eksporti(
        argumentoj: Optional[list[str]] = typer.Argument(
            None, help=tr_multi("UUID(j) au datoj (YYYYMMDD/MMDD/DD).", "UUID(s) or dates (YYYYMMDD/MMDD/DD).", "UUID ou dates (AAAAMMJJ/MMJJ/JJ)."),
        ),
        kalendaro: Optional[list[str]] = typer.Option(
            None, "-k", "--kalendaro", help=tr_multi("Filtri lau kalendaro UUID.", "Filter by calendar UUID.", "Filtrer par UUID du calendrier."),
        ),
        dosiero: Optional[str] = typer.Option(
            None, "-d", "--dosiero", help=tr_multi("Cela .ics dosiero.", "Target .ics file.", "Fichier .ics de destination."),
        ),
    ) -> None:
        """Eksporti eventojn lau UUID au kalendaro+datoj."""
        from A_organizi.cli.okazajo import _fmt_date, _fmt_hhmm  # noqa: F401

        args = argumentoj or []
        date_tokens = [t for t in args if t.isdigit() and len(t) in (2, 4, 8)]
        refs = [t for t in args if t not in date_tokens]

        svc = get_evento_service()
        cal_svc = get_kalendaro_service()
        rows: list[dict] = []

        if refs:
            for ref in refs:
                uid = svc.resolve_uuid(ref)
                if uid and (row := svc.get(uid)):
                    rows.append(row)
        else:
            today = date.today()
            s_token = date_tokens[0] if date_tokens else None
            e_token = date_tokens[1] if len(date_tokens) > 1 else None
            start = parse_partial_date(s_token, ref=today) if s_token else today
            end = parse_partial_date(e_token, ref=today) if e_token else start
            if end < start:
                start, end = end, start

            cal_uuids = []
            if kalendaro:
                for ref in kalendaro:
                    uid = cal_svc.resolve_uuid(ref)
                    if uid:
                        cal_uuids.append(uid)
            rows = list(svc.list_by_date_range(start, end, cal_uuids or None))

        payload = events_to_ics(rows)
        if dosiero:
            Path(dosiero).write_text(payload, encoding="utf-8")
            info(f"Eksportis {len(rows)} evento(j)n al {dosiero}")
        else:
            console.print(payload.rstrip("\n"))

    @app.command()
    def sinkronigi(
        kalendaroj: Optional[list[str]] = typer.Argument(
            None, help=tr_multi("UUID(j) por sinkronigi.", "UUID(s) to sync.", "UUID à synchroniser."),
        ),
    ) -> None:
        """Sinkronigi kalendarojn kun fora servilo."""
        cal_svc = get_kalendaro_service()
        cal_uuids = []
        if kalendaroj:
            for ref in kalendaroj:
                uid = cal_svc.resolve_uuid(ref)
                if uid:
                    cal_uuids.append(uid)
        else:
            cal_uuids = [str(r["uuid"]) for r in cal_svc.list() if r.get("remote") == 1]

        if not cal_uuids:
            error(tr_multi("Neniu fora kalendaro.", "No remote calendar.", "Aucun calendrier distant."))
            return

        db = get_evento_service().db
        start_sync_worker()
        for cal_uuid in cal_uuids:
            queue_sync(db, cal_uuid, "pull", {})
            info(f"Sinkronigis kalendaron #{cal_uuid[:8]}.")

    @app.command()
    def vici(
        stato: Optional[str] = typer.Argument(
            None,
            help=tr_multi(
                "Filtri lau stato (pending/running/completed/failed).",
                "Filter by status (pending/running/completed/failed).",
                "Filtrer par statut (pending/running/completed/failed).",
            ),
        ),
        kalendaro: Optional[str] = typer.Option(
            None, "--kalendaro", "-k",
            help=tr_multi(
                "Filtri lau kalendaro UUID.",
                "Filter by calendar UUID.",
                "Filtrer par UUID de calendrier.",
            ),
        ),
    ) -> None:
        """Montri la staton de la sinkroniga vico."""
        svc = get_evento_service()
        db = svc.db

        # Resolve calendar prefix to full UUID
        cal_uuid: str | None = None
        if kalendaro:
            cal_svc = get_kalendaro_service()
            cal_uuid = cal_svc.resolve_uuid(kalendaro)
            if not cal_uuid:
                error(tr_multi(
                    f"Kalendaro ne trovita: {kalendaro}",
                    f"Calendar not found: {kalendaro}",
                    f"Calendrier non trouvé: {kalendaro}",
                ))
                raise typer.Exit(1)

        rows = list_sync_queue(
            db, stato=stato, calendar_uuid=cal_uuid,
        )
        if not rows:
            info(tr_multi(
                "Neniu sinkroniga tasko trovita.",
                "No sync task found.",
                "Aucune tache de synchronisation trouvee.",
            ))
            return

        from A_organizi.cli.okazajo import _short

        table = Table()
        table.add_column("ID", style="cyan", width=12)
        table.add_column(tr_multi("Kalendaro", "Calendar"), width=10)
        table.add_column(tr_multi("Operacio", "Operation"), width=10)
        table.add_column(tr_multi("Stato", "Status"), width=12)
        table.add_column(tr_multi("Eraro", "Error"), width=40)
        table.add_column(tr_multi("Kreita", "Created"), width=20)

        for row in rows:
            eraro = str(row.get("eraro") or "")
            table.add_row(
                str(row["id"])[:12],
                str(row["calendar_uuid"])[:8],
                str(row["operacio"]),
                str(row["stato"]),
                _short(eraro, 40) if eraro else "",
                str(row.get("kreita_je", ""))[:19],
            )
        console.print(table)

    @app.command()
    def reprovi(
        job_id: Optional[str] = typer.Argument(
            None,
            help=tr_multi(
                "Sinkroniga tasko ID por reprovi. Se ne donita, reprovas cxiujn malsukcesintajn.",
                "Sync job ID to retry. If omitted, retries ALL failed jobs.",
                "ID de la tâche à réessayer. Si omis, réessaye TOUTES les tâches échouées.",
            ),
        ),
        kalendaro: Optional[str] = typer.Option(
            None, "--kalendaro", "-k",
            help=tr_multi(
                "Reprovi nur por tiu kalendaro.",
                "Retry only for this calendar.",
                "Réessayer seulement pour ce calendrier.",
            ),
        ),
    ) -> None:
        """Reprovi malsukcesintajn sinkronigajn taskojn."""
        db = get_evento_service().db

        cal_uuid: str | None = None
        if kalendaro:
            cal_svc = get_kalendaro_service()
            cal_uuid = cal_svc.resolve_uuid(kalendaro)
            if not cal_uuid:
                error(tr_multi(
                    f"Kalendaro ne trovita: {kalendaro}",
                    f"Calendar not found: {kalendaro}",
                    f"Calendrier non trouvé: {kalendaro}",
                ))
                raise typer.Exit(1)

        count = reprovi_sync_job(db, job_id=job_id, calendar_uuid=cal_uuid)
        if count == 0:
            info(tr_multi(
                "Neniu malsukcesinta tasko trovita.",
                "No failed job found.",
                "Aucune tâche échouée trouvée.",
            ))
        else:
            info(tr_multi(
                f"Reprovis {count} tasko(j)n.",
                f"Retried {count} job(s).",
                f"{count} tâche(s) réessayée(s).",
            ))

    @app.command()
    def malfari(
        argumentoj: list[str] = typer.Argument(
            ..., help=tr_multi("'ls' au sxangxo-ID(j).", "'ls' or change-ID(s).", "'ls' ou ID de changement."),
        ),
    ) -> None:
        """Montri au apliki malfarojn."""
        db = get_evento_service().db

        if argumentoj and argumentoj[0] == "ls":
            rows = list_undos(db)
            if not rows:
                info(tr_multi("Neniu malfaro.", "No undo.", "Aucune annulation."))
                return
            table = Table()
            table.add_column("ID", style="cyan", width=10)
            table.add_column(tr_multi("Operacio", "Operation"), width=20)
            table.add_column(tr_multi("Dato", "Date"), width=20)
            for row in rows:
                table.add_row(row["id"][:8], row["operacio"], row["kreita_je"][:19])
            console.print(table)
        else:
            for change_id in argumentoj:
                if apply_undo(db, change_id):
                    info(f"Aplikis malfaron #{change_id[:8]}.")
                else:
                    error(f"Malfaro ne trovita: #{change_id[:8]}")


__all__ = ["register_extra_commands"]
