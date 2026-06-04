from telegram.ext import Updater, MessageHandler, Filters, CommandHandler, CallbackQueryHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.ext.callbackcontext import CallbackContext

from business_agent import answer_question
from config import (
    TELEGRAM_ALLOWED_CHAT_ID,
    TELEGRAM_ALLOWED_THREAD_ID,
    TELEGRAM_BOT_TOKEN,
)
from tools.google_calendar_client import sync_financial_obligations_to_calendar

FINANCIAL_OBLIGATION_TEMPLATE = (
    "Use this format and edit values:\n"
    "add financial obligation creditor NAME amount 1000000 category Loan "
    "subcategory Investor Loan frequency Monthly start 2026-06-03 "
    "next due 2026-07-03 status Active notes optional text"
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

FINANCE_PROMPT_BUTTONS = [
    ["Today KPI", "Today income"],
    ["Today expense", "Today profit"],
    ["This week KPI", "This month KPI"],
    ["This month profit", "Cash flow"],
    ["Top expenses", "Top income"],
    ["Today transactions", "This month transactions"],
    ["Sector summary", "Compare month to month"],
    ["Compare year to year", "Business advice"],
    ["Sote Phwar summary", "Sote Phwar top invoices"],
    ["Sote Phwar vouchers", "Sote Phwar unpaid"],
    ["Sote Phwar 4L quantity", "Sote Phwar 1L quantity"],
    ["Sote Phwar 500 mL quantity", "Sote Phwar 100 mL quantity"],
    ["Sote inventory stock", "Sote inventory movement"],
    ["Factory stock", "Heho stock"],
    ["Sote Phwar customer search"],
    ["Obligation summary", "Obligation due soon"],
    ["Obligation list", "Sync obligation calendar"],
    ["Add obligation template"],
]

FINANCE_PROMPT_QUESTIONS = {
    "today kpi": "today kpi",
    "today income": "today income",
    "today expense": "today expense",
    "today profit": "today profit",
    "this week kpi": "this week kpi",
    "this month kpi": "this month kpi",
    "this month profit": "this month profit",
    "cash flow": "cash flow",
    "top expenses": "top expenses",
    "top income": "top income",
    "today transactions": "show transactions today",
    "this month transactions": "show transactions this month",
    "sector summary": "sector summary",
    "compare month to month": "compare month to month",
    "compare year to year": "compare year to year",
    "business advice": "business advice for this month",
    "sote phwar summary": "total in sotephwar transection this month",
    "sote phwar top invoices": "top 10 in sotephwar transection this month",
    "sote phwar vouchers": "show Sote Phwar vouchers by customer this month",
    "sote phwar unpaid": "show unpaid Sote Phwar vouchers by customer",
    "sote phwar 4l quantity": "Sotephwar inventory stock Sote Phwar 4L",
    "sote phwar 1l quantity": "Sotephwar inventory stock Sote Phwar 1L",
    "sote phwar 500 ml quantity": "Sotephwar inventory stock Sote Phwar 500 mL",
    "sote phwar 500ml quantity": "Sotephwar inventory stock Sote Phwar 500 mL",
    "sote phwar 100 ml quantity": "Sotephwar inventory stock Sote Phwar 100 mL",
    "sote phwar 100ml quantity": "Sotephwar inventory stock Sote Phwar 100 mL",
    "sote phwar customer search": "show Sote Phwar vouchers for customer name",
    "sote inventory stock": "Sotephwar inventory stock",
    "sote inventory movement": "Sotephwar inventory movement this month",
    "factory stock": "Sotephwar inventory stock factory",
    "heho stock": "Sotephwar inventory stock heho",
    "obligation summary": "financial obligations summary",
    "obligation due soon": "financial obligations due soon",
    "obligation list": "show financial obligations list",
    "sync obligation calendar": "__sync_obligation_calendar__",
    "add obligation template": FINANCIAL_OBLIGATION_TEMPLATE,
}

FINANCE_PROMPT_CALLBACKS = {
    "today_kpi": "Today KPI",
    "today_income": "Today income",
    "today_expense": "Today expense",
    "today_profit": "Today profit",
    "month_kpi": "This month KPI",
    "cash_flow": "Cash flow",
    "top_expenses": "Top expenses",
    "top_income": "Top income",
    "month_transactions": "This month transactions",
    "sote_summary": "Sote Phwar summary",
    "sote_top": "Sote Phwar top invoices",
    "sote_vouchers": "Sote Phwar vouchers",
    "sote_unpaid": "Sote Phwar unpaid",
    "sote_4l": "Sote Phwar 4L quantity",
    "sote_1l": "Sote Phwar 1L quantity",
    "sote_500ml": "Sote Phwar 500 mL quantity",
    "sote_100ml": "Sote Phwar 100 mL quantity",
    "sote_customer": "Sote Phwar customer search",
    "inv_stock": "Sote inventory stock",
    "inv_movement": "Sote inventory movement",
    "inv_factory": "Factory stock",
    "inv_heho": "Heho stock",
    "obl_summary": "Obligation summary",
    "obl_due": "Obligation due soon",
    "obl_list": "Obligation list",
    "obl_calendar": "Sync obligation calendar",
    "obl_template": "Add obligation template",
}


def _split_message(text, size=3900):
    return [
        text[i:i + size]
        for i in range(0, len(text), size)
    ]


def _finance_reply_markup():
    return ReplyKeyboardMarkup(
        FINANCE_PROMPT_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        selective=False,
    )


def _finance_inline_markup():
    rows = [
        ["today_kpi", "today_income"],
        ["today_expense", "today_profit"],
        ["month_kpi", "cash_flow"],
        ["top_expenses", "top_income"],
        ["month_transactions", "sote_summary"],
        ["sote_top", "sote_vouchers"],
        ["sote_unpaid", "sote_customer"],
        ["sote_4l", "sote_1l"],
        ["sote_500ml", "sote_100ml"],
        ["inv_stock", "inv_movement"],
        ["inv_factory", "inv_heho"],
        ["obl_summary", "obl_due"],
        ["obl_list", "obl_calendar"],
        ["obl_template"],
    ]
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(FINANCE_PROMPT_CALLBACKS[key], callback_data=f"finance:{key}")
            for key in row
        ]
        for row in rows
    ])


