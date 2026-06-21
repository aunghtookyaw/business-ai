import os
import re
import subprocess
import tempfile
import textwrap
from datetime import date, datetime
from pathlib import Path

from telegram.ext import Updater, MessageHandler, Filters, CommandHandler, CallbackQueryHandler, PicklePersistence
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext.callbackcontext import CallbackContext

from business_agent import answer_question
from config import (
    TELEGRAM_ALLOWED_CHAT_ID,
    TELEGRAM_ALLOWED_THREAD_ID,
    TELEGRAM_BOT_TOKEN,
)
from tools.bi_catalog import (
    BUSINESS_SECTOR,
    BUSINESS_MENU,
    MODULES,
    PRODUCT_BY_MODULE,
    STORE_BY_MODULE,
    report_needs_category,
    report_needs_customer,
    reports_for,
)
from tools.bi_executor import execute_intent
from tools.bi_intents import intent_from_state
from tools.bi_periods import (
    RELATIVE_PERIODS,
    date_period,
    legacy_period,
    month_days,
    month_period,
    period_label,
    range_period,
    relative_period,
)
from tools.bi_reports import format_text_report, temp_report_path, write_excel_report
from tools.bi_search import search_categories, search_customers
from tools.chart_pdf import (
    create_ceo_management_pdf_report,
    create_chart_pdf_report,
    create_chart_pdf_report_from_result,
)
from tools.comparison_reports import (
    BUSINESS_CONFIG,
    comparison_business,
    expense_month_comparison,
    is_expense_month_comparison,
)
from tools.executive_agent import answer_executive_question
from tools.executive_reports import write_executive_excel_report
from tools.formula_engine import master_name_comparison
from tools.google_calendar_client import sync_financial_obligations_to_calendar

SOTEPHWAR_PAYMENT_TEMPLATE = (
    "Use this format and edit values:\n"
    "Sote Phwar voucher NUMBER got 400000 kyats received date YYYY-MM-DD"
)

PDF_EXPORT_COMMAND = "__send_pdf__"
JPEG_EXPORT_COMMAND = "__send_jpeg__"
PDF_JPEG_EXPORT_COMMAND = "__send_pdf_jpeg__"
PDF_EXPORT_DEFAULT_QUESTION = "this month kpi"
PDF_EXPORT_TITLE = "BigShot Finance Report"
CEO_PDF_EXPORT_TITLE = "BigShot CEO Management Report"
AUTO_DELETE_SECONDS = int(os.getenv("FINANCE_AUTO_DELETE_SECONDS", "86400"))
BI_STATE_KEY = "bi_wizard"
BI_PERSISTENCE_FILE = os.getenv("FINANCE_BI_PERSISTENCE_FILE", "/private/tmp/business-ai-bi-wizard-state.pkl")
MASTER_COMPARE_GRANULARITIES = [
    ("day", "Day by Day"),
    ("week", "Week by Week"),
    ("month", "Month by Month"),
    ("year", "Year by Year"),
]


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

FINANCE_PROMPT_QUESTIONS = {
    "overall kpi": "this year KPI pdf",
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
    "sote payment template": SOTEPHWAR_PAYMENT_TEMPLATE,
}

FINANCE_PROMPT_CALLBACKS = {
    "overall_kpi": "Overall KPI",
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
    "sote_payment_template": "Sote payment template",
}


def _split_message(text, size=3900):
    return [
        text[i:i + size]
        for i in range(0, len(text), size)
    ]


def _remove_reply_keyboard():
    return ReplyKeyboardRemove()


def _finance_inline_markup():
    rows = [
        ["overall_kpi", "today_kpi"],
        ["today_income", "today_expense"],
        ["today_profit", "month_kpi"],
        ["cash_flow", "top_expenses"],
        ["top_income", "month_transactions"],
        ["sote_summary", "sote_top"],
        ["sote_vouchers", "sote_unpaid"],
        ["sote_customer", "sote_4l"],
        ["sote_1l", "sote_500ml"],
        ["sote_100ml", "inv_stock"],
        ["inv_movement", "inv_factory"],
        ["inv_heho", "obl_summary"],
        ["obl_due", "obl_list"],
        ["obl_calendar", "sote_payment_template"],
    ]
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(FINANCE_PROMPT_CALLBACKS[key], callback_data=f"finance:{key}")
            for key in row
        ]
        for row in rows
    ])


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


def _reply_text(message, context, text, **kwargs):
    reply = message.reply_text(text, **kwargs)
    _schedule_auto_delete(context, reply)
    return reply


def _reply_document(message, context, **kwargs):
    reply = message.reply_document(**kwargs)
    _schedule_auto_delete(context, reply)
    return reply


