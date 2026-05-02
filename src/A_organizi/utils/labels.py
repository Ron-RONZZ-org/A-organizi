"""Shared label helpers for A-organizi (etikedo/todo/taglibro).

Ported from autish-legacy autish/commands/_tasklib.py.
"""

from __future__ import annotations

import re
from collections.abc import Callable

import typer
from A.utils.normalize import fold_search_text

from A_organizi.utils.markdown import (
    normalize_markdown_links,
    render_markdown_links_plain,
)

# ──────────────────────────────────────────────────────────────────────────────
# Label blob parsing (uuid:text|uuid:text format)
# ──────────────────────────────────────────────────────────────────────────────


def parse_label_blob(raw: str | None) -> list[tuple[str, str]]:
    """Parse a label blob string into list of (uuid, text) pairs.

    Format: ``uuid1:text1|uuid2:text2``

    Args:
        raw: The blob string (e.g. from GROUP_CONCAT).

    Returns:
        List of (uuid, text) tuples.
    """
    if not raw:
        return []
    pairs: list[tuple[str, str]] = []
    for chunk in str(raw).split("|"):
        if not chunk.strip():
            continue
        uid, _, text = chunk.partition(":")
        if uid.strip():
            pairs.append((uid.strip(), text.strip()))
    return pairs


def render_label_pairs(pairs: list[tuple[str, str]]) -> str:
    """Render label (uuid, text) pairs as a comma-separated display string.

    Args:
        pairs: List of (uuid, text) tuples.

    Returns:
        Rendered string (e.g. "urgxa, persona"), or "-" if empty.
    """
    if not pairs:
        return "-"
    rendered: list[str] = []
    for _, text in pairs:
        if text:
            rendered.append(render_markdown_links_plain(text))
    return ", ".join(rendered) if rendered else "-"


# ──────────────────────────────────────────────────────────────────────────────
# Generic reference resolution (UUID prefix, title match, fuzzy)
# ──────────────────────────────────────────────────────────────────────────────


def fuzzy_matches(
    items: list[dict],
    query: str,
    *,
    text_getter: Callable[[dict], str],
    limit: int = 20,
    threshold: float = 0.62,
) -> list[dict]:
    """Fuzzy match items using difflib SequenceMatcher.

    Args:
        items: List of item dicts to search.
        query: Search query.
        text_getter: Function to extract searchable text from an item.
        limit: Max results.
        threshold: Minimum similarity ratio (0.0-1.0).

    Returns:
        Filtered and sorted list of matching items.
    """
    from difflib import SequenceMatcher

    needle = fold_search_text(query)
    if not needle:
        return []
    scored: list[tuple[float, dict]] = []
    for item in items:
        candidate = fold_search_text(text_getter(item))
        if not candidate:
            continue
        ratio = SequenceMatcher(None, needle, candidate).ratio()
        if ratio >= threshold:
            scored.append((ratio, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:limit]]


def search_items(
    items: list[dict],
    query: str | None,
    *,
    text_getter: Callable[[dict], str],
    limit: int = 50,
) -> tuple[list[dict], bool]:
    """Search items by substring match, falling back to fuzzy.

    Args:
        items: List of item dicts.
        query: Search query string.
        text_getter: Function to extract searchable text.
        limit: Max results.

    Returns:
        Tuple of (results, fuzzy_used).
    """
    if not query:
        return list(items), False
    needle = fold_search_text(query)
    contains = [
        item
        for item in items
        if needle and needle in fold_search_text(text_getter(item))
    ]
    if contains:
        return contains[:limit], False
    fuzzy = fuzzy_matches(items, query, text_getter=text_getter, limit=limit)
    return fuzzy, bool(fuzzy)


