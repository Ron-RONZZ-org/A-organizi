"""RRULE validation and shorthand expansion for okazajo (calendar events).

RFC 5545 RRULE syntax validator with Esperanto/English/French error messages.
Supports common shorthand expansions for user convenience.
"""

from __future__ import annotations

import re

from A import tr_multi

# ── Shorthand mapping ──────────────────────────────────────────────────────

_SHORTHAND: dict[str, str] = {
    "daily": "FREQ=DAILY",
    "weekly": "FREQ=WEEKLY",
    "monthly": "FREQ=MONTHLY",
    "yearly": "FREQ=YEARLY",
    "weekdays": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
    "weekends": "FREQ=WEEKLY;BYDAY=SA,SU",
}

# Valid RRULE parts (RFC 5545 section 3.8.5.3)
_VALID_PARTS = {
    "FREQ": {"DAILY", "WEEKLY", "MONTHLY", "YEARLY"},
    "UNTIL": None,  # date-time, validated by regex
    "COUNT": None,  # integer, validated by regex
    "INTERVAL": None,  # positive integer
    "BYDAY": None,  # comma-separated day codes
    "BYMONTHDAY": None,  # integer
    "BYMONTH": None,  # integer 1-12
    "BYSETPOS": None,  # integer
    "WKST": {"MO", "TU", "WE", "TH", "FR", "SA", "SU"},
}

# Regex for a single RRULE parameter: KEY=value
_RRULE_PART_RE = re.compile(r"^([A-Z]+)=(.+)$")

# Valid BYDAY values
_WEEKDAYS = {"MO", "TU", "WE", "TH", "FR", "SA", "SU"}


def expand_shorthand(text: str) -> str:
    """Expand common English shorthand to full RRULE strings.

    Case-insensitive matching. Returns the original text unchanged
    if no shorthand match is found.

    Args:
        text: Possible shorthand like "daily" or "weekdays".

    Returns:
        Expanded RRULE string, or the original text if not shorthand.
    """
    key = text.strip().lower()
    if key in _SHORTHAND:
        return _SHORTHAND[key]
    return text.strip()


