"""Tests for okazajo_rrule — RRULE validation and shorthand expansion."""

from __future__ import annotations

import pytest

from A_organizi.cli.okazajo_rrule import (
    expand_shorthand,
    normalize_rrule,
    validate_rrule,
)


class TestExpandShorthand:
    """Tests for expand_shorthand()."""

    def test_daily(self):
        assert expand_shorthand("daily") == "FREQ=DAILY"

    def test_weekly(self):
        assert expand_shorthand("weekly") == "FREQ=WEEKLY"

    def test_monthly(self):
        assert expand_shorthand("monthly") == "FREQ=MONTHLY"

    def test_yearly(self):
        assert expand_shorthand("yearly") == "FREQ=YEARLY"

    def test_weekdays(self):
        assert expand_shorthand("weekdays") == "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"

    def test_weekends(self):
        assert expand_shorthand("weekends") == "FREQ=WEEKLY;BYDAY=SA,SU"

    def test_case_insensitive(self):
        assert expand_shorthand("DAILY") == "FREQ=DAILY"
        assert expand_shorthand("Weekly") == "FREQ=WEEKLY"

    def test_passthrough_for_full_rrule(self):
        """Full RRULE strings pass through unchanged."""
        assert expand_shorthand("FREQ=DAILY") == "FREQ=DAILY"
        assert expand_shorthand("FREQ=WEEKLY;BYDAY=MO") == "FREQ=WEEKLY;BYDAY=MO"

    def test_passthrough_for_unknown(self):
        assert expand_shorthand("foobar") == "foobar"


class TestValidateRrule:
    """Tests for validate_rrule()."""

    def test_minimal_freq_daily(self):
        assert validate_rrule("FREQ=DAILY") == "FREQ=DAILY"

    def test_minimal_freq_weekly(self):
        assert validate_rrule("FREQ=WEEKLY") == "FREQ=WEEKLY"

    def test_freq_with_interval(self):
        assert validate_rrule("FREQ=WEEKLY;INTERVAL=2") == "FREQ=WEEKLY;INTERVAL=2"

    def test_freq_with_byday(self):
        assert validate_rrule("FREQ=WEEKLY;BYDAY=MO,WE,FR") == "FREQ=WEEKLY;BYDAY=MO,WE,FR"

    def test_freq_with_until(self):
        assert validate_rrule("FREQ=DAILY;UNTIL=20260602T235959Z") == "FREQ=DAILY;UNTIL=20260602T235959Z"

    def test_freq_with_count(self):
        assert validate_rrule("FREQ=DAILY;COUNT=10") == "FREQ=DAILY;COUNT=10"

    def test_freq_with_wkst(self):
        assert validate_rrule("FREQ=WEEKLY;WKST=MO") == "FREQ=WEEKLY;WKST=MO"

    def test_freq_with_bymonth(self):
        assert validate_rrule("FREQ=MONTHLY;BYMONTH=6") == "FREQ=MONTHLY;BYMONTH=6"

    def test_freq_with_bymonthday(self):
        assert validate_rrule("FREQ=MONTHLY;BYMONTHDAY=15") == "FREQ=MONTHLY;BYMONTHDAY=15"

    def test_empty_string(self):
        assert validate_rrule("") == ""

    # ── Validation errors ─────────────────────────────────────────────────

    def test_missing_freq(self):
        with pytest.raises(ValueError, match="FREQ"):
            validate_rrule("INTERVAL=2")

    def test_invalid_freq(self):
        with pytest.raises(ValueError, match="FREQ"):
            validate_rrule("FREQ=HOURLY")

    def test_unknown_parameter(self):
        with pytest.raises(ValueError, match="Nekonata|Unknown"):
            validate_rrule("FREQ=DAILY;FOO=bar")

    def test_duplicate_parameter(self):
        with pytest.raises(ValueError, match="Duobla|Duplicate"):
            validate_rrule("FREQ=DAILY;FREQ=WEEKLY")

    def test_invalid_until_format(self):
        with pytest.raises(ValueError, match="UNTIL"):
            validate_rrule("FREQ=DAILY;UNTIL=foobar")

    def test_invalid_count_zero(self):
        with pytest.raises(ValueError, match="COUNT"):
            validate_rrule("FREQ=DAILY;COUNT=0")

    def test_invalid_interval_negative(self):
        with pytest.raises(ValueError, match="INTERVAL"):
            validate_rrule("FREQ=DAILY;INTERVAL=-1")

    def test_invalid_bymonth(self):
        with pytest.raises(ValueError, match="BYMONTH"):
            validate_rrule("FREQ=YEARLY;BYMONTH=13")

    def test_invalid_byday(self):
        with pytest.raises(ValueError, match="BYDAY"):
            validate_rrule("FREQ=WEEKLY;BYDAY=XX")

    def test_invalid_wkst(self):
        with pytest.raises(ValueError, match="WKST"):
            validate_rrule("FREQ=WEEKLY;WKST=XX")

    def test_byday_with_prefix_number(self):
        """BYDAY allows optional prefix (e.g. 1MO for first Monday)."""
        assert validate_rrule("FREQ=MONTHLY;BYDAY=1MO") == "FREQ=MONTHLY;BYDAY=1MO"
        assert validate_rrule("FREQ=MONTHLY;BYDAY=-1FR") == "FREQ=MONTHLY;BYDAY=-1FR"

    def test_full_complex_rrule(self):
        rrule = "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,WE,FR;UNTIL=20261231T235959Z"
        assert validate_rrule(rrule) == rrule


class TestNormalizeRrule:
    """Tests for normalize_rrule() — expand + validate."""

    def test_none(self):
        assert normalize_rrule(None) == ""

    def test_empty(self):
        assert normalize_rrule("") == ""

    def test_whitespace(self):
        assert normalize_rrule("  ") == ""

    def test_shorthand_expansion(self):
        assert normalize_rrule("daily") == "FREQ=DAILY"
        assert normalize_rrule("weekly") == "FREQ=WEEKLY"

    def test_passthrough_valid(self):
        assert normalize_rrule("FREQ=MONTHLY;BYMONTHDAY=15") == "FREQ=MONTHLY;BYMONTHDAY=15"

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            normalize_rrule("FREQ=HOURLY")
