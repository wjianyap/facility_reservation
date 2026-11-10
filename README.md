# Facility Reservation Bot

A Telegram bot for booking facilities, built with [python-telegram-bot](https://python-telegram-bot.org) v22. It's a port of an earlier aiogram bot and uses the same `.env` variables and Google Sheet layout.

- Users choose a facility, pick a date from an inline calendar, enter start and end times and their contact details, then confirm.
- Admins get **Approve** / **Reject** buttons for each request. Approved bookings are written to the `Booking_Details` worksheet.
- Users can view and cancel their bookings by email. Admins can broadcast a message to all allowed users.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill it in
python bot.py
```

The service account in `GSHEET_CREDENTIALS` needs edit access to the sheet. Row 1 of the sheet is a header, and the columns are:
`user_id, facility, date (MM/DD/YYYY), start (HH:MM), end (HH:MM), time_period, email, name, contact_number`.

Conversation state and pending approval requests are saved to `bot_state.pickle`, so they survive a restart.

## Files

| File | Purpose |
|---|---|
| `bot.py` | Entry point: access control, `/start` `/help` `/about` `/end`, wiring of all handlers |
| `booking.py` | New-booking conversation |
| `manage.py` | View and cancel bookings |
| `admin.py` | Approve/reject requests, broadcast |
| `calendar_kb.py` | Inline calendar keyboard |
| `sheets.py` | Google Sheets reads/writes |
| `helpers.py` | Validation, menus, booking summary |
| `config.py` | Environment settings and facility list |
