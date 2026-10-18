"""Deadline calculation under the Polish Civil Code (KC art. 111-115), with public holidays.

- art. 111: a term in days ends at the end of its last day; when the term starts from an event,
  the day of the event is not counted.
- art. 112: a term in weeks / months / years ends on the day that corresponds by name or date
  to the start day; if that day does not exist in the last month, on the last day of that month.
- art. 115: if the end falls on a statutory public holiday or a Saturday, the term ends on the
  next day that is neither.
"""

import calendar
import datetime as dt
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel

Unit = Literal["days", "weeks", "months", "years"]


def easter_sunday(year: int) -> dt.date:
    """Anonymous Gregorian algorithm (Meeus/Jones/Butcher)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month, day = divmod(h + l_ - 7 * m + 114, 31)
    return dt.date(year, month, day + 1)


@lru_cache(maxsize=64)
def polish_holidays(year: int) -> dict[dt.date, str]:
    """Statutory public holidays (ustawa o dniach wolnych od pracy)."""
    easter = easter_sunday(year)
    holidays = {
        dt.date(year, 1, 1): "Nowy Rok",
        dt.date(year, 1, 6): "Trzech Króli",
        easter: "Wielkanoc",
        easter + dt.timedelta(days=1): "Poniedziałek Wielkanocny",
        dt.date(year, 5, 1): "Święto Pracy",
        dt.date(year, 5, 3): "Święto Konstytucji 3 Maja",
        easter + dt.timedelta(days=49): "Zielone Świątki",
        easter + dt.timedelta(days=60): "Boże Ciało",
        dt.date(year, 8, 15): "Wniebowzięcie NMP",
        dt.date(year, 11, 1): "Wszystkich Świętych",
        dt.date(year, 11, 11): "Święto Niepodległości",
        dt.date(year, 12, 25): "Boże Narodzenie (pierwszy dzień)",
        dt.date(year, 12, 26): "Boże Narodzenie (drugi dzień)",
    }
    if year >= 2025:
        holidays[dt.date(year, 12, 24)] = "Wigilia Bożego Narodzenia"
    return holidays


def free_day_reason(day: dt.date) -> str | None:
    if (name := polish_holidays(day.year).get(day)) is not None:
        return f"{name} (dzień ustawowo wolny od pracy)"
    if day.weekday() == 6:
        return "niedziela (dzień ustawowo wolny od pracy)"
    if day.weekday() == 5:
        return "sobota"
    return None


def add_months(start: dt.date, months: int) -> dt.date:
    """Same day number `months` later; clamp to the last day of the month (art. 112)."""
    month_index = start.month - 1 + months
    year, month = start.year + month_index // 12, month_index % 12 + 1
    last = calendar.monthrange(year, month)[1]
    return dt.date(year, month, min(start.day, last))


class DeadlineResult(BaseModel):
    start: dt.date
    amount: int
    unit: Unit
    raw_end: dt.date  # before the art. 115 shift
    end: dt.date
    shifted: bool
    steps: list[str]
    legal_basis: list[str]  # provision ids


WEEKDAYS = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"]


def fmt(day: dt.date) -> str:
    return f"{day.isoformat()} ({WEEKDAYS[day.weekday()]})"


def calculate_deadline(
    start: dt.date, amount: int, unit: Unit, *, shift_free_days: bool = True
) -> DeadlineResult:
    """End of a term counted from an event on `start` (e.g. receipt of goods)."""
    if amount <= 0:
        raise ValueError("amount must be positive")
    steps = [f"Zdarzenie rozpoczynające bieg terminu: {fmt(start)}."]
    basis: list[str] = []
    if unit == "days":
        raw_end = start + dt.timedelta(days=amount)
        steps.append(
            f"Termin w dniach: dnia zdarzenia nie wlicza się, liczymy {amount} dni od następnego "
            f"dnia; termin kończy się z upływem dnia {fmt(raw_end)}."
        )
        basis.append("KC:art_111")
    else:
        months = {"weeks": 0, "months": amount, "years": 12 * amount}[unit]
        raw_end = (
            start + dt.timedelta(weeks=amount) if unit == "weeks" else add_months(start, months)
        )
        unit_pl = {"weeks": "tygodniach", "months": "miesiącach", "years": "latach"}[unit]
        steps.append(
            f"Termin w {unit_pl}: kończy się z upływem dnia, który nazwą lub datą odpowiada "
            f"początkowemu dniowi (albo ostatniego dnia miesiąca): {fmt(raw_end)}."
        )
        basis.append("KC:art_112")
    end = raw_end
    if shift_free_days:
        while (reason := free_day_reason(end)) is not None:
            steps.append(f"{fmt(end)} to {reason} — termin przesuwa się na następny dzień.")
            end += dt.timedelta(days=1)
        if end != raw_end:
            basis.append("KC:art_115")
    steps.append(f"Ostatni dzień terminu: {fmt(end)}.")
    return DeadlineResult(
        start=start,
        amount=amount,
        unit=unit,
        raw_end=raw_end,
        end=end,
        shifted=end != raw_end,
        steps=steps,
        legal_basis=basis,
    )