def _answer_finance_question(message, question, context=None):
    if _is_export_command(question):
        _send_export(message, question, context=context)
        return

    if question == SOTEPHWAR_PAYMENT_TEMPLATE:
        _reply_text(message, context, question, reply_markup=_remove_reply_keyboard())
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
        _reply_text(message, context, "\n".join(lines), reply_markup=_remove_reply_keyboard())
        return

    answer = answer_question(question)
    for part in _split_message(answer):
        _reply_text(message, context, part, reply_markup=_remove_reply_keyboard())


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
    if command in ("/send_pdf", "/send_jpeg", "/send_jpg", "/send_pdf_jpeg"):
        export_command = {
            "/send_pdf": PDF_EXPORT_COMMAND,
            "/send_jpeg": JPEG_EXPORT_COMMAND,
            "/send_jpg": JPEG_EXPORT_COMMAND,
            "/send_pdf_jpeg": PDF_JPEG_EXPORT_COMMAND,
        }[command]
        return _export_command_with_question(export_command, text.strip().split(maxsplit=1))

    if command in COMMAND_QUESTIONS:
        return COMMAND_QUESTIONS[command]

    normalized_text = " ".join(text.strip().lower().split())
    if _is_ceo_management_pdf_request(normalized_text):
        return f"{PDF_EXPORT_COMMAND}:{text.strip()}"
    if normalized_text in ("send pdf and jpeg", "send pdf and jpg", "send jpeg and pdf", "send jpg and pdf"):
        return PDF_JPEG_EXPORT_COMMAND
    if normalized_text.startswith("send pdf and jpeg "):
        return f"{PDF_JPEG_EXPORT_COMMAND}:{text.strip()[len('send pdf and jpeg '):].strip()}"
    if normalized_text.startswith("send pdf and jpg "):
        return f"{PDF_JPEG_EXPORT_COMMAND}:{text.strip()[len('send pdf and jpg '):].strip()}"
    if normalized_text.startswith("send jpeg and pdf "):
        return f"{PDF_JPEG_EXPORT_COMMAND}:{text.strip()[len('send jpeg and pdf '):].strip()}"
    if normalized_text.startswith("send jpg and pdf "):
        return f"{PDF_JPEG_EXPORT_COMMAND}:{text.strip()[len('send jpg and pdf '):].strip()}"
    for suffix in (" send pdf and jpeg", " send pdf and jpg", " send jpeg and pdf", " send jpg and pdf"):
        if normalized_text.endswith(suffix):
            return f"{PDF_JPEG_EXPORT_COMMAND}:{text.strip()[:-len(suffix)].strip()}"

    if normalized_text == "send pdf":
        return PDF_EXPORT_COMMAND
    if normalized_text.startswith("send pdf "):
        return f"{PDF_EXPORT_COMMAND}:{text.strip()[len('send pdf '):].strip()}"
    if normalized_text.endswith(" send pdf"):
        return f"{PDF_EXPORT_COMMAND}:{text.strip()[:-len(' send pdf')].strip()}"

    if normalized_text in ("send jpeg", "send jpg"):
        return JPEG_EXPORT_COMMAND
    if normalized_text.startswith("send jpeg "):
        return f"{JPEG_EXPORT_COMMAND}:{text.strip()[len('send jpeg '):].strip()}"
    if normalized_text.startswith("send jpg "):
        return f"{JPEG_EXPORT_COMMAND}:{text.strip()[len('send jpg '):].strip()}"
    for suffix in (" send jpeg", " send jpg"):
        if normalized_text.endswith(suffix):
            return f"{JPEG_EXPORT_COMMAND}:{text.strip()[:-len(suffix)].strip()}"

    return FINANCE_PROMPT_QUESTIONS.get(normalized_text, text)


def _is_ceo_management_pdf_request(normalized_text):
    if _is_export_command(normalized_text):
        normalized_text = _export_question(normalized_text)
    is_pdf_report = "pdf" in normalized_text or "report" in normalized_text
    is_kpi_management_report = (
        "kpi" in normalized_text
        and (
            "pdf" in normalized_text
            or "report" in normalized_text
            or "management" in normalized_text
            or "dashboard" in normalized_text
        )
    )
    explicit_ceo_report = (
        "ceo" in normalized_text
        or "chief executive" in normalized_text
        or "management report" in normalized_text
        or "monthly management report" in normalized_text
    )
    local_ai_ceo_alias = (
        is_pdf_report
        and ("local ai" in normalized_text or "qwen" in normalized_text or "qwen3" in normalized_text)
        and ("finance" in normalized_text or "business" in normalized_text)
    )
    return (
        is_pdf_report
        and (explicit_ceo_report or local_ai_ceo_alias or is_kpi_management_report)
    )


def _export_title_for_question(question):
    normalized_text = " ".join(str(question).strip().lower().split())
    if _is_ceo_management_pdf_request(normalized_text):
        return CEO_PDF_EXPORT_TITLE
    return PDF_EXPORT_TITLE


def _export_command_with_question(export_command, parts):
    if len(parts) == 1:
        return export_command
    return f"{export_command}:{parts[1]}"


def _is_export_command(command):
    return any(
        command == export_command or command.startswith(f"{export_command}:")
        for export_command in (PDF_EXPORT_COMMAND, JPEG_EXPORT_COMMAND, PDF_JPEG_EXPORT_COMMAND)
    )


def _pdf_export_question(command):
    return _export_question(command)


