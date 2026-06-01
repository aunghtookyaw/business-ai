from telegram.ext import Updater, MessageHandler, Filters, CommandHandler
from telegram import Update
from telegram.ext.callbackcontext import CallbackContext

from business_agent import answer_question
from config import (
    TELEGRAM_ALLOWED_CHAT_ID,
    TELEGRAM_ALLOWED_THREAD_ID,
    TELEGRAM_BOT_TOKEN,
)


COMMAND_QUESTIONS = {
    "/today_income": "today income",
    "/today_expense": "today expense",
    "/today_profit": "today profit",
    "/today_kpi": "today kpi",
    "/week_income": "this week income",
    "/week_expense": "this week expense",
    "/week_profit": "this week profit",
    "/week_kpi": "this week kpi",
    "/month_income": "this month income",
    "/month_expense": "this month expense",
    "/month_profit": "this month profit",
    "/month_kpi": "this month kpi",
    "/year_income": "this year income",
    "/year_expense": "this year expense",
    "/year_profit": "this year profit",
    "/year_kpi": "this year kpi",
    "/top_expenses": "top expenses",
    "/cash_flow": "cash flow",
    "/sector": "sector summary",
    "/compare_month": "compare month to month",
    "/compare_year": "compare year to year",
}


def _split_message(text, size=3900):
    return [
        text[i:i + size]
        for i in range(0, len(text), size)
    ]


def _normalize_command(text):
    command = text.strip().split()[0].split("@")[0].lower()
    return COMMAND_QUESTIONS.get(command, text)


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


def whereami(update: Update, context: CallbackContext):
    message = update.message
    if not _is_allowed_message(message):
        return

    message.reply_text(
        "chat_id: {chat_id}\nthread_id: {thread_id}".format(
            chat_id=message.chat_id,
            thread_id=_message_thread_id(message),
        )
    )


def handle_message(update: Update, context: CallbackContext):
    if not _is_allowed_message(update.message):
        return

    user_text = _normalize_command(update.message.text)

    try:
        answer = answer_question(user_text)

        for part in _split_message(answer):
            update.message.reply_text(part)

    except Exception as e:
        update.message.reply_text(
            f"Error: {str(e)}"
        )


def main():
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required.")
    if not TELEGRAM_ALLOWED_CHAT_ID:
        raise RuntimeError("TELEGRAM_ALLOWED_CHAT_ID is required.")
    if not TELEGRAM_ALLOWED_THREAD_ID:
        raise RuntimeError("TELEGRAM_ALLOWED_THREAD_ID is required.")

    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)

    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("whereami", whereami))

    dispatcher.add_handler(
        MessageHandler(Filters.text, handle_message)
    )

    print("Telegram AI Bot Running...")

    updater.start_polling()

    updater.idle()


if __name__ == "__main__":
    main()
