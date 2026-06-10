import os
import json
import time
import traceback

from telegram import Update
from telegram.ext import CallbackContext, CommandHandler, Filters, MessageHandler, Updater
from tools.live_info import format_live_info_answer, live_info_context
from tools.openclaw_client import ask_ai
from tools.web_scraper import extract_urls, scrape_urls_from_text

try:
    import config
except ImportError:
    config = None


def _setting(name, default=None, aliases=None):
    for candidate in [name] + list(aliases or []):
        value = os.getenv(candidate)
        if value not in (None, ""):
            return value

    if config is not None:
        for candidate in [name] + list(aliases or []):
            value = getattr(config, candidate, None)
            if value not in (None, ""):
                return value

    return default


TELEGRAM_BOT_TOKEN = _setting(
    "FAMILY_TELEGRAM_BOT_TOKEN",
    aliases=["BIGSHOT_GUY_BOT_TOKEN"],
)
TELEGRAM_ALLOWED_CHAT_ID = _setting("FAMILY_ALLOWED_CHAT_ID")
TELEGRAM_ALLOWED_THREAD_ID = _setting("FAMILY_ALLOWED_THREAD_ID")
TELEGRAM_IGNORED_THREAD_IDS = _setting("FAMILY_IGNORED_THREAD_IDS", "")
AI_MODEL = _setting("FAMILY_AI_MODEL", "gemma4:e4b")
AUTO_DELETE_SECONDS = int(_setting("FAMILY_AUTO_DELETE_SECONDS", "86400"))


def _optional_int(value):
    if value in (None, ""):
        return None
    return int(value)


def _optional_int_set(value):
    if value in (None, ""):
        return set()
    return {
        int(item.strip())
        for item in value.split(",")
        if item.strip()
    }


def _message_thread_id(message):
    return getattr(message, "message_thread_id", None)


def _message_reject_reason(message):
    allowed_chat_id = _optional_int(TELEGRAM_ALLOWED_CHAT_ID)
    allowed_thread_id = _optional_int(TELEGRAM_ALLOWED_THREAD_ID)
    ignored_thread_ids = _optional_int_set(TELEGRAM_IGNORED_THREAD_IDS)
    message_thread_id = _message_thread_id(message)

    if allowed_chat_id is not None and message.chat_id != allowed_chat_id:
        return f"chat_id {message.chat_id} does not match {allowed_chat_id}"

    if allowed_thread_id is not None and message_thread_id != allowed_thread_id:
        return f"thread_id {message_thread_id} does not match {allowed_thread_id}"

    if message_thread_id in ignored_thread_ids:
        return f"thread_id {message_thread_id} is ignored"

    return None


def _is_allowed_message(message):
    if _message_reject_reason(message):
        return False

    return True


def _split_message(text, size=3900):
    return [
        text[i:i + size]
        for i in range(0, len(text), size)
    ]


def _delete_message_job(context: CallbackContext):
    data = context.job.context
    try:
        context.bot.delete_message(
            chat_id=data["chat_id"],
            message_id=data["message_id"],
        )
    except Exception as exc:
        print(f"Auto-delete skipped: {exc.__class__.__name__}: {exc}", flush=True)


def _schedule_auto_delete(context, message):
    if not context or AUTO_DELETE_SECONDS <= 0:
        return
    if not getattr(context, "job_queue", None):
        return
    message_id = getattr(message, "message_id", None)
    chat_id = getattr(message, "chat_id", None)
    if message_id is None or chat_id is None:
        return
    context.job_queue.run_once(
        _delete_message_job,
        AUTO_DELETE_SECONDS,
        context={"chat_id": chat_id, "message_id": message_id},
    )


def _reply_text(message, context, text):
    reply = message.reply_text(text)
    _schedule_auto_delete(context, reply)
    return reply


def _scraped_context(question):
    if not extract_urls(question):
        return ""

    scrape_result = scrape_urls_from_text(question)
    sections = []

    for page in scrape_result["pages"]:
        sections.append(
            "URL: {url}\nStatus: {status_code}\nContent-Type: {content_type}\nText:\n{text}".format(
                url=page["url"],
                status_code=page["status_code"],
                content_type=page["content_type"],
                text=page["text"],
            )
        )

    for error in scrape_result["errors"]:
        sections.append(
            "URL: {url}\nScrape error: {error}".format(
                url=error["url"],
                error=error["error"],
            )
        )

    if not sections:
        return ""

    return "\n\nWeb page content:\n" + "\n\n---\n\n".join(sections)


