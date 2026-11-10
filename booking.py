"""New-booking conversation: facility → date → start → end → email → name → contact → confirm."""

import logging
from datetime import timedelta
from uuid import uuid4

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.error import TelegramError
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters

import calendar_kb
import config
import sheets
from helpers import (
    MENU_NEW,
    is_admin,
    keyboard,
    menu_filter_pattern,
    normalize_email,
    normalize_sg_phone,
    now,
    parse_hhmm,
    send_menu,
    summary,
)

log = logging.getLogger(__name__)

FACILITY, DATE, START, END, EMAIL, NAME, CONTACT, CONFIRM = (
    "BOOK_FACILITY", "BOOK_DATE", "BOOK_START", "BOOK_END",
    "BOOK_EMAIL", "BOOK_NAME", "BOOK_CONTACT", "BOOK_CONFIRM",
)

TEXT = filters.TEXT & ~filters.COMMAND


def _date_range():
    today = now().date()
    return today, today + timedelta(days=config.BOOKING_WINDOW_DAYS)


async def _ask_date(update: Update, text: str) -> str:
    first, last = _date_range()
    await update.effective_message.reply_text(text, reply_markup=calendar_kb.build(first, first, last))
    return DATE


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    context.user_data["booking"] = {"user_id": update.effective_user.id}
    rows = [config.FACILITIES[i : i + 3] for i in range(0, len(config.FACILITIES), 3)]
    await update.effective_message.reply_text("Which facility would you like to book?", reply_markup=keyboard(rows))
    return FACILITY


async def facility(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    choice = update.message.text.strip()
    if choice not in config.FACILITIES:
        await update.message.reply_text("Please pick a facility from the keyboard.")
        return FACILITY
    context.user_data["booking"]["facility"] = choice
    await update.message.reply_text(f"Facility: {choice}", reply_markup=ReplyKeyboardRemove())
    return await _ask_date(update, "Please select the date of booking")


async def date_picked(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    query = update.callback_query
    await query.answer()
    kind, value = calendar_kb.parse(query.data)
    first, last = _date_range()

    if kind == "month":
        await query.edit_message_reply_markup(calendar_kb.build(value, first, last))
        return DATE
    if kind != "day" or not first <= value <= last:
        return DATE

    context.user_data["booking"]["date"] = value
    await query.edit_message_text(f"Date: {value:%d/%m/%Y} ({value:%A})")
    await query.message.reply_text("Please enter the start time of booking (hhmm)")
    return START


async def date_typed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    await update.message.reply_text("Please pick a date from the calendar above.")
    return DATE


async def start_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    booking = context.user_data["booking"]
    t = parse_hhmm(update.message.text)
    if t is None:
        await update.message.reply_text("Invalid time format. Please enter the start time of booking (hhmm)")
        return START
    current = now()
    if booking["date"] == current.date() and t < current.time().replace(tzinfo=None):
        await update.message.reply_text("Start time cannot be before the current time. Please enter the start time (hhmm)")
        return START
    booking["start"] = t
    await update.message.reply_text("Please enter the end time of booking (hhmm)")
    return END


async def end_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    booking = context.user_data["booking"]
    t = parse_hhmm(update.message.text)
    if t is None:
        await update.message.reply_text("Invalid time format. Please enter the end time of booking (hhmm)")
        return END
    if t <= booking["start"]:
        await update.message.reply_text("End time must be after the start time. Please re-enter the end time.")
        return END
    booking["end"] = t

    clash = await sheets.find_conflict(booking["facility"], booking["date"], booking["start"], t)
    if clash:
        await update.message.reply_text(
            f"{clash.facility} is already booked by {clash.name} on {clash.day:%d/%m/%Y}, "
            f"from {clash.start:%H:%M} to {clash.end:%H:%M}."
        )
        return await _ask_date(update, "Please select another date, then enter a different time.")

    await update.message.reply_text("Please enter your email")
    return EMAIL


async def email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    value = normalize_email(update.message.text)
    if value is None:
        await update.message.reply_text("Invalid email. Please enter a valid email")
        return EMAIL
    context.user_data["booking"]["email"] = value
    await update.message.reply_text("Please enter your name")
    return NAME


async def name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    context.user_data["booking"]["name"] = update.message.text.strip()
    await update.message.reply_text("Please enter your contact number (+65)")
    return CONTACT


async def contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    value = normalize_sg_phone(update.message.text)
    if value is None:
        await update.message.reply_text("Invalid contact number. Please enter an 8-digit Singapore number")
        return CONTACT
    booking = context.user_data["booking"]
    booking["contact"] = value
    await update.message.reply_text(summary(booking) + "\nConfirm booking?", reply_markup=keyboard([["Yes", "No"]]))
    return CONFIRM


async def confirm_yes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    booking = context.user_data.pop("booking")

    if is_admin(update.effective_user.id):
        # Admin bookings skip approval, but still must not clash with one saved meanwhile.
        clash = await sheets.find_conflict(booking["facility"], booking["date"], booking["start"], booking["end"])
        if clash:
            await update.message.reply_text(f"Sorry, that slot was just taken ({clash.describe()}, {clash.name}).")
        else:
            await sheets.append_booking(booking)
            await update.message.reply_text("Your booking has been confirmed.\n\n" + summary(booking))
        await send_menu(update)
        return ConversationHandler.END

    booking_id = uuid4().hex
    request = {"booking": booking, "messages": {}}
    context.bot_data.setdefault("pending", {})[booking_id] = request

    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton("Approve", callback_data=f"approve:{booking_id}"),
        InlineKeyboardButton("Reject", callback_data=f"reject:{booking_id}"),
    ]])
    for admin_id in config.ADMIN_USERS:
        try:
            sent = await context.bot.send_message(admin_id, "New booking request:\n\n" + summary(booking), reply_markup=buttons)
            request["messages"][admin_id] = sent.message_id
        except TelegramError as e:
            log.error("Could not send booking request to admin %s: %s", admin_id, e)

    await update.message.reply_text(
        "Your booking request has been sent for approval. You will be notified once it is reviewed.\n\n" + summary(booking)
    )
    await send_menu(update)
    return ConversationHandler.END


async def confirm_no(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("booking", None)
    await update.message.reply_text("Booking discarded.")
    await send_menu(update)
    return ConversationHandler.END


async def confirm_other(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    await update.message.reply_text("Please answer Yes or No.", reply_markup=keyboard([["Yes", "No"]]))
    return CONFIRM


entry_points = [
    CommandHandler("new_booking", start),
    MessageHandler(filters.Regex(menu_filter_pattern(MENU_NEW)), start),
]

states = {
    FACILITY: [MessageHandler(TEXT, facility)],
    DATE: [CallbackQueryHandler(date_picked, pattern=calendar_kb.PATTERN), MessageHandler(TEXT, date_typed)],
    START: [MessageHandler(TEXT, start_time)],
    END: [MessageHandler(TEXT, end_time)],
    EMAIL: [MessageHandler(TEXT, email)],
    NAME: [MessageHandler(TEXT, name)],
    CONTACT: [MessageHandler(TEXT, contact)],
    CONFIRM: [
        MessageHandler(filters.Regex(r"(?i)^\s*yes\s*$"), confirm_yes),
        MessageHandler(filters.Regex(r"(?i)^\s*no\s*$"), confirm_no),
        MessageHandler(TEXT, confirm_other),
    ],
}
