"""Validation, keyboards and message helpers shared by the handlers."""

import re
from datetime import datetime, time

from email_validator import EmailNotValidError, validate_email
from telegram import ReplyKeyboardMarkup, Update

import config

MENU_NEW = "New Booking"
MENU_VIEW = "View Booking"
MENU_CANCEL = "Cancel Booking"
MENU_BROADCAST = "Broadcast Message"


def now() -> datetime:
    return datetime.now(config.TIMEZONE)


def parse_hhmm(text: str) -> time | None:
    text = text.strip()
    if not re.fullmatch(r"\d{4}", text):
        return None
    try:
        return datetime.strptime(text, "%H%M").time()
    except ValueError:
        return None


def normalize_email(text: str) -> str | None:
    try:
        # No DNS check: it would block the bot and fail on flaky networks.
        return validate_email(text.strip(), check_deliverability=False).normalized
    except EmailNotValidError:
        return None


def normalize_sg_phone(text: str) -> str | None:
    digits = re.sub(r"[\s-]", "", text.strip()).removeprefix("+65")
    return digits if re.fullmatch(r"[3689]\d{7}", digits) else None


def keyboard(rows: list[list[str]]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=True)


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_USERS


def admin_name(user_id: int) -> str:
    return config.ADMIN_USERS.get(user_id, str(user_id))


def summary(b: dict) -> str:
    return (
        "Booking Details\n"
        "================\n"
        f"Facility: {b['facility']}\n"
        f"Date: {b['date']:%d/%m/%Y} ({b['date']:%A})\n"
        f"Start time: {b['start']:%H:%M}\n"
        f"End time: {b['end']:%H:%M}\n"
        f"Email: {b['email']}\n"
        f"Name: {b['name']}\n"
        f"Contact Number: {b['contact']}\n"
    )


async def send_menu(update: Update) -> None:
    rows = [[MENU_NEW], [MENU_VIEW], [MENU_CANCEL]]
    text = "What would you like to do?"
    if is_admin(update.effective_user.id):
        rows.append([MENU_BROADCAST])
        text = "Welcome Admin! What would you like to do?"
    await update.effective_message.reply_text(text, reply_markup=keyboard(rows))


def menu_filter_pattern(label: str) -> str:
    """Regex matching a menu button label, case-insensitive."""
    return rf"(?i)^\s*{re.escape(label)}\s*$"