def prompt_pick(
    candidates: list[dict],
    *,
    title: str,
    text_getter: Callable[[dict], str],
) -> dict | None:
    """Prompt the user to pick from a list of candidates.

    Args:
        candidates: List of candidate dicts.
        title: Prompt title.
        text_getter: Function to extract display text from an item.

    Returns:
        The selected item, or None if cancelled.
    """
    if not candidates:
        return None
    typer.echo(title)
    for index, item in enumerate(candidates, start=1):
        uid = str(item.get("uuid") or "")
        label = text_getter(item)
        typer.echo(f"{index}. {label} (#{uid[:8]})")
    raw = typer.prompt("Elektu numeron (aŭ Enter por nuligi)", default="")
    if not raw.strip():
        return None
    try:
        idx = int(raw.strip()) - 1
    except ValueError:
        typer.echo("Nevalida elekto.", err=True)
        raise typer.Exit(1) from None
    if idx < 0 or idx >= len(candidates):
        typer.echo("Nevalida elekto.", err=True)
        raise typer.Exit(1)
    return candidates[idx]


def resolve_reference(
    items: list[dict],
    reference: str,
    *,
    text_getter: Callable[[dict], str],
    kind_label: str,
    allow_fuzzy: bool = True,
    interactive: bool = True,
) -> dict | None:
    """Resolve a user reference (UUID, prefix, or title) to a single item.

    Resolution order:
    1. Exact UUID match
    2. UUID prefix match (unique)
    3. Exact text match
    4. Fuzzy/contains match (if allow_fuzzy)

    Args:
        items: List of all candidate items.
        reference: User-provided reference string.
        text_getter: Function to extract searchable text.
        kind_label: Human-readable label (e.g. "etikedo").
        allow_fuzzy: Allow fuzzy/contains matching as fallback.
        interactive: Prompt user if multiple matches found.

    Returns:
        Resolved item, or None if not found.
    """
    raw_ref = str(reference or "").strip()
    if not raw_ref:
        return None
    token = raw_ref.lstrip("#")
    folded_ref = fold_search_text(token)

    exact_uuid = [item for item in items if str(item.get("uuid") or "") == token]
    if len(exact_uuid) == 1:
        return exact_uuid[0]
    prefix = [
        item for item in items if str(item.get("uuid") or "").startswith(token)
    ]
    exact_text = [
        item
        for item in items
        if fold_search_text(text_getter(item)) == folded_ref
    ]

    exact_candidates: list[dict] = []
    seen: set[str] = set()
    for item in [*exact_uuid, *prefix, *exact_text]:
        uid = str(item.get("uuid") or "")
        if uid in seen:
            continue
        seen.add(uid)
        exact_candidates.append(item)

    if len(exact_candidates) == 1:
        return exact_candidates[0]
    if len(exact_candidates) > 1:
        if not interactive:
            return None
        return prompt_pick(
            exact_candidates,
            title=f"Pluraj {kind_label}-kandidatoj por {reference!r}:",
            text_getter=text_getter,
        )

    if not allow_fuzzy:
        return None
    contains = [
        item
        for item in items
        if folded_ref
        and folded_ref in fold_search_text(text_getter(item))
    ][:20]
    fuzzy = fuzzy_matches(items, token, text_getter=text_getter, limit=20)
    candidates = contains if contains else fuzzy
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1 and interactive:
        return prompt_pick(
            candidates,
            title=(
                f"Neniu ekzakta kongruo por {reference!r}. "
                f"Proksimaj rezultoj:"
            ),
            text_getter=text_getter,
        )
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Label-specific DB helpers
# ──────────────────────────────────────────────────────────────────────────────


def list_etikedoj(db) -> list[dict]:
    """List all labels from the database.

    Args:
        db: SQLiteDB instance.

    Returns:
        List of label dicts ordered by text.
    """
    return db.execute(
        "SELECT uuid, teksto, teksto_norm, kreita_je, modifita_je "
        "FROM etikedoj ORDER BY teksto COLLATE NOCASE"
    )


