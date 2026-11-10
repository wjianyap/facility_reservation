"""View-booking and cancel-booking conversations (looked up by email, as in the original bot)."""

from telegram import ReplyKeyboardRemove, Update
from telegram.ext import CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters

import sheets
from helpers import MENU_CANCEL, MENU_VIEW, keyboard, menu_filter_pattern, normalize_email, now, send_menu

VIEW_EMAIL, CANCEL_EMAIL, CANCEL_PICK = "VIEW_EMAIL", "CANCEL_EMAIL", "CANCEL_PICK"

TEXT = filters.TEXT & ~filters.COMMAND


# --- View -----------------------------------------------------------------

async def view_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    await update.effective_message.reply_text("Please enter your email to view your bookings", reply_markup=ReplyKeyboardRemove())
    return VIEW_EMAIL


async def view_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | str:
    email = normalize_email(update.message.text)
    if email is None:
        await update.message.reply_text("Invalid email. Please enter a valid email")
        return VIEW_EMAIL

    bookings = await sheets.bookings_for_email(email)
    if not bookings:
        await update.message.reply_text("No bookings found for this email.")
    else:
        details = "\n\n".join(
            f"Facility: {b.facility}\nDate: {b.day:%d/%m/%Y} ({b.day:%a})\n"
            f"Time: {b.start:%H:%M}-{b.end:%H:%M}\nName: {b.name}\nContact Number: {b.contact}"
            for b in bookings
        )
        await update.message.reply_text(f"Your bookings:\n\n{details}")

    await send_menu(update)
    return ConversationHandler.END


# --- Cancel ---------------------------------------------------------------

async def cancel_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    await update.effective_message.reply_text(
        "Please enter your email to view and cancel your bookings", reply_markup=ReplyKeyboardRemove()
    )
    return CANCEL_EMAIL


async def cancel_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | str:
    email = normalize_email(update.message.text)
    if email is None:
        await update.message.reply_text("Invalid email. Please enter a valid email")
        return CANCEL_EMAIL

    today = now().date()
    upcoming = [b for b in await sheets.bookings_for_email(email) if b.day >= today]
    if not upcoming:
        await update.message.reply_text("No upcoming bookings found for this email.")
        await send_menu(update)
        return ConversationHandler.END

    options = {f"Cancel {b.describe()}": b for b in upcoming}
    context.user_data["cancel_options"] = options
    rows = [[label] for label in options] + [["Back"]]
    await update.message.reply_text("Select a booking to cancel:", reply_markup=keyboard(rows))
    return CANCEL_PICK


async def cancel_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | str:
    text = update.message.text.strip()
    options = context.user_data.get("cancel_options", {})

    if text.lower() == "back":
        context.user_data.pop("cancel_options", None)
        await send_menu(update)
        return ConversationHandler.END

    booking = options.get(text)
    if booking is None:
        await update.message.reply_text("Please select a booking from the keyboard.")
        return CANCEL_PICK

    context.user_data.pop("cancel_options", None)
    if await sheets.delete_booking(booking):
        await update.message.reply_text(f"Booking for {booking.describe()} has been cancelled.")
    else:
        await update.message.reply_text("That booking could not be found any more — it may already have been cancelled.")
    await send_menu(update)
    return ConversationHandler.END


entry_points = [
    CommandHandler("view_booking", view_start),
    MessageHandler(filters.Regex(menu_filter_pattern(MENU_VIEW)), view_start),
    CommandHandler("cancel_booking", cancel_start),
    MessageHandler(filters.Regex(menu_filter_pattern(MENU_CANCEL)), cancel_start),
]

states = {
    VIEW_EMAIL: [MessageHandler(TEXT, view_email)],
    CANCEL_EMAIL: [MessageHandler(TEXT, cancel_email)],
    CANCEL_PICK: [MessageHandler(TEXT, cancel_pick)],
}
