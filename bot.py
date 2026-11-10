"""Facility booking Telegram bot (python-telegram-bot v22). Run with:  python bot.py"""

import logging
import sys
import warnings

from telegram import BotCommand, ReplyKeyboardRemove, Update
from telegram.ext import (
    Application,
    ApplicationHandlerStop,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    PicklePersistence,
    TypeHandler,
)
from telegram.warnings import PTBUserWarning

import admin
import booking
import config
import manage
from helpers import send_menu

log = logging.getLogger(__name__)

COMMANDS = [
    BotCommand("start", "Start the bot"),
    BotCommand("new_booking", "Create new booking"),
    BotCommand("view_booking", "View your booking"),
    BotCommand("cancel_booking", "Cancel your booking"),
    BotCommand("help", "Get help"),
    BotCommand("about", "About the bot"),
    BotCommand("end", "End the current command"),
]


async def access_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Runs before every other handler (group -1) and drops updates from unknown users."""
    user = update.effective_user
    if user is None or user.id in config.ALLOWED_USERS:
        return
    log.warning("Unauthorized access denied for %s (id %s)", user.username, user.id)
    if update.callback_query:
        await update.callback_query.answer("You are not authorized to use this bot.", show_alert=True)
    elif update.effective_message:
        await update.effective_message.reply_text("You are not authorized to use this bot.")
    raise ApplicationHandlerStop


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _clear_flow_data(context)
    await send_menu(update)
    return ConversationHandler.END


async def end(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _clear_flow_data(context)
    await update.effective_message.reply_text(
        "Ending previous command...\nAnything else I can do for you?\n\nPlease type /start to start again.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lines = [f"/{c.command} — {c.description}" for c in COMMANDS]
    await update.effective_message.reply_text("Available commands:\n" + "\n".join(lines))


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "Facility booking bot: request a facility slot, and an admin will approve or reject it."
    )


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("Unhandled error", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("Sorry, something went wrong. Please try again, or /start over.")


def _clear_flow_data(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in ("booking", "cancel_options", "broadcast"):
        context.user_data.pop(key, None)


async def post_init(app: Application) -> None:
    await app.bot.set_my_commands(COMMANDS)


def build_app() -> Application:
    persistence = PicklePersistence(filepath=config.PERSISTENCE_FILE)
    app = Application.builder().token(config.TOKEN).persistence(persistence).post_init(post_init).build()

    app.add_handler(TypeHandler(Update, access_gate), group=-1)
    app.add_handler(admin.review_handler)

    # One conversation for every flow: starting any flow (or /start, /end) abandons the current one.
    flow_starters = booking.entry_points + manage.entry_points + admin.entry_points
    app.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler("start", start), *flow_starters],
            states={**booking.states, **manage.states, **admin.states},
            fallbacks=[CommandHandler("start", start), CommandHandler("end", end), *flow_starters],
            allow_reentry=True,
            name="main",
            persistent=True,
        )
    )

    app.add_handler(CommandHandler("end", end))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("about", about))
    app.add_error_handler(on_error)
    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # httpx logs every request URL at INFO, and those URLs contain the bot token.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    # Expected: the calendar uses a CallbackQueryHandler inside a per-chat conversation.
    warnings.filterwarnings("ignore", message=".*per_message.*", category=PTBUserWarning)

    build_app().run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