def _export_question(command):
    if command == PDF_EXPORT_COMMAND:
        return PDF_EXPORT_DEFAULT_QUESTION
    if command == JPEG_EXPORT_COMMAND:
        return PDF_EXPORT_DEFAULT_QUESTION
    if command == PDF_JPEG_EXPORT_COMMAND:
        return PDF_EXPORT_DEFAULT_QUESTION

    for export_command in (PDF_EXPORT_COMMAND, JPEG_EXPORT_COMMAND, PDF_JPEG_EXPORT_COMMAND):
        prefix = f"{export_command}:"
        if command.startswith(prefix):
            question = command[len(prefix):].strip()
            if question:
                normalized = _normalize_command(question)
                nested_prefix = f"{export_command}:"
                if normalized.startswith(nested_prefix):
                    return normalized[len(nested_prefix):].strip()
                if _is_export_command(normalized):
                    return _export_question(normalized)
                return normalized

    return PDF_EXPORT_DEFAULT_QUESTION


def _safe_export_filename(title, extension):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_").lower()
    if not slug:
        slug = "bigshot_finance_report"
    return f"{slug}_{timestamp}.{extension}"


def _safe_pdf_filename(title):
    return _safe_export_filename(title, "pdf")


def _pdf_text_bytes(text):
    replacements = {
        "\\": "\\\\",
        "(": "\\(",
        ")": "\\)",
        "\r": "",
    }
    encoded = []
    for char in text:
        if char == "\n":
            encoded.append(r"\n")
        elif char in replacements:
            encoded.append(replacements[char])
        elif ord(char) < 128:
            encoded.append(char)
        else:
            encoded.append("?")
    return "".join(encoded).encode("latin-1")


def _write_basic_pdf(text, output_path, title=PDF_EXPORT_TITLE):
    wrapped_lines = []
    for paragraph in text.splitlines() or [""]:
        wrapped = textwrap.wrap(paragraph, width=88) or [""]
        wrapped_lines.extend(wrapped)

    lines_per_page = 48
    pages = [
        wrapped_lines[i:i + lines_per_page]
        for i in range(0, len(wrapped_lines), lines_per_page)
    ] or [[""]]

    objects = []
    page_ids = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(None)
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    for page in pages:
        content_id = len(objects) + 2
        page_id = len(objects) + 1
        page_ids.append(page_id)
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
            ).encode("latin-1")
        )
        stream_lines = [
            "BT",
            "/F1 11 Tf",
            "50 795 Td",
            "14 TL",
            f"({_pdf_text_bytes(title).decode('latin-1')}) Tj",
            "T*",
            "T*",
        ]
        for line in page:
            stream_lines.append(f"({_pdf_text_bytes(line).decode('latin-1')}) Tj")
            stream_lines.append("T*")
        stream_lines.append("ET")
        stream = "\n".join(stream_lines).encode("latin-1")
        objects.append(
            b"<< /Length " + str(len(stream)).encode("latin-1") + b" >>\nstream\n" + stream + b"\nendstream"
        )

    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("latin-1")

    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode("latin-1"))
        output.extend(obj)
        output.extend(b"\nendobj\n")

    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("latin-1")
    )
    Path(output_path).write_bytes(output)


