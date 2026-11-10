"""Google Sheets storage for confirmed bookings.

The worksheet keeps the same columns as the original aiogram bot (row 1 is a header):
user_id | facility | date (MM/DD/YYYY) | start (HH:MM) | end (HH:MM) | time_period | email | name | contact_number

gspread is synchronous, so every call runs in a worker thread to avoid blocking the bot,
and the sheet is re-read each time so the bot never works from a stale copy.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, time

import gspread

import config

log = logging.getLogger(__name__)

_worksheet: gspread.Worksheet | None = None
_lock = asyncio.Lock()


@dataclass(frozen=True)
class Booking:
    facility: str
    day: date
    start: time
    end: time
    email: str
    name: str
    contact: str
    raw: tuple[str, ...]  # the sheet row exactly as read, used to find it again for deletion

    def overlaps(self, facility: str, day: date, start: time, end: time) -> bool:
        return self.facility == facility and self.day == day and start < self.end and end > self.start

    def describe(self) -> str:
        return f"{self.facility} on {self.day:%d/%m/%Y} {self.start:%H:%M}-{self.end:%H:%M}"


def _ws() -> gspread.Worksheet:
    global _worksheet
    if _worksheet is None:
        client = gspread.service_account_from_dict(config.GSHEET_CREDENTIALS)
        _worksheet = client.open_by_key(config.GSHEET_KEY_ID).worksheet(config.WORKSHEET_NAME)
    return _worksheet


def _parse(row: list[str]) -> Booking | None:
    try:
        return Booking(
            facility=row[1],
            # strptime also accepts the unpadded "1/5/2026" / "9:00" that Sheets may display.
            day=datetime.strptime(row[2], "%m/%d/%Y").date(),
            start=datetime.strptime(row[3], "%H:%M").time(),
            end=datetime.strptime(row[4], "%H:%M").time(),
            email=row[6],
            name=row[7],
            contact=row[8],
            raw=tuple(row),
        )
    except (IndexError, ValueError):
        log.warning("Skipping unreadable sheet row: %r", row)
        return None


def _fetch_sync() -> list[Booking]:
    rows = _ws().get_all_values()[1:]
    return [b for row in rows if (b := _parse(row))]


def _append_sync(row: list) -> None:
    _ws().append_row(row, value_input_option="USER_ENTERED")


def _delete_sync(raw: tuple[str, ...]) -> bool:
    rows = _ws().get_all_values()
    for index, row in enumerate(rows[1:], start=2):  # sheet rows are 1-based, row 1 is the header
        if tuple(row) == raw:
            _ws().delete_rows(index)
            return True
    return False


async def fetch_bookings() -> list[Booking]:
    async with _lock:
        return await asyncio.to_thread(_fetch_sync)


async def find_conflict(facility: str, day: date, start: time, end: time) -> Booking | None:
    for booking in await fetch_bookings():
        if booking.overlaps(facility, day, start, end):
            return booking
    return None


async def bookings_for_email(email: str) -> list[Booking]:
    email = email.lower()
    found = [b for b in await fetch_bookings() if b.email.lower() == email]
    return sorted(found, key=lambda b: (b.day, b.start))


async def append_booking(b: dict) -> None:
    row = [
        b["user_id"],
        b["facility"],
        b["date"].strftime("%m/%d/%Y"),
        b["start"].strftime("%H:%M"),
        b["end"].strftime("%H:%M"),
        f"{b['start']:%H:%M}-{b['end']:%H:%M}",
        b["email"],
        b["name"],
        b["contact"],
    ]
    async with _lock:
        await asyncio.to_thread(_append_sync, row)


async def delete_booking(booking: Booking) -> bool:
    async with _lock:
        return await asyncio.to_thread(_delete_sync, booking.raw)
