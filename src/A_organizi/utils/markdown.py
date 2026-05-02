"""Markdown internal link helpers for A-organizi (ec#/vt# references).

Handles A-internal cross-references between encik (ec#) and vorto (vt#)
entries used in label text, todo descriptions, and journal entries.
"""

from __future__ import annotations

import re
from typing import Any

_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")


def _canonicalize_internal_ref(token: str) -> str:
    """Canonicalize an ec# or vt# reference.

    Currently a passthrough; in future may resolve UUID prefixes
    by querying encik/vorto databases.

    Args:
        token: Raw reference string.

    Returns:
        Canonicalized reference.
    """
    raw = str(token or "").strip()
    lower = raw.casefold()
    if lower.startswith("ec#") or lower.startswith("vt#"):
        return raw
    return raw


def _render_internal_link_plain(
    label: str, target: str, *, show_ref: bool
) -> str:
    """Render a single internal markdown link as human-readable text.

    Args:
        label: Link label text.
        target: Link target (e.g. ec#uuid, vt#uuid).
        show_ref: If True, append the reference UUID in parentheses.

    Returns:
        Human-readable representation of the link.
    """
    token = _canonicalize_internal_ref(target)
    lower = token.casefold()
    if lower.startswith("ec#"):
        ref = token[3:]
        shown = label or f"ec#{ref[:8]}"
        return f"{shown} (ec#{ref[:8]})" if show_ref else shown
    if lower.startswith("vt#"):
        ref = token[3:]
        shown = label or f"vt#{ref[:8]}"
        return f"{shown} (vt#{ref[:8]})" if show_ref else shown
    return label or target


def normalize_markdown_links(text: str) -> str:
    """Normalize ec#/vt# targets in markdown links to canonical form.

    Finds all ``[label](target)`` patterns and canonicalizes targets
    that start with ``ec#`` or ``vt#``.

    Args:
        text: Raw markdown text.

    Returns:
        Text with canonicalized internal references.
    """
    raw_text = str(text or "")
    if not raw_text:
        return ""

    def _replace(match: re.Match[str]) -> str:
        label = match.group(1)
        target = match.group(2)
        canonical = _canonicalize_internal_ref(target)
        return f"[{label}]({canonical})"

    return _MARKDOWN_LINK_RE.sub(_replace, raw_text)


def render_markdown_links_plain(text: str, *, show_ref: bool = False) -> str:
    """Render markdown text with ec#/vt# links as human-readable plain text.

    Transforms ``[label](ec#uuid)`` into just ``label`` (or
    ``label (ec#uuid)`` if ``show_ref=True``).

    Args:
        text: Markdown text with internal links.
        show_ref: If True, append the resolved reference UUID.

    Returns:
        Plain text with links replaced by readable representations.
    """
    raw_text = str(text or "")
    if not raw_text:
        return ""

    def _replace(match: re.Match[str]) -> str:
        return _render_internal_link_plain(
            match.group(1).strip(),
            match.group(2).strip(),
            show_ref=show_ref,
        )

    return _MARKDOWN_LINK_RE.sub(_replace, raw_text)


__all__ = [
    "normalize_markdown_links",
    "render_markdown_links_plain",
]
