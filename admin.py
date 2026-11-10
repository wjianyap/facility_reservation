"""Admin features: approving/rejecting booking requests and broadcasting messages."""

import logging

from telegram import ReplyKeyboardRemove, Update
from telegram.error import TelegramError
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters

import config
import sheets
from helpers import MENU_BROADCAST, admin_name, is_admin, keyboard, menu_filter_pattern, send_menu, summary

log = logging.getLogger(__name__)

BROADCAST_TEXT, BROADCAST_CONFIRM = "BROADCAST_TEXT", "BROADCAST_CONFIRM"

TEXT = filters.TEXT & ~filters.COMMAND


# --- Approve / reject -----------------------------------------------------

async def review(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("Only admins can review bookings.", show_alert=True)
        return

    action, booking_id = query.data.split(":", 1)
    pending = context.bot_data.setdefault("pending", {})
    request = pending.get(booking_id)
    if request is None:
        await query.answer("This request has already been handled.", show_alert=True)
        await query.edit_message_reply_markup(None)
        return

    booking = request["booking"]
    if action == "approve":
        clash = await sheets.find_conflict(booking["facility"], booking["date"], booking["start"], booking["end"])
        if clash:
            await query.answer(
                f"Clashes with {clash.name}'s booking ({clash.start:%H:%M}-{clash.end:%H:%M}). Reject this one instead.",
                show_alert=True,
            )
            return
        await sheets.append_booking(booking)

    del pending[booking_id]
    await query.answer()

    reviewer = admin_name(query.from_user.id)
    verdict = "approved" if action == "approve" else "rejected"

    try:
        await context.bot.send_message(
            booking["user_id"], f"Your booking request has been {verdict} by {reviewer}.\n\n{summary(booking)}"
        )
    except TelegramError as e:
        log.error("Could not notify user %s: %s", booking["user_id"], e)

    # Update every admin's copy so nobody acts on it twice.
    for admin_id, message_id in request["messages"].items():
        try:
            await context.bot.edit_message_text(
                f"Booking request {verdict.upper()} by {reviewer}:\n\n{summary(booking)}",
                chat_id=admin_id,
                message_id=message_id,
            )
        except TelegramError as e:
            log.error("Could not update request message for admin %s: %s", admin_id, e)


review_handler = CallbackQueryHandler(review, pattern=r"^(approve|reject):")


# --- Broadcast ------------------------------------------------------------

async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | str:
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("You are not authorized to broadcast messages.")
        await send_menu(update)
        return ConversationHandler.END
    await update.effective_message.reply_text(
        "Please enter the message you would like to broadcast to all users", reply_markup=ReplyKeyboardRemove()
    )
    return BROADCAST_TEXT


async def broadcast_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    context.user_data["broadcast"] = update.message.text
    await update.message.reply_text(
        f"Broadcast message: {update.message.text}\n\nConfirm broadcast?", reply_markup=keyboard([["Yes", "No"]])
    )
    return BROADCAST_CONFIRM


async def broadcast_yes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = context.user_data.pop("broadcast")
    sender = admin_name(update.effective_user.id)
    sent = 0
    for user_id in config.BROADCAST_USERS:
        try:
            await context.bot.send_message(user_id, f"Broadcasted Message from {sender}:\n{text}")
            sent += 1
        except TelegramError as e:
            log.error("Broadcast to %s failed: %s", user_id, e)
    await update.message.reply_text(f"Broadcast sent to {sent} of {len(config.BROADCAST_USERS)} users.")
    await send_menu(update)
    return ConversationHandler.END


async def broadcast_no(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("broadcast", None)
    await update.message.reply_text("Broadcast cancelled.")
    await send_menu(update)
    return ConversationHandler.END


entry_points = [
    CommandHandler("broadcast_message", broadcast_start),
    MessageHandler(filters.Regex(menu_filter_pattern(MENU_BROADCAST)), broadcast_start),
]

states = {
    BROADCAST_TEXT: [MessageHandler(TEXT, broadcast_text)],
    BROADCAST_CONFIRM: [
        MessageHandler(filters.Regex(r"(?i)^\s*yes\s*$"), broadcast_yes),
        MessageHandler(TEXT, broadcast_no),
    ],
}
