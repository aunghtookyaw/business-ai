from telegram.ext import Filters, MessageHandler, Updater

from config import (
    TELEGRAM_ALLOWED_CHAT_ID,
    TELEGRAM_ALLOWED_THREAD_ID,
    TELEGRAM_BOT_TOKEN,
)
from tools.kpi_engine import calculate_kpi


def _optional_int(value):
    if value in (None, ""):
        return None
    return int(value)


def _message_thread_id(message):
    return getattr(message, "message_thread_id", None)


def _is_allowed_message(message):
    allowed_chat_id = _optional_int(TELEGRAM_ALLOWED_CHAT_ID)
    allowed_thread_id = _optional_int(TELEGRAM_ALLOWED_THREAD_ID)

    if allowed_chat_id is not None and message.chat_id != allowed_chat_id:
        return False

    if allowed_thread_id is not None and _message_thread_id(message) != allowed_thread_id:
        return False

    return True


def reply_message(update, context):
    if not _is_allowed_message(update.message):
        return

    user_question = update.message.text

    from tools.ai_kpi_engine import analyze_business

    ai_response = analyze_business(user_question)

    update.message.reply_text(ai_response)

    text = update.message.text.lower()

    # KPI COMMAND
    if "statistic" in text or "overview" in text:

        kpi = calculate_kpi()

        update.message.reply_text(kpi)


def main():
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required.")
    if not TELEGRAM_ALLOWED_CHAT_ID:
        raise RuntimeError("TELEGRAM_ALLOWED_CHAT_ID is required.")
    if not TELEGRAM_ALLOWED_THREAD_ID:
        raise RuntimeError("TELEGRAM_ALLOWED_THREAD_ID is required.")

    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)

    dispatcher = updater.dispatcher

    dispatcher.add_handler(
        MessageHandler(Filters.text, reply_message)
    )

    print("KPI Telegram Bot Running...")

    updater.start_polling()

    updater.idle()


if __name__ == "__main__":
    main()