def resolve_etikedo_refs(
    db,
    references: list[str] | None,
    *,
    interactive: bool = True,
    prompt_on_missing: bool = False,
) -> list[str]:
    """Resolve label references (UUID, prefix, text) to UUIDs.

    Args:
        db: SQLiteDB instance.
        references: List of user-provided references.
        interactive: Allow interactive disambiguation.
        prompt_on_missing: If True, prompt to create missing labels.

    Returns:
        List of resolved label UUIDs.
    """
    refs = [
        str(ref or "").strip()
        for ref in (references or [])
        if str(ref or "").strip()
    ]
    if not refs:
        return []
    resolved: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        labels = list_etikedoj(db)
        target = resolve_reference(
            labels,
            ref,
            text_getter=lambda item: str(item.get("teksto") or ""),
            kind_label="etikedo",
            allow_fuzzy=True,
            interactive=interactive,
        )
        if target is None:
            if prompt_on_missing and interactive:
                answer = typer.prompt(
                    f"Etikedo ne trovita: {ref!r}. Ĉu aldoni novan? (j/N)",
                    default="N",
                )
                if answer.strip().lower() == "j":
                    uid = _create_label_from_ref(db, ref)
                    if uid and uid not in seen:
                        seen.add(uid)
                        resolved.append(uid)
                else:
                    typer.echo(f"Etikedo ne trovita: {ref!r}", err=True)
                    raise typer.Exit(1)
            else:
                typer.echo(f"Etikedo ne trovita: {ref!r}", err=True)
                raise typer.Exit(1)
        else:
            uid = str(target.get("uuid") or "")
            if uid and uid not in seen:
                seen.add(uid)
                resolved.append(uid)
    return resolved


def _create_label_from_ref(db, ref: str) -> str | None:
    """Create a new label from a user-provided reference string.

    Args:
        db: SQLiteDB instance.
        ref: Reference text to use as label text.

    Returns:
        New label UUID, or None if creation failed.
    """
    import uuid
    from datetime import datetime, timezone

    normalized = normalize_markdown_links(ref).strip()
    if not normalized:
        typer.echo("Malplena etikedo ne permesata.", err=True)
        raise typer.Exit(1)
    folded = fold_search_text(normalized)
    existing = db.execute_one(
        "SELECT uuid FROM etikedoj WHERE teksto_norm = ?", (folded,)
    )
    if existing:
        uid = str(existing["uuid"])
    else:
        uid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            "INSERT INTO etikedoj (uuid, teksto, teksto_norm, kreita_je, modifita_je) "
            "VALUES (?, ?, ?, ?, ?)",
            (uid, normalized, folded, now, now),
        )
        rendered = render_markdown_links_plain(normalized, show_ref=True)
        typer.echo(f"Aldonis etikedon: {rendered}")
    return uid


def etikedo_text_map(db) -> dict[str, str]:
    """Get a mapping of label UUID to rendered text.

    Args:
        db: SQLiteDB instance.

    Returns:
        Dict of {uuid: rendered_text}.
    """
    rows = db.execute("SELECT uuid, teksto FROM etikedoj")
    return {
        str(row["uuid"]): render_markdown_links_plain(str(row["teksto"] or ""))
        for row in rows
    }


def auto_create_semantic_link_etikedoj(db, text: str) -> None:
    """Auto-create etikedo entries for semantic links [label](ec#uuid).

    Scans text for markdown links targeting ec# or vt# references,
    creating etikedo entries for them if they don't exist yet.

    Args:
        db: SQLiteDB instance.
        text: Text to scan for markdown links.
    """
    import re
    import uuid
    from datetime import datetime, timezone

    raw_text = str(text or "")
    if not raw_text:
        return

    link_re = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
    matches = link_re.finditer(raw_text)
    for match in matches:
        label = match.group(1).strip()
        target = match.group(2).strip()
        lower_target = target.casefold()

        if not (lower_target.startswith("ec#") or lower_target.startswith("vt#")):
            continue

        etikedo_text = f"[{label}]({target})" if label else target
        folded = fold_search_text(etikedo_text)

        existing = db.execute_one(
            "SELECT uuid FROM etikedoj WHERE teksto_norm = ?",
            (folded,),
        )
        if not existing:
            uid = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()
            db.execute(
                "INSERT INTO etikedoj "
                "(uuid, teksto, teksto_norm, kreita_je, modifita_je) "
                "VALUES (?, ?, ?, ?, ?)",
                (uid, etikedo_text, folded, now, now),
            )


__all__ = [
    "parse_label_blob",
    "render_label_pairs",
    "fuzzy_matches",
    "search_items",
    "prompt_pick",
    "resolve_reference",
    "list_etikedoj",
    "resolve_etikedo_refs",
    "etikedo_text_map",
    "auto_create_semantic_link_etikedoj",
]