def _answer_finance_question(message, question):
    if question == FINANCIAL_OBLIGATION_TEMPLATE:
        message.reply_text(question, reply_markup=_finance_reply_markup())
        return
    if question == "__sync_obligation_calendar__":
        result = sync_financial_obligations_to_calendar()
        lines = [
            f"Calendar sync: {result['calendar_id']}",
            f"Synced: {len(result['synced'])}",
        ]
        for row in result["synced"][:10]:
            lines.append(
                "{action}: {creditor} {amount:,} due {next_due_date}".format(
                    action=row["action"],
                    creditor=row["creditor"] or "-",
                    amount=row["amount"],
                    next_due_date=row["next_due_date"],
                )
            )
        if result["errors"]:
            lines.append(f"Errors: {len(result['errors'])}")
            for error in result["errors"][:5]:
                lines.append(f"- {error['obligation_id']} {error['creditor']}: {error['error']}")
        message.reply_text("\n".join(lines), reply_markup=_finance_reply_markup())
        return

    answer = answer_question(question)
    for part in _split_message(answer):
        message.reply_text(part, reply_markup=_finance_reply_markup())


def _callback_question(data):
    prefix = "finance:"
    if not data.startswith(prefix):
        return None

    label = FINANCE_PROMPT_CALLBACKS.get(data[len(prefix):])
    if not label:
        return None

    return _normalize_command(label)


def _normalize_command(text):
    command = text.strip().split()[0].split("@")[0].lower()
    if command in COMMAND_QUESTIONS:
        return COMMAND_QUESTIONS[command]

    normalized_text = " ".join(text.strip().lower().split())
    return FINANCE_PROMPT_QUESTIONS.get(normalized_text, text)


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


def menu(update: Update, context: CallbackContext):
    message = update.message
    if not _is_allowed_message(message):
        return

    message.reply_text(
        "Tap a finance question:",
        reply_markup=_finance_inline_markup(),
    )
    message.reply_text(
        "Prompt keyboard opened.",
        reply_markup=_finance_reply_markup(),
    )


def sync_obligations_calendar(update: Update, context: CallbackContext):
    message = update.message
    if not _is_allowed_message(message):
        return

    try:
        _answer_finance_question(message, "__sync_obligation_calendar__")
    except Exception as e:
        message.reply_text(
            f"Calendar sync error: {str(e)}",
            reply_markup=_finance_reply_markup(),
        )


def handle_prompt_button(update: Update, context: CallbackContext):
    query = update.callback_query
    message = query.message
    if not _is_allowed_message(message):
        query.answer()
        return

    question = _callback_question(query.data or "")
    if not question:
        query.answer("Unknown prompt.")
        return

    query.answer("Running finance question...")
    print(f"Finance prompt button: {question}", flush=True)

    try:
        _answer_finance_question(message, question)
    except Exception as e:
        message.reply_text(
            f"Error: {str(e)}",
            reply_markup=_finance_reply_markup(),
        )


def handle_message(update: Update, context: CallbackContext):
    if not _is_allowed_message(update.message):
        return

    user_text = _normalize_command(update.message.text)
    print(f"Finance text: {user_text}", flush=True)

    try:
        _answer_finance_question(update.message, user_text)

    except Exception as e:
        update.message.reply_text(
            f"Error: {str(e)}",
            reply_markup=_finance_reply_markup(),
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
    dispatcher.add_handler(CommandHandler("menu", menu))
    dispatcher.add_handler(CommandHandler("prompts", menu))
    dispatcher.add_handler(CommandHandler("start", menu))
    dispatcher.add_handler(CommandHandler("sync_obligations_calendar", sync_obligations_calendar))
    dispatcher.add_handler(CallbackQueryHandler(handle_prompt_button, pattern=r"^finance:"))

    dispatcher.add_handler(
        MessageHandler(Filters.text, handle_message)
    )

    print("Telegram AI Bot Running...")

    updater.start_polling()

    updater.idle()


if __name__ == "__main__":
    main()
