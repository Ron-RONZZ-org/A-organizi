"""Priority formula engine for todo tasks.

Computes task priority from formula strings with time-context variables.
Uses ``A.utils.expr.eval_safe`` for safe mathematical evaluation.

Ported from autish-legacy todo.py priority formula engine.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from A.utils.expr import eval_safe, validate_safe

# Time variable aliases available in priority formulas
_TIME_VARS = {
    "M": "months (30 days) since creation",
    "D": "days since creation",
    "H": "hours since creation",
    "MIN": "minutes since creation",
    "m": "minutes since creation (alias for MIN)",
}


def _priority_context(created_at: str) -> dict[str, float]:
    """Build time-context variables for a priority formula.

    Computes M, D, H, m/MIN from the time elapsed since ``created_at``.

    Args:
        created_at: ISO 8601 datetime string of when the task was created.

    Returns:
        Dict with keys ``M``, ``D``, ``H``, ``MIN``, ``m``.
    """
    created = datetime.fromisoformat(
        str(created_at).replace("Z", "+00:00")
    )
    now = datetime.now(timezone.utc)
    delta = now - created.astimezone(timezone.utc)
    if delta.total_seconds() < 0:
        delta = timedelta(0)

    minutes = delta.total_seconds() / 60.0
    hours = delta.total_seconds() / 3600.0
    days = delta.total_seconds() / 86400.0
    months = days / 30.0

    return {
        "M": months,
        "D": days,
        "H": hours,
        "MIN": minutes,
        "m": minutes,
    }


def compute_priority(formula: str, created_at: str) -> float:
    """Compute a task's priority value from its formula and creation time.

    Args:
        formula: Priority formula string (e.g. ``"min(20 + 2 * D, 70)"``).
                 A plain number is also valid.
        created_at: ISO 8601 creation timestamp.

    Returns:
        Computed priority value as float.

    Raises:
        ValueError: If the formula is invalid or produces a non-finite value.
    """
    text = str(formula or "").strip()
    if not text:
        return 0.0

    # Fast path: plain number
    try:
        return float(text)
    except ValueError:
        pass

    context = _priority_context(created_at)
    return eval_safe(text, context)


def format_priority(formula: str, created_at: str) -> str:
    """Format a task's priority for display.

    Shows both computed value and raw formula (when formula is not a plain number).

    Args:
        formula: Priority formula string.
        created_at: ISO 8601 creation timestamp.

    Returns:
        Formatted string like ``"30.00 (kruda: 20+2*D)"`` or just ``"42.00"``.
    """
    value = compute_priority(formula, created_at)
    text = str(formula or "").strip()
    try:
        float(text)
        return f"{value:.2f}"
    except ValueError:
        return f"{value:.2f} (kruda: {text})"


def validate_formula(formula: str) -> bool:
    """Check whether a formula string is syntactically safe to evaluate.

    Allows time-context variables (M, D, H, m, MIN) in addition to
    the default math functions.

    Args:
        formula: Priority formula string.

    Returns:
        True if the formula is safe.
    """
    text = str(formula or "").strip()
    if not text:
        return True  # empty = 0, always valid
    try:
        float(text)
        return True  # plain number, always valid
    except ValueError:
        pass
    return validate_safe(text, allowed_vars={"M", "D", "H", "MIN", "m"})


def priority_filter_description() -> str:
    """Return a human-readable description of time variables for help text.

    Returns:
        Multiline string describing available variables and examples.
    """
    lines = [
        "Priority formula variables (time since creation):",
        "  M   = months (30 days)",
        "  D   = days",
        "  H   = hours",
        "  m/MIN = minutes",
        "",
        "Examples:",
        '  -P "42"           (constant priority)',
        '  -P "20 + 2*D"     (increases with age)',
        '  -P "min(30, 10*H)" (caps at 30)',
        "",
        "Supported functions: min, max, abs, round, int, float",
        "Supported operators: +, -, *, /, //, %, **",
    ]
    return "\n".join(lines)


__all__ = [
    "compute_priority",
    "format_priority",
    "validate_formula",
    "priority_filter_description",
]
