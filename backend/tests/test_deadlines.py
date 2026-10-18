import datetime as dt

import pytest

from paragraf.agent.deadlines import (
    add_months,
    calculate_deadline,
    easter_sunday,
    free_day_reason,
    polish_holidays,
)

D = dt.date


@pytest.mark.parametrize(
    ("year", "expected"),
    [(2024, D(2024, 3, 31)), (2025, D(2025, 4, 20)), (2026, D(2026, 4, 5)), (2027, D(2027, 3, 28))],
)
def test_easter(year: int, expected: dt.date) -> None:
    assert easter_sunday(year) == expected


def test_movable_holidays_2026() -> None:
    holidays = polish_holidays(2026)
    assert D(2026, 4, 6) in holidays  # Easter Monday
    assert D(2026, 6, 4) in holidays  # Corpus Christi = Easter + 60
    assert D(2026, 12, 24) in holidays  # Christmas Eve is a holiday since 2025
    assert D(2024, 12, 24) not in polish_holidays(2024)


def test_add_months_clamps_to_end_of_month() -> None:
    assert add_months(D(2026, 1, 31), 1) == D(2026, 2, 28)
    assert add_months(D(2024, 1, 31), 1) == D(2024, 2, 29)
    assert add_months(D(2026, 11, 15), 3) == D(2027, 2, 15)


def test_days_exclude_event_day() -> None:
    # goods received Monday 2026-10-05; 14 days -> Monday 2026-10-19
    result = calculate_deadline(D(2026, 10, 5), 14, "days")
    assert result.end == D(2026, 10, 19)
    assert not result.shifted
    assert result.legal_basis == ["KC:art_111"]


def test_end_on_saturday_shifts_to_monday() -> None:
    # 2026-10-03 + 14 days = Saturday 2026-10-17 -> Monday 2026-10-19
    result = calculate_deadline(D(2026, 10, 3), 14, "days")
    assert result.raw_end == D(2026, 10, 17)
    assert result.end == D(2026, 10, 19)
    assert result.shifted
    assert "KC:art_115" in result.legal_basis


def test_end_on_holiday_chain_shifts_past_all_free_days() -> None:
    # raw end Wed 2025-12-24 (Wigilia) -> 25, 26 holidays, 27 Saturday, 28 Sunday -> Mon 29
    result = calculate_deadline(D(2025, 12, 10), 14, "days")
    assert result.raw_end == D(2025, 12, 24)
    assert result.end == D(2025, 12, 29)


def test_months_and_years() -> None:
    assert calculate_deadline(D(2026, 1, 31), 1, "months", shift_free_days=False).end == D(
        2026, 2, 28
    )
    assert calculate_deadline(D(2023, 3, 15), 3, "years").raw_end == D(2026, 3, 15)


def test_free_day_reason() -> None:
    assert free_day_reason(D(2026, 11, 11)) is not None
    assert free_day_reason(D(2026, 10, 18)) is not None  # Sunday
    assert free_day_reason(D(2026, 10, 19)) is None


def test_rejects_non_positive_amount() -> None:
    with pytest.raises(ValueError):
        calculate_deadline(D(2026, 1, 1), 0, "days")