def _write_pdf_export(text, output_path, title=PDF_EXPORT_TITLE):
    with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as source:
        source.write(f"{title}\n\n{text}")
        source_path = source.name

    try:
        try:
            result = subprocess.run(
                [
                    "cupsfilter",
                    "-i",
                    "text/plain",
                    "-m",
                    "application/pdf",
                    "-t",
                    title,
                    source_path,
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if result.returncode == 0 and result.stdout.startswith(b"%PDF"):
                Path(output_path).write_bytes(result.stdout)
                return
        except OSError:
            pass
    finally:
        try:
            os.unlink(source_path)
        except OSError:
            pass

    _write_basic_pdf(text, output_path, title=title)


def _write_jpeg_export(pdf_path, jpeg_path):
    result = subprocess.run(
        [
            "sips",
            "-s",
            "format",
            "jpeg",
            str(pdf_path),
            "--out",
            str(jpeg_path),
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0 or not Path(jpeg_path).exists():
        raise RuntimeError("JPEG export failed.")


def _send_export(message, command, context=None):
    export_question = _export_question(command)
    send_pdf = command == PDF_EXPORT_COMMAND or command.startswith(f"{PDF_EXPORT_COMMAND}:")
    send_jpeg = command == JPEG_EXPORT_COMMAND or command.startswith(f"{JPEG_EXPORT_COMMAND}:")
    send_both = command == PDF_JPEG_EXPORT_COMMAND or command.startswith(f"{PDF_JPEG_EXPORT_COMMAND}:")
    export_title = _export_title_for_question(export_question)

    with tempfile.TemporaryDirectory() as temp_dir:
        pdf_filename = _safe_export_filename(export_title, "pdf")
        jpeg_filename = _safe_export_filename(export_title, "jpg")
        pdf_path = Path(temp_dir) / pdf_filename
        jpeg_path = Path(temp_dir) / jpeg_filename
        if not create_chart_pdf_report(export_question, pdf_path, title=export_title):
            answer = answer_question(export_question)
            _write_pdf_export(answer, pdf_path, title=export_title)
        if send_pdf or send_both:
            with pdf_path.open("rb") as pdf_file:
                _reply_document(
                    message,
                    context,
                    document=pdf_file,
                    filename=pdf_filename,
                    caption=f"PDF export: {export_question}",
                    reply_markup=_remove_reply_keyboard(),
                )
        if send_jpeg or send_both:
            _write_jpeg_export(pdf_path, jpeg_path)
            with jpeg_path.open("rb") as jpeg_file:
                _reply_document(
                    message,
                    context,
                    document=jpeg_file,
                    filename=jpeg_filename,
                    caption=f"JPEG export: {export_question}",
                    reply_markup=_remove_reply_keyboard(),
                )


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


def _bi_state(context):
    if not hasattr(context, "user_data") or context.user_data is None:
        context.user_data = {}
    return context.user_data.setdefault(BI_STATE_KEY, {})


def _reset_bi_state(context):
    if hasattr(context, "user_data") and context.user_data is not None:
        context.user_data[BI_STATE_KEY] = {}


def _button_rows(items, prefix, columns=2):
    buttons = [
        InlineKeyboardButton(label, callback_data=f"{prefix}:{key}")
        for key, label in items
    ]
    return [
        buttons[index:index + columns]
        for index in range(0, len(buttons), columns)
    ]


def _nav_row(include_back=True):
    row = []
    if include_back:
        row.append(InlineKeyboardButton("Back", callback_data="bi:back"))
    row.append(InlineKeyboardButton("Home", callback_data="bi:home"))
    row.append(InlineKeyboardButton("Cancel", callback_data="bi:cancel"))
    return row


def _send_bi_message(message, context, text, rows, include_back=True):
    markup_rows = rows + [_nav_row(include_back=include_back)]
    return _reply_text(
        message,
        context,
        text,
        reply_markup=InlineKeyboardMarkup(markup_rows),
    )


def _show_bi_home(message, context):
    _reset_bi_state(context)
    rows = [[InlineKeyboardButton("Overall KPI", callback_data="bi:overall_kpi")]]
    rows.append([InlineKeyboardButton("Compare", callback_data="bi:prompt_enquiry")])
    home_business_menu = [
        item for item in BUSINESS_MENU
        if item[0] != "extension"
    ]
    rows.extend(_button_rows(home_business_menu, "bi:business"))
    return _send_bi_message(
        message,
        context,
        "Business Intelligence",
        rows,
        include_back=False,
    )


def _show_prompt_enquiry_menu(message, context):
    state = _bi_state(context)
    state.clear()
    state["step"] = "master_compare_mode"
    rows = _button_rows(
        [("same", "Same Category"), ("different", "Different Category")],
        "bi:master_mode",
        columns=1,
    )
    return _send_bi_message(message, context, "Compare: choose category comparison:", rows)


def _show_master_granularity_menu(message, context):
    state = _bi_state(context)
    state["step"] = "master_granularity"
    rows = _button_rows(MASTER_COMPARE_GRANULARITIES, "bi:master_granularity", columns=2)
    return _send_bi_message(message, context, "Choose time of enquiry:", rows)


def _show_module_menu(message, context):
    state = _bi_state(context)
    business = state.get("business")
    rows = _button_rows(MODULES.get(business, []), "bi:module")
    return _send_bi_message(message, context, "Choose report area:", rows)


def _show_report_menu(message, context):
    state = _bi_state(context)
    reports = reports_for(state.get("business"), state.get("module"))
    rows = _button_rows(reports, "bi:report")
    return _send_bi_message(message, context, "Choose report:", rows)


def _show_period_menu(message, context):
    rows = _button_rows(RELATIVE_PERIODS, "bi:period", columns=2)
    rows.extend([
        [
            InlineKeyboardButton("Custom Month", callback_data="bi:custom:month"),
            InlineKeyboardButton("Custom Date", callback_data="bi:custom:date"),
        ],
        [InlineKeyboardButton("Custom Date Range", callback_data="bi:custom:range")],
    ])
    return _send_bi_message(message, context, "Choose period:", rows)


def _show_output_menu(message, context):
    rows = _button_rows(
        [("text", "Text Report"), ("pdf", "PDF Report"), ("excel", "Excel Report")],
        "bi:output",
        columns=1,
    )
    return _send_bi_message(
        message,
        context,
        "Choose output format:",
        rows,
    )


def _show_comparison_output_menu(message, context, question):
    state = _bi_state(context)
    business = comparison_business(question)
    business_title = BUSINESS_CONFIG[business]["title"]
    state.clear()
    state["comparison_question"] = question
    state["comparison_business"] = business
    state["step"] = "comparison_output"
    rows = _button_rows(
        [("text", "Text Report"), ("pdf", "PDF Report"), ("excel", "Excel Report")],
        "bi:output",
        columns=1,
    )
    return _send_bi_message(
        message,
        context,
        f"Choose output format for {business_title} expense comparison:",
        rows,
        include_back=False,
    )


def _start_custom_calendar(message, context, kind):
    state = _bi_state(context)
    state["calendar_kind"] = kind
    if kind == "range":
        state["range_stage"] = "start"
        state.pop("range_start", None)
    return _show_calendar_years(message, context, date.today().year)


def _show_calendar_years(message, context, year):
    rows = [
        [
            InlineKeyboardButton(str(year - 1), callback_data=f"bi:cal:year:{year - 1}"),
            InlineKeyboardButton(str(year), callback_data=f"bi:cal:year:{year}"),
            InlineKeyboardButton(str(year + 1), callback_data=f"bi:cal:year:{year + 1}"),
        ],
        [
            InlineKeyboardButton("<", callback_data=f"bi:cal:years:{year - 3}"),
            InlineKeyboardButton(">", callback_data=f"bi:cal:years:{year + 3}"),
        ],
    ]
    return _send_bi_message(message, context, "Choose year:", rows)


def _show_calendar_months(message, context, year):
    labels = [
        ("1", "Jan"), ("2", "Feb"), ("3", "Mar"), ("4", "Apr"),
        ("5", "May"), ("6", "Jun"), ("7", "Jul"), ("8", "Aug"),
        ("9", "Sep"), ("10", "Oct"), ("11", "Nov"), ("12", "Dec"),
    ]
    rows = _button_rows(labels, f"bi:cal:month:{year}", columns=3)
    return _send_bi_message(message, context, f"Choose month in {year}:", rows)


def _show_calendar_dates(message, context, year, month):
    days = month_days(year, month)
    buttons = [
        InlineKeyboardButton(str(day.day), callback_data=f"bi:cal:date:{day.isoformat()}")
        for day in days
    ]
    rows = [
        buttons[index:index + 7]
        for index in range(0, len(buttons), 7)
    ]
    return _send_bi_message(message, context, f"Choose date in {year}-{month:02d}:", rows)


def _after_report_selected(message, context):
    state = _bi_state(context)
    state.pop("awaiting", None)
    state.pop("candidates", None)
    module = state.get("module")
    if module in STORE_BY_MODULE:
        state["store"] = STORE_BY_MODULE[module]
    if module in PRODUCT_BY_MODULE:
        state["product"] = PRODUCT_BY_MODULE[module]

    report = state.get("report")
    if report_needs_customer(report):
        state["awaiting"] = "customer"
        return _reply_text(
            message,
            context,
            "Type customer name to search.",
            reply_markup=_remove_reply_keyboard(),
        )
    if report_needs_category(report):
        state["awaiting"] = "category"
        state["categories"] = []
        category_type = "income name" if module == "income" else "expense category"
        return _reply_text(
            message,
            context,
            f"Type {category_type} to search. You can type multiple lines, select more than one category, then press Done.",
            reply_markup=_remove_reply_keyboard(),
        )
    return _show_period_menu(message, context)


def _handle_search_text(message, context, text):
    state = _bi_state(context)
    awaiting = state.get("awaiting")
    if awaiting == "customer":
        matches = search_customers(text)
        label = "customer"
        prefix = "bi:select_customer"
    elif awaiting == "category":
        matches = []
        seen = set()
        terms = [line.strip() for line in text.splitlines() if line.strip()] or [text]
        sector = BUSINESS_SECTOR.get(state.get("business"))
        income_expense = "Income" if state.get("module") == "income" else "Expense"
        for term in terms:
            for match in search_categories(term, sector=sector, income_expense=income_expense):
                if match["value"] in seen:
                    continue
                seen.add(match["value"])
                matches.append(match)
        label = "income name" if state.get("module") == "income" else "category"
        prefix = "bi:select_category"
    elif awaiting == "master_category":
        matches = []
        seen = set()
        terms = [line.strip() for line in text.splitlines() if line.strip()] or [text]
        for term in terms:
            for match in search_categories(term):
                if match["value"] in seen:
                    continue
                seen.add(match["value"])
                matches.append(match)
        label = "category"
        prefix = "bi:select_master_category"
    else:
        return False

    state["candidates"] = [match["value"] for match in matches]
    if not matches:
        _reply_text(
            message,
            context,
            f"No matching {label} found. Try another search.",
            reply_markup=_remove_reply_keyboard(),
        )
        return True

    rows = [
        [InlineKeyboardButton(match["value"], callback_data=f"{prefix}:{index}")]
        for index, match in enumerate(matches)
    ]
    if awaiting == "master_category" and state.get("master_categories"):
        rows.append([InlineKeyboardButton("Done", callback_data="bi:master_category_done")])
        selected = "\n".join(f"- {category}" for category in state["master_categories"])
        return _send_bi_message(message, context, f"Selected categories:\n{selected}\n\nSelect more category:", rows)
    if awaiting == "category" and state.get("categories"):
        rows.append([InlineKeyboardButton("Done", callback_data="bi:category_done")])
        selected = "\n".join(f"- {category}" for category in state["categories"])
        return _send_bi_message(message, context, f"Selected categories:\n{selected}\n\nSelect more category:", rows)
    _send_bi_message(message, context, f"Select {label}:", rows)
    return True


def _execute_bi_output(message, context):
    state = _bi_state(context)
    intent = intent_from_state(state)
    payload = execute_intent(intent)
    output = intent.output
    if output == "text":
        for part in _split_message(format_text_report(payload)):
            _reply_text(message, context, part, reply_markup=_remove_reply_keyboard())
        return

    if output == "pdf":
        path = temp_report_path(".pdf")
        created = create_chart_pdf_report_from_result(
            payload["result"],
            payload["title"],
            path,
            title=payload["title"],
        )
        if not created:
            _write_pdf_export(format_text_report(payload), path, title=payload["title"])
        with path.open("rb") as document:
            _reply_document(
                message,
                context,
                document=document,
                filename=_safe_export_filename(payload["title"], "pdf"),
                caption=payload["title"],
                reply_markup=_remove_reply_keyboard(),
            )
        path.unlink(missing_ok=True)
        return

    path = temp_report_path(".xlsx")
    write_excel_report(payload, path)
    with path.open("rb") as document:
        _reply_document(
            message,
            context,
            document=document,
            filename=_safe_export_filename(payload["title"], "xlsx"),
            caption=payload["title"],
            reply_markup=_remove_reply_keyboard(),
        )
    path.unlink(missing_ok=True)


def _execute_comparison_output(message, context):
    state = _bi_state(context)
    output = state.get("output")
    question = state.get("comparison_question") or "compare expenses last month and this month"
    business = state.get("comparison_business") or comparison_business(question)
    payload = expense_month_comparison(question, business)

    if output == "text":
        for part in _split_message(format_text_report(payload)):
            _reply_text(message, context, part, reply_markup=_remove_reply_keyboard())
        return

    if output == "pdf":
        path = temp_report_path(".pdf")
        created = create_chart_pdf_report_from_result(
            payload["result"],
            payload["title"],
            path,
            title=payload["title"],
        )
        if not created:
            _write_pdf_export(format_text_report(payload), path, title=payload["title"])
        with path.open("rb") as document:
            _reply_document(
                message,
                context,
                document=document,
                filename=_safe_export_filename(payload["title"], "pdf"),
                caption=payload["title"],
                reply_markup=_remove_reply_keyboard(),
            )
        path.unlink(missing_ok=True)
        return

    path = temp_report_path(".xlsx")
    write_excel_report(payload, path)
    with path.open("rb") as document:
        _reply_document(
            message,
            context,
            document=document,
            filename=_safe_export_filename(payload["title"], "xlsx"),
            caption=payload["title"],
            reply_markup=_remove_reply_keyboard(),
        )
    path.unlink(missing_ok=True)


def _execute_master_compare_output(message, context):
    state = _bi_state(context)
    output = state.get("output")
    period = state.get("period") or relative_period("this_year")
    categories = state.get("master_categories") or []
    compare_mode = state.get("master_compare_mode")
    granularity = state.get("master_granularity") or "month"
    result = master_name_comparison(
        legacy_period(period),
        scope="category",
        granularity=granularity,
        limit=200 if output in {"pdf", "excel"} else 50,
        categories=categories,
        compare_mode=compare_mode,
    )
    payload = {
        "intent": {
            "business": "compare",
            "module": "category_master",
            "report": "master_name_comparison",
            "categories": categories,
            "compare_mode": compare_mode,
            "granularity": granularity,
            "output": output,
        },
        "title": "Compare - Category Comparison",
        "period_label": period_label(period),
        "result": result,
    }

    if output == "text":
        for part in _split_message(format_text_report(payload)):
            _reply_text(message, context, part, reply_markup=_remove_reply_keyboard())
        return

    if output == "pdf":
        path = temp_report_path(".pdf")
        _write_pdf_export(format_text_report(payload), path, title=payload["title"])
        with path.open("rb") as document:
            _reply_document(
                message,
                context,
                document=document,
                filename=_safe_export_filename(payload["title"], "pdf"),
                caption=payload["title"],
                reply_markup=_remove_reply_keyboard(),
            )
        path.unlink(missing_ok=True)
        return

    path = temp_report_path(".xlsx")
    write_excel_report(payload, path)
    with path.open("rb") as document:
        _reply_document(
            message,
            context,
            document=document,
            filename=_safe_export_filename(payload["title"], "xlsx"),
            caption=payload["title"],
            reply_markup=_remove_reply_keyboard(),
        )
    path.unlink(missing_ok=True)


def _executive_output_format(text):
    normalized = " ".join(str(text or "").lower().split())
    if "excel" in normalized or "xlsx" in normalized:
        return "excel"
    if "pdf" in normalized:
        return "pdf"
    return "text"


def _send_executive_answer(message, context, question):
    answer = answer_executive_question(question)
    output = _executive_output_format(question)
    if output == "pdf":
        path = temp_report_path(".pdf")
        try:
            created = create_ceo_management_pdf_report(
                question,
                path,
                title=CEO_PDF_EXPORT_TITLE,
            )
        except Exception:
            created = False
        if not created:
            _write_pdf_export(answer, path, title="BigShot Business Intelligence Report")
        with path.open("rb") as document:
            _reply_document(
                message,
                context,
                document=document,
                filename=_safe_export_filename("BigShot Business Intelligence Report", "pdf"),
                caption="BigShot Business Intelligence Report",
                reply_markup=_remove_reply_keyboard(),
            )
        path.unlink(missing_ok=True)
        return
    if output == "excel":
        path = temp_report_path(".xlsx")
        write_executive_excel_report(answer, path)
        with path.open("rb") as document:
            _reply_document(
                message,
                context,
                document=document,
                filename=_safe_export_filename("BigShot Business Intelligence Report", "xlsx"),
                caption="BigShot Business Intelligence Report",
                reply_markup=_remove_reply_keyboard(),
            )
        path.unlink(missing_ok=True)
        return
    for part in _split_message(answer):
        _reply_text(message, context, part, reply_markup=_remove_reply_keyboard())


def handle_bi_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    message = query.message
    if not _is_allowed_message(message):
        query.answer()
        return

    data = query.data or ""
    query.answer()
    state = _bi_state(context)

    if data == "bi:home":
        _show_bi_home(message, context)
        return
    if data == "bi:overall_kpi":
        _send_export(message, f"{PDF_EXPORT_COMMAND}:this year KPI pdf", context=context)
        return
    if data == "bi:cancel":
        _reset_bi_state(context)
        _reply_text(message, context, "Business Intelligence cancelled.", reply_markup=_remove_reply_keyboard())
        return
    if data == "bi:back":
        step = state.get("step")
        if step == "comparison_output":
            _reset_bi_state(context)
            _reply_text(message, context, "Comparison cancelled.", reply_markup=_remove_reply_keyboard())
            return
        if step == "master_output":
            state.pop("period", None)
            state["step"] = "period"
            _show_period_menu(message, context)
            return
        if step == "master_period":
            state.pop("master_granularity", None)
            _show_master_granularity_menu(message, context)
            return
        if step == "master_granularity":
            state["awaiting"] = "master_category"
            _reply_text(
                message,
                context,
                "Type category name to search.",
                reply_markup=_remove_reply_keyboard(),
            )
            return
        if step == "master_select_category":
            _show_prompt_enquiry_menu(message, context)
            return
        if step == "output":
            state.pop("period", None)
            state["step"] = "period"
            _show_period_menu(message, context)
        elif step == "period":
            state.pop("report", None)
            state["step"] = "report"
            _show_report_menu(message, context)
        elif step == "report":
            state.pop("module", None)
            state["step"] = "module"
            _show_module_menu(message, context)
        else:
            _show_bi_home(message, context)
        return

    if data.startswith("bi:business:"):
        state.clear()
        state["business"] = data.rsplit(":", 1)[1]
        state["step"] = "module"
        _show_module_menu(message, context)
        return
    if data == "bi:prompt_enquiry":
        _show_prompt_enquiry_menu(message, context)
        return
    if data.startswith("bi:master_mode:"):
        state.clear()
        state["master_compare_mode"] = data.rsplit(":", 1)[1]
        state["master_categories"] = []
        state["awaiting"] = "master_category"
        state["step"] = "master_select_category"
        _reply_text(
            message,
            context,
            "Type category name to search.",
            reply_markup=_remove_reply_keyboard(),
        )
        return
    if data.startswith("bi:module:"):
        state["module"] = data.rsplit(":", 1)[1]
        state["step"] = "report"
        _show_report_menu(message, context)
        return
    if data.startswith("bi:report:"):
        state["report"] = data.rsplit(":", 1)[1]
        state["step"] = "period"
        _after_report_selected(message, context)
        return
    if data.startswith("bi:select_customer:"):
        index = int(data.rsplit(":", 1)[1])
        state["customer"] = state.get("candidates", [])[index]
        state.pop("awaiting", None)
        state["step"] = "period"
        _show_period_menu(message, context)
        return
    if data.startswith("bi:select_master_category:"):
        index = int(data.rsplit(":", 1)[1])
        category = state.get("candidates", [])[index]
        selected = state.setdefault("master_categories", [])
        if category not in selected:
            selected.append(category)
        state.pop("candidates", None)
        if state.get("master_compare_mode") == "same":
            state.pop("awaiting", None)
            _show_master_granularity_menu(message, context)
            return
        rows = [[InlineKeyboardButton("Done", callback_data="bi:master_category_done")]]
        selected_text = "\n".join(f"- {value}" for value in selected)
        _send_bi_message(
            message,
            context,
            f"Selected categories:\n{selected_text}\n\nType another category to search, or press Done.",
            rows,
        )
        return
    if data == "bi:master_category_done":
        if not state.get("master_categories"):
            _reply_text(message, context, "Select at least one category first.", reply_markup=_remove_reply_keyboard())
            return
        state.pop("awaiting", None)
        state.pop("candidates", None)
        _show_master_granularity_menu(message, context)
        return
    if data.startswith("bi:master_granularity:"):
        state["master_granularity"] = data.rsplit(":", 1)[1]
        state["step"] = "master_period"
        _show_period_menu(message, context)
        return
    if data.startswith("bi:select_category:"):
        index = int(data.rsplit(":", 1)[1])
        category = state.get("candidates", [])[index]
        selected = state.setdefault("categories", [])
        if category not in selected:
            selected.append(category)
        state["category"] = category if len(selected) == 1 else ""
        rows = [[InlineKeyboardButton("Done", callback_data="bi:category_done")]]
        selected_text = "\n".join(f"- {value}" for value in selected)
        _send_bi_message(
            message,
            context,
            f"Selected categories:\n{selected_text}\n\nType another category to search, or press Done.",
            rows,
        )
        return
    if data == "bi:category_done":
        if not state.get("categories") and state.get("category"):
            state["categories"] = [state["category"]]
        state.pop("awaiting", None)
        state.pop("candidates", None)
        state["step"] = "period"
        _show_period_menu(message, context)
        return
    if data.startswith("bi:period:"):
        state["period"] = relative_period(data.rsplit(":", 1)[1])
        state["step"] = "master_output" if state.get("master_compare_mode") else "output"
        _show_output_menu(message, context)
        return
    if data.startswith("bi:custom:"):
        _start_custom_calendar(message, context, data.rsplit(":", 1)[1])
        return
    if data.startswith("bi:cal:years:"):
        _show_calendar_years(message, context, int(data.rsplit(":", 1)[1]))
        return
    if data.startswith("bi:cal:year:"):
        _show_calendar_months(message, context, int(data.rsplit(":", 1)[1]))
        return
    if data.startswith("bi:cal:month:"):
        _, _, _, year, month = data.split(":")
        kind = state.get("calendar_kind")
        if kind == "month":
            state["period"] = month_period(year, month)
            state["step"] = "master_output" if state.get("master_compare_mode") else "output"
            _show_output_menu(message, context)
        else:
            _show_calendar_dates(message, context, int(year), int(month))
        return
    if data.startswith("bi:cal:date:"):
        selected = data.rsplit(":", 1)[1]
        kind = state.get("calendar_kind")
        if kind == "range" and state.get("range_stage") == "start":
            state["range_start"] = selected
            state["range_stage"] = "end"
            _reply_text(message, context, f"Start date: {selected}")
            _show_calendar_years(message, context, int(selected[:4]))
        else:
            if kind == "range":
                state["period"] = range_period(state["range_start"], selected)
            else:
                state["period"] = date_period(selected)
            state["step"] = "master_output" if state.get("master_compare_mode") else "output"
            _show_output_menu(message, context)
        return
    if data.startswith("bi:output:"):
        state["output"] = data.rsplit(":", 1)[1]
        state["step"] = "done"
        try:
            if state.get("comparison_question"):
                _execute_comparison_output(message, context)
            elif state.get("master_compare_mode"):
                _execute_master_compare_output(message, context)
            else:
                _execute_bi_output(message, context)
        except Exception as exc:
            _reply_text(message, context, f"Report error: {exc}", reply_markup=_remove_reply_keyboard())
        return

    _reply_text(message, context, "Unknown Business Intelligence action.")


def whereami(update: Update, context: CallbackContext):
    message = update.message
    if not _is_allowed_message(message):
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


def menu(update: Update, context: CallbackContext):
    message = update.message
    if not _is_allowed_message(message):
        return

    _schedule_auto_delete(context, message)
    _reply_text(
        message,
        context,
        "Prompt keyboard removed.",
        reply_markup=_remove_reply_keyboard(),
    )
    _show_bi_home(message, context)


def prompts(update: Update, context: CallbackContext):
    message = update.message
    if not _is_allowed_message(message):
        return

    _schedule_auto_delete(context, message)
    _reply_text(
        message,
        context,
        "Prebuilt Prompt Enquiry",
        reply_markup=_finance_inline_markup(),
    )


def sync_obligations_calendar(update: Update, context: CallbackContext):
    message = update.message
    if not _is_allowed_message(message):
        return

    _schedule_auto_delete(context, message)
    try:
        _answer_finance_question(message, "__sync_obligation_calendar__", context=context)
    except Exception as e:
        _reply_text(
            message,
            context,
            f"Calendar sync error: {str(e)}",
            reply_markup=_remove_reply_keyboard(),
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
        _answer_finance_question(message, question, context=context)
    except Exception as e:
        _reply_text(
            message,
            context,
            f"Error: {str(e)}",
            reply_markup=_remove_reply_keyboard(),
        )


def handle_message(update: Update, context: CallbackContext):
    if not _is_allowed_message(update.message):
        return

    _schedule_auto_delete(context, update.message)
    user_text = update.message.text
    print(f"Finance text: {user_text}", flush=True)

    if _handle_search_text(update.message, context, user_text):
        return

    if is_expense_month_comparison(user_text):
        _show_comparison_output_menu(update.message, context, user_text)
        return

    question = _normalize_command(user_text)
    try:
        if _is_export_command(question) or str(user_text).strip().startswith("/"):
            _answer_finance_question(update.message, question, context=context)
            return
        _send_executive_answer(update.message, context, user_text)
    except Exception as e:
        _reply_text(
            update.message,
            context,
            f"Error: {str(e)}",
            reply_markup=_remove_reply_keyboard(),
        )


def main():
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required.")
    if not TELEGRAM_ALLOWED_CHAT_ID:
        raise RuntimeError("TELEGRAM_ALLOWED_CHAT_ID is required.")
    if not TELEGRAM_ALLOWED_THREAD_ID:
        raise RuntimeError("TELEGRAM_ALLOWED_THREAD_ID is required.")

    persistence = PicklePersistence(filename=BI_PERSISTENCE_FILE)
    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True, persistence=persistence)

    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("whereami", whereami))
    dispatcher.add_handler(CommandHandler("menu", menu))
    dispatcher.add_handler(CommandHandler("prompts", prompts))
    dispatcher.add_handler(CommandHandler("start", menu))
    dispatcher.add_handler(CommandHandler("sync_obligations_calendar", sync_obligations_calendar))
    dispatcher.add_handler(CallbackQueryHandler(handle_bi_callback, pattern=r"^bi:"))
    dispatcher.add_handler(CallbackQueryHandler(handle_prompt_button, pattern=r"^finance:"))

    dispatcher.add_handler(
        MessageHandler(Filters.text, handle_message)
    )

    print("Telegram AI Bot Running...")

    updater.start_polling()

    updater.idle()


if __name__ == "__main__":
    main()