def validate_rrule(text: str) -> str:
    """Validate an RRULE string and return it normalized.

    Checks:
    - FREQ is present and valid
    - All parameter names are recognized
    - UNTIL format is a valid date-time (YYYYMMDDTHHMMSSZ)
    - COUNT/INTERVAL are positive integers
    - BYDAY values are valid weekday codes
    - WKST value is valid

    Args:
        text: The RRULE string to validate.

    Returns:
        The trimmed RRULE string on success.

    Raises:
        ValueError: With a translated error message if validation fails.
    """
    raw = text.strip()
    if not raw:
        return ""

    parts = raw.split(";")
    seen_keys: set[str] = set()

    for part in parts:
        m = _RRULE_PART_RE.match(part)
        if not m:
            raise ValueError(
                tr_multi(
                    f"Nevalida RRULE-parto: {part!r}.",
                    f"Invalid RRULE part: {part!r}.",
                    f"Partie RRULE invalide : {part!r}.",
                )
            )
        key, value = m.group(1), m.group(2)

        if key in seen_keys:
            raise ValueError(
                tr_multi(
                    f"Duobla parametro en RRULE: {key}.",
                    f"Duplicate parameter in RRULE: {key}.",
                    f"Paramètre en double dans RRULE : {key}.",
                )
            )
        seen_keys.add(key)

        if key not in _VALID_PARTS:
            raise ValueError(
                tr_multi(
                    f"Nekonata RRULE-parametro: {key}.",
                    f"Unknown RRULE parameter: {key}.",
                    f"Paramètre RRULE inconnu : {key}.",
                )
            )

        if key == "FREQ":
            if value not in _VALID_PARTS["FREQ"]:
                raise ValueError(
                    tr_multi(
                        f"Nevalida FREQ-valoro: {value!r}. "
                        f"Uzu DAILY, WEEKLY, MONTHLY aŭ YEARLY.",
                        f"Invalid FREQ value: {value!r}. "
                        f"Use DAILY, WEEKLY, MONTHLY or YEARLY.",
                        f"Valeur FREQ invalide : {value!r}. "
                        f"Utilisez DAILY, WEEKLY, MONTHLY ou YEARLY.",
                    )
                )

        elif key == "UNTIL":
            # Format: YYYYMMDDTHHMMSSZ (UTC datetime)
            if not re.match(r"^\d{8}T\d{6}Z$", value):
                raise ValueError(
                    tr_multi(
                        f"Nevalida UNTIL-formato: {value!r}. "
                        f"Uzu YYYYMMDDTHHMMSSZ.",
                        f"Invalid UNTIL format: {value!r}. "
                        f"Use YYYYMMDDTHHMMSSZ.",
                        f"Format UNTIL invalide : {value!r}. "
                        f"Utilisez AAAAMMJJTHHMMSSZ.",
                    )
                )

        elif key in ("COUNT", "INTERVAL", "BYMONTHDAY", "BYSETPOS"):
            if not value.isdigit() or int(value) < 1:
                raise ValueError(
                    tr_multi(
                        f"{key} devas esti pozitiva entjero, "
                        f"ricevis {value!r}.",
                        f"{key} must be a positive integer, "
                        f"got {value!r}.",
                        f"{key} doit être un entier positif, "
                        f"a reçu {value!r}.",
                    )
                )

        elif key == "BYMONTH":
            if not value.isdigit() or not (1 <= int(value) <= 12):
                raise ValueError(
                    tr_multi(
                        f"BYMONTH devas esti inter 1 kaj 12, "
                        f"ricevis {value!r}.",
                        f"BYMONTH must be between 1 and 12, "
                        f"got {value!r}.",
                        f"BYMONTH doit être entre 1 et 12, "
                        f"a reçu {value!r}.",
                    )
                )

        elif key == "BYDAY":
            days = value.split(",")
            for d in days:
                # Strip optional prefix number (e.g. "1MO" -> "MO")
                day_code = d.lstrip("-0123456789")
                if day_code not in _WEEKDAYS:
                    raise ValueError(
                        tr_multi(
                            f"Nevalida BYDAY-valoro: {d!r}. "
                            f"Uzu MO,TU,WE,TH,FR,SA,SU.",
                            f"Invalid BYDAY value: {d!r}. "
                            f"Use MO,TU,WE,TH,FR,SA,SU.",
                            f"Valeur BYDAY invalide : {d!r}. "
                            f"Utilisez MO,TU,WE,TH,FR,SA,SU.",
                        )
                    )

        elif key == "WKST":
            if value not in _WEEKDAYS:
                raise ValueError(
                    tr_multi(
                        f"Nevalida WKST-valoro: {value!r}.",
                        f"Invalid WKST value: {value!r}.",
                        f"Valeur WKST invalide : {value!r}.",
                    )
                )

    if "FREQ" not in seen_keys:
        raise ValueError(
            tr_multi(
                "RRULE devas enhavi FREQ (ekz: FREQ=DAILY).",
                "RRULE must contain FREQ (e.g. FREQ=DAILY).",
                "RRULE doit contenir FREQ (ex: FREQ=DAILY).",
            )
        )

    return raw


def normalize_rrule(text: str | None) -> str:
    """Expand shorthand and validate an RRULE string.

    Args:
        text: Raw RRULE string, shorthand, or None.

    Returns:
        Normalized RRULE string, or empty string if None/empty.

    Raises:
        ValueError: If the input is not a valid RRULE after expansion.
    """
    if not text or not text.strip():
        return ""

    expanded = expand_shorthand(text)
    return validate_rrule(expanded)


__all__ = [
    "expand_shorthand",
    "validate_rrule",
    "normalize_rrule",
]
