"""A small inline month calendar (replaces aiogram_calendar).

Callback data:
  cal:m:YYYY-MM     show another month
  cal:d:YYYY-MM-DD  a day was picked
  cal:x             no-op (headers, blanks, unavailable days)
"""

import calendar
from datetime import date, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

PATTERN = r"^cal:"
_NOOP = "cal:x"


def _noop(text: str = " ") -> InlineKeyboardButton:
    return InlineKeyboardButton(text, callback_data=_NOOP)


def build(month: date, first_day: date, last_day: date) -> InlineKeyboardMarkup:
    month = month.replace(day=1)
    prev_month = (month - timedelta(days=1)).replace(day=1)
    next_month = (month + timedelta(days=32)).replace(day=1)

    nav = [
        InlineKeyboardButton("«", callback_data=f"cal:m:{prev_month:%Y-%m}")
        if prev_month >= first_day.replace(day=1)
        else _noop(),
        _noop(f"{calendar.month_name[month.month]} {month.year}"),
        InlineKeyboardButton("»", callback_data=f"cal:m:{next_month:%Y-%m}")
        if next_month <= last_day
        else _noop(),
    ]
    rows = [nav, [_noop(d) for d in ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")]]

    for week in calendar.monthcalendar(month.year, month.month):
        row = []
        for d in week:
            if d == 0:
                row.append(_noop())
                continue
            day = month.replace(day=d)
            if first_day <= day <= last_day:
                row.append(InlineKeyboardButton(str(d), callback_data=f"cal:d:{day.isoformat()}"))
            else:
                row.append(_noop("·"))
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def parse(data: str) -> tuple[str, date | None]:
    """Return ("month", first-of-month), ("day", date) or ("noop", None)."""
    parts = data.split(":", 2)
    if len(parts) == 3 and parts[1] == "m":
        return "month", date.fromisoformat(parts[2] + "-01")
    if len(parts) == 3 and parts[1] == "d":
        return "day", date.fromisoformat(parts[2])
    return "noop", None