def ask_family_ai(question):
    live_context = live_info_context(question)
    if live_context:
        fallback_answer = format_live_info_answer(live_context)
        if live_context.get("error"):
            return fallback_answer

        prompt = f"""
You are BigShot_Guy_Bot helping a farming family.

Use only the live data below. Do not invent weather, prices, exchange rates, or sources.

Answer for agricultural use in this exact shape:
1. Main risk / market signal
2. What to do today
3. What to avoid
4. Weather / price data
5. Source

Keep it short and practical. If the user writes Burmese, answer in Burmese. If English, answer in English.
For weather: focus on spraying, fertilizer, irrigation, drainage, harvest, drying, and storage decisions.
For weather section 4: include each forecast day with date, condition, max/min temperature, and rain chance.
For vegetable price: focus on farm planning, margin signal, transport/currency risk, and say it is market signal, not final selling price.
For price section 4: include each price row with THB/kg and MMK/kg, plus the exchange rate.
For Makro, City Mart, or retail seller negotiation: help the user avoid reducing product quality or quantity unnecessarily.
For negotiation answers, explain the negotiation target, ceiling/walk-away warning, product reduction risk, and questions to ask the seller.
For negotiation section 4: include Makro/City Mart Myanmar retail rows, Thailand rows, Myanmar market-range rows, and sources if present.
If Myanmar local data is a range, use it as a signal only and say when the source is not a direct wholesale quote.
Do not summarize away the actual live rows. Include the actual forecast or price data from Live data.

Question:
{question}

Live data:
{json.dumps(live_context, indent=2, ensure_ascii=False, default=str)}
"""
        try:
            start_time = time.time()
            print(f"Calling local AI model={AI_MODEL} live_type={live_context.get('type')}", flush=True)
            answer = ask_ai(prompt, model=AI_MODEL, timeout=120).strip()
            elapsed = time.time() - start_time
            print(f"Local AI answered in {elapsed:.1f}s", flush=True)
            if answer:
                return answer
        except Exception as exc:
            print(f"Local AI failed: {exc.__class__.__name__}: {exc}", flush=True)
            traceback.print_exc()

        return fallback_answer

    web_context = _scraped_context(question)
    prompt = f"""
You are BigShot_Guy_Bot, the BigShot Family AI Assistant.

Rules:
- Help with family conversation, planning, explanation, writing, and general questions.
- Do not answer business finance questions; tell the user to ask big_lady_bot in the Finance topic.
- Do not claim access to files or private chats unless the user pasted the content.
- When web page content is provided, answer only from that content and clearly say if the page could not be read.
- Keep answers clear and practical.

Question:
{question}
{web_context}
"""
    start_time = time.time()
    print(f"Calling local AI model={AI_MODEL} live_type=none", flush=True)
    answer = ask_ai(prompt, model=AI_MODEL, timeout=120).strip()
    elapsed = time.time() - start_time
    print(f"Local AI answered in {elapsed:.1f}s", flush=True)
    return answer


def whereami(update: Update, context: CallbackContext):
    message = update.message
    reject_reason = _message_reject_reason(message)
    if reject_reason:
        print(f"Ignoring /whereami: {reject_reason}", flush=True)
        return

    _schedule_auto_delete(context, message)
    _reply_text(
        message,
        context,
        "chat_id: {chat_id}\nthread_id: {thread_id}".format(
            chat_id=message.chat_id,
            thread_id=_message_thread_id(message),
        )
    )


def handle_message(update: Update, context: CallbackContext):
    message = update.message
    print(
        "Received text chat_id={chat_id} thread_id={thread_id}".format(
            chat_id=message.chat_id,
            thread_id=_message_thread_id(message),
        ),
        flush=True,
    )

    reject_reason = _message_reject_reason(message)
    if reject_reason:
        print(f"Ignoring text: {reject_reason}", flush=True)
        return

    _schedule_auto_delete(context, message)
    try:
        answer = ask_family_ai(message.text)
        for part in _split_message(answer):
            _reply_text(message, context, part)
    except Exception as e:
        _reply_text(message, context, f"Error: {str(e)}")


def main():
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("FAMILY_TELEGRAM_BOT_TOKEN is required.")
    if not TELEGRAM_ALLOWED_CHAT_ID:
        raise RuntimeError("FAMILY_ALLOWED_CHAT_ID is required.")

    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("whereami", whereami))
    dispatcher.add_handler(MessageHandler(Filters.text, handle_message))

    print("Family AI Bot Running...", flush=True)
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
