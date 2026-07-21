from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, timedelta
import json
import re
import threading
from time import monotonic
from typing import Optional

from tools import bi_search
from tools import formula_engine
from tools.ollama_client import ask_ai


DASHBOARD_CACHE_TTL_SECONDS = 30
INSIGHT_CACHE_TTL_SECONDS = 600
BUSINESS_UNIT_SECTORS = {
    "farm": "Farm",
    "sote_phwar": "Sote Phwar",
    "extension": "SP Extension",
    "factory": "SP Production",
}
VALID_PAYMENT_STATUSES = {"", "Paid", "Partial", "Outstanding"}
PAYMENTS_QUERY_CONTRACT = {
    "version": "payments-v1-2026-07-16",
    "read_only": True,
    "voucher_identity": ["sector", "voucher_number", "invoice_date", "customer"],
    "period_basis": {"receivables": "invoice_date", "receipts": "receive_date"},
    "sources": ["payment_receive_summary", "recent_payment_receipts"],
    "row_limit": 100,
    "voucher_order": ["outstanding_balance DESC", "invoice_date ASC NULLS LAST"],
    "receipt_order": ["receive_date DESC NULLS LAST", "id DESC"],
    "aging_semantics": "invoice_age_not_due_date",
}
_CACHE = {}
_CACHE_LOCK = threading.Lock()


@dataclass(frozen=True)
class DashboardFilters:
    period: dict
    sector: str = ""
    business_unit: str = ""
    customer: str = ""
    category: str = ""
    product: str = ""
    location: str = ""
    payment_status: str = ""

    def to_dict(self):
        return {
            "period": dict(self.period),
            "sector": self.sector,
            "business_unit": self.business_unit,
            "customer": self.customer,
            "category": self.category,
            "product": self.product,
            "location": self.location,
            "payment_status": self.payment_status,
        }


@dataclass(frozen=True)
class FarmProductionFilters:
    start_date: date
    end_date: date
    crop_ids: Optional[tuple[int, ...]] = None
    farm_area_ids: tuple[int, ...] = ()
    grouping: str = "daily"


def parse_farm_production_filters(payload):
    raw = (payload or {}).get("filters") or {}
    try:
        start = date.fromisoformat(str(raw.get("start_date") or ""))
        end = date.fromisoformat(str(raw.get("end_date") or ""))
    except ValueError as exc:
        raise ValueError("start_date and end_date must use YYYY-MM-DD") from exc
    if end < start:
        raise ValueError("end_date must not be before start_date")
    if (end - start).days > 730:
        raise ValueError("date range cannot exceed two years")
    grouping = str(raw.get("grouping") or "daily").lower()
    if grouping not in {"daily", "weekly", "monthly"}:
        raise ValueError("grouping must be daily, weekly, or monthly")
    try:
        crop_ids = (tuple(sorted({int(value) for value in (raw.get("crop_ids") or [])}))
                    if "crop_ids" in raw else None)
        farm_area_ids = tuple(sorted({int(value) for value in (raw.get("farm_area_ids") or [])}))
    except (TypeError, ValueError) as exc:
        raise ValueError("crop_ids and farm_area_ids must contain integer IDs") from exc
    return FarmProductionFilters(start, end, crop_ids, farm_area_ids, grouping)


def farm_production_dashboard(filters):
    dimensions = formula_engine.farm_production_dimensions()
    selected_crops = (tuple(crop["id"] for crop in dimensions["crops"][:5])
                      if filters.crop_ids is None else filters.crop_ids)
    trend = formula_engine.farm_production_analytics(
        filters.start_date, filters.end_date, selected_crops,
        filters.farm_area_ids, filters.grouping, dimensions["farm_areas"],
    )
    return {
        **trend,
        "available_crops": dimensions["crops"],
        "available_farm_areas": dimensions["farm_areas"],
        "selected_crop_ids": list(selected_crops),
        "selected_farm_area_ids": list(filters.farm_area_ids),
    }


def inventory_dashboard():
    return formula_engine.sotephwar_inventory_dashboard()


def payments_dashboard(filters):
    """Compose the read-only Payments page from canonical Formula Engine reports."""
    period = legacy_period(filters.period)
    sector = _formula_filters(filters).get("sector")
    with ThreadPoolExecutor(max_workers=2) as executor:
        summary_future = executor.submit(
            formula_engine.payment_receive_summary,
            period,
            sector=sector,
            customer=filters.customer or None,
            payment_status=filters.payment_status or None,
            limit=PAYMENTS_QUERY_CONTRACT["row_limit"],
        )
        history_future = executor.submit(
            formula_engine.recent_payment_receipts,
            period,
            sector=sector,
            customer=filters.customer or None,
            payment_status=filters.payment_status or None,
            limit=PAYMENTS_QUERY_CONTRACT["row_limit"],
        )
        summary = summary_future.result()
        history = history_future.result()

    invoices = summary.get("invoices", [])
    status_counts = {"Paid": 0, "Partial": 0, "Outstanding": 0}
    for invoice in invoices:
        outstanding = int(invoice.get("outstanding_balance") or 0)
        received = int(invoice.get("received_amount") or 0)
        status = "Paid" if outstanding <= 0 else "Partial" if received > 0 else "Outstanding"
        invoice["payment_status"] = status
        status_counts[status] += 1
    return {
        "filters": filters.to_dict(),
        "filter_label": filter_label(filters),
        "metrics": {
            "invoiced": summary.get("total_invoice_amount", 0),
            "received": summary.get("total_received", 0),
            "outstanding": summary.get("outstanding_receivables", 0),
            "collection_rate_percent": summary.get("collection_rate_percent", 0),
            "voucher_count": len(invoices),
        },
        "aging": summary.get("aging", {}),
        "status_counts": status_counts,
        "sector_totals": summary.get("sector_totals", []),
        "customer_balances": summary.get("customer_balances", []),
        "invoices": invoices,
        "recent_payments": history.get("payments", []),
        "data_quality": [{
            "metric": "aging",
            "status": "limited",
            "message": "Aging is based on invoice age because an approved due-date model is not yet available.",
        }],
        "sources": ["payment_receive_summary", "recent_payment_receipts"],
        "contract": PAYMENTS_QUERY_CONTRACT,
    }


def parse_dashboard_filters(payload):
    raw = (payload or {}).get("filters") or {}
    period = _validate_period(raw.get("period") or {"type": "year", "year": date.today().year})
    sector = str(raw.get("sector") or "").strip()
    business_unit = str(raw.get("business_unit") or "").strip().lower()
    business_sector = BUSINESS_UNIT_SECTORS.get(business_unit)
    if sector and business_sector and sector != business_sector:
        raise ValueError("sector and business_unit filters conflict")
    payment_status = str(raw.get("payment_status") or "").strip()
    if payment_status not in VALID_PAYMENT_STATUSES:
        raise ValueError("payment_status must be Paid, Partial, Outstanding, or empty")
    return DashboardFilters(
        period=period,
        sector=sector,
        business_unit=business_unit,
        customer=str(raw.get("customer") or "").strip(),
        category=str(raw.get("category") or "").strip(),
        product=str(raw.get("product") or "").strip(),
        location=str(raw.get("location") or "").strip(),
        payment_status=payment_status,
    )


def _validate_period(period):
    kind = str(period.get("type") or "").strip().lower()
    if kind == "year":
        year = int(period.get("year") or date.today().year)
        if not 2000 <= year <= 2100:
            raise ValueError("year is outside the supported range")
        return {"type": "year", "year": year}
    if kind == "month":
        year = int(period.get("year") or date.today().year)
        month = int(period.get("month") or date.today().month)
        if not 2000 <= year <= 2100 or not 1 <= month <= 12:
            raise ValueError("invalid month period")
        return {"type": "month", "year": year, "month": month}
    if kind == "quarter":
        year = int(period.get("year") or date.today().year)
        quarter = int(period.get("quarter") or (((date.today().month - 1) // 3) + 1))
        if not 2000 <= year <= 2100 or not 1 <= quarter <= 4:
            raise ValueError("invalid quarter period")
        return {"type": "quarter", "year": year, "quarter": quarter}
    if kind == "date":
        try:
            value = date.fromisoformat(str(period.get("date") or ""))
        except ValueError:
            raise ValueError("date must use YYYY-MM-DD")
        return {"type": "date", "date": value.isoformat()}
    if kind == "relative":
        value = str(period.get("value") or "").strip()
        if value not in {
            "today",
            "yesterday",
            "this_week",
            "last_week",
            "this_month",
            "last_month",
            "this_quarter",
            "last_quarter",
            "this_year",
            "last_year",
        }:
            raise ValueError("unsupported relative period")
        return {"type": "relative", "value": value}
    if kind == "week":
        value = str(period.get("value") or "").strip()
        try:
            year_text, week_text = value.upper().split("-W", 1)
            monday = date.fromisocalendar(int(year_text), int(week_text), 1)
        except (TypeError, ValueError):
            raise ValueError("week must use YYYY-Www format")
        return {"type": "week", "value": value.upper(), "start": monday.isoformat()}
    if kind == "range":
        try:
            start = date.fromisoformat(str(period.get("start") or ""))
            end = date.fromisoformat(str(period.get("end") or ""))
        except ValueError:
            raise ValueError("date range must use YYYY-MM-DD")
        if end < start:
            raise ValueError("date range end must not be before start")
        if (end - start).days > 730:
            raise ValueError("date range cannot exceed two years")
        return {"type": "range", "start": start.isoformat(), "end": end.isoformat()}
    raise ValueError("period type must be year, quarter, month, week, date, relative, or range")


def legacy_period(period):
    kind = period["type"]
    if kind == "year":
        return f"year:{period['year']}"
    if kind == "month":
        return f"month:{period['year']}-{period['month']:02d}"
    if kind == "quarter":
        return f"quarter:{period['year']}-Q{period['quarter']}"
    if kind == "date":
        return f"date:{period['date']}"
    if kind == "relative":
        return period["value"]
    if kind == "week":
        start = date.fromisoformat(period["start"])
        end = start + timedelta(days=6)
        return f"range:{start.isoformat()}:{end.isoformat()}"
    return f"range:{period['start']}:{period['end']}"


def filter_label(filters):
    period = filters.period
    if period["type"] == "year":
        label = str(period["year"])
    elif period["type"] == "month":
        label = date(period["year"], period["month"], 1).strftime("%B %Y")
    elif period["type"] == "quarter":
        label = f"Q{period['quarter']} {period['year']}"
    elif period["type"] == "date":
        label = period["date"]
    elif period["type"] == "relative":
        label = period["value"].replace("_", " ").title()
    elif period["type"] == "week":
        label = period["value"]
    else:
        label = f"{period['start']} to {period['end']}"
    scope = filters.sector or BUSINESS_UNIT_SECTORS.get(filters.business_unit) or "All sectors"
    return f"{label} · {scope}"


def _formula_filters(filters):
    values = {}
    sector = filters.sector or BUSINESS_UNIT_SECTORS.get(filters.business_unit)
    if sector:
        values["sector"] = sector
    if filters.category:
        values["category"] = filters.category
    if filters.customer:
        values["customer"] = filters.customer
    return values


def _cache_key(namespace, filters):
    return namespace + ":" + json.dumps(filters.to_dict(), sort_keys=True, separators=(",", ":"))


def _cached(namespace, filters, ttl, loader):
    key = _cache_key(namespace, filters)
    now = monotonic()
    with _CACHE_LOCK:
        item = _CACHE.get(key)
        if item and item["expires_at"] > now:
            return item["value"], True
    value = loader()
    with _CACHE_LOCK:
        _CACHE[key] = {"expires_at": now + ttl, "value": value}
    return value, False


def clear_dashboard_cache():
    with _CACHE_LOCK:
        _CACHE.clear()


def dashboard_dimensions():
    engine = formula_engine.dashboard_dimension_values()
    return {
        "years": list(range(date.today().year, 2019, -1)),
        "sectors": engine["sectors"],
        "business_units": [
            {"value": "sote_phwar", "label": "Sote Phwar"},
            {"value": "farm", "label": "Farm"},
            {"value": "extension", "label": "Extension"},
            {"value": "factory", "label": "Factory"},
        ],
        "customers": bi_search.customer_values(),
        "categories": bi_search.category_values(),
        "products": engine["products"],
        "locations": engine["locations"],
        "payment_statuses": ["Paid", "Partial", "Outstanding"],
    }


def _trend_periods(period):
    if period["type"] == "year":
        return [
            (date(period["year"], month, 1).strftime("%b"), f"month:{period['year']}-{month:02d}")
            for month in range(1, 13)
        ]
    if period["type"] == "month":
        start = date(period["year"], period["month"], 1)
        if start.month == 12:
            end = date(start.year + 1, 1, 1)
        else:
            end = date(start.year, start.month + 1, 1)
        rows = []
        current = start
        week = 1
        while current < end:
            bucket_end = min(current + timedelta(days=6), end - timedelta(days=1))
            rows.append((f"W{week}", f"range:{current.isoformat()}:{bucket_end.isoformat()}"))
            current = bucket_end + timedelta(days=1)
            week += 1
        return rows
    if period["type"] == "quarter":
        start_month = ((period["quarter"] - 1) * 3) + 1
        return [
            (
                date(period["year"], month, 1).strftime("%b"),
                f"month:{period['year']}-{month:02d}",
            )
            for month in range(start_month, start_month + 3)
        ]
    if period["type"] == "date":
        return [(period["date"], f"date:{period['date']}")]
    if period["type"] == "relative":
        return [(period["value"].replace("_", " ").title(), period["value"])]
    if period["type"] == "week":
        start = date.fromisoformat(period["start"])
        return [
            ((start + timedelta(days=offset)).strftime("%a"), f"date:{(start + timedelta(days=offset)).isoformat()}")
            for offset in range(7)
        ]
    start = date.fromisoformat(period["start"])
    end = date.fromisoformat(period["end"])
    days = (end - start).days + 1
    step = max(1, (days + 11) // 12)
    rows = []
    current = start
    while current <= end:
        bucket_end = min(current + timedelta(days=step - 1), end)
        rows.append((
            current.strftime("%d %b"),
            f"range:{current.isoformat()}:{bucket_end.isoformat()}",
        ))
        current = bucket_end + timedelta(days=1)
    return rows


def _trend_row(label, period, filters):
    kpi = formula_engine.kpi_overview(period, filters)
    cash = formula_engine.cash_flow(period, filters)
    sales = formula_engine.sales_total(period, filters)
    customer_scope = bool((filters or {}).get("customer"))
    return {
        "label": label,
        "period": period,
        "revenue": kpi["total_income"],
        "expense": None if customer_scope else kpi["total_expense"],
        "profit": None if customer_scope else kpi["net_profit"],
        "cash_flow": cash["net_cash_flow"],
        "outstanding": sales["outstanding_amount"],
    }


def executive_dashboard(filters):
    return _cached(
        "executive",
        filters,
        DASHBOARD_CACHE_TTL_SECONDS,
        lambda: _build_executive_dashboard(filters),
    )


def _build_executive_dashboard(filters):
    period = legacy_period(filters.period)
    engine_filters = _formula_filters(filters)
    sector = engine_filters.get("sector")
    product_allowed = not sector or sector == "Sote Phwar"
    warnings = []
    if filters.product and not product_allowed:
        warnings.append("Product filter applies only to Sote Phwar product and inventory widgets.")
    if filters.location:
        warnings.append("Location filter applies only to inventory widgets.")
    if filters.payment_status:
        warnings.append("Payment status filter applies only to payment widgets.")
    if filters.category:
        warnings.append("Category filters exclude Farm and Sote Phwar sales where category is not a canonical sales dimension.")
    if filters.customer:
        warnings.append("Customer expense, net profit, and profit margin are unavailable because expenses are not attributed to customers.")

    jobs = {
        "kpi": lambda: formula_engine.kpi_overview(period, engine_filters),
        "sales": lambda: formula_engine.sales_total(period, engine_filters),
        "cash": lambda: formula_engine.cash_flow(period, engine_filters),
        "receivables": lambda: formula_engine.payment_receive_summary(
            period,
            sector=sector,
            customer=filters.customer or None,
            payment_status=filters.payment_status or None,
            limit=10,
        ),
        "inventory": lambda: formula_engine.calculate_inventory_value(
            product=filters.product or None,
            store=filters.location or None,
        ) if product_allowed else {
            "formula": "sotephwar_inventory_value",
            "total_inventory_value": 0,
            "stock": [],
            "products": [],
            "locations": [],
        },
        "top_customers": lambda: formula_engine.top_income(period, engine_filters, limit=10),
        "top_products": lambda: formula_engine.sotephwar_product_ranking(
            period,
            product=filters.product or None,
            limit=10,
        ) if product_allowed else {"formula": "sotephwar_product_ranking", "products": []},
        "top_expense_categories": lambda: formula_engine.top_expense_categories(
            period,
            engine_filters,
            limit=10,
        ),
        "recent_payments": lambda: formula_engine.recent_payment_receipts(
            period,
            sector=sector,
            customer=filters.customer or None,
            payment_status=filters.payment_status or None,
            limit=10,
        ),
        "recent_transactions": lambda: formula_engine.list_transactions(
            period,
            engine_filters,
            limit=10,
        ),
    }
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {name: executor.submit(loader) for name, loader in jobs.items()}
        results = {name: future.result() for name, future in futures.items()}

    trend_buckets = _trend_periods(filters.period)
    with ThreadPoolExecutor(max_workers=min(12, len(trend_buckets) or 1)) as executor:
        trend = list(executor.map(
            lambda item: _trend_row(item[0], item[1], engine_filters),
            trend_buckets,
        ))

    kpi = results["kpi"]
    sales = results["sales"]
    cash = results["cash"]
    receivables = results["receivables"]
    return {
        "filters": filters.to_dict(),
        "filter_label": filter_label(filters),
        "metrics": {
            "revenue": kpi["total_income"],
            "expenses": None if filters.customer else kpi["total_expense"],
            "net_profit": None if filters.customer else kpi["net_profit"],
            "cash_received": cash["total_inflow"],
            "outstanding_receivables": receivables["outstanding_receivables"],
            "inventory_value": results["inventory"].get("total_inventory_value", 0),
            "profit_margin_percent": None if filters.customer else kpi["profit_margin_percent"],
            "collection_rate_percent": receivables["collection_rate_percent"],
            "sales_received": sales["amount_received"],
        },
        "trend": trend,
        "cash_flow": cash,
        "receivables": receivables,
        "inventory": results["inventory"],
        "top_customers": results["top_customers"]["income"],
        "top_products": results["top_products"]["products"],
        "top_expense_categories": results["top_expense_categories"]["categories"],
        "recent_payments": results["recent_payments"]["payments"],
        "recent_transactions": results["recent_transactions"]["transactions"],
        "data_quality": [
            *({"metric": "filters", "status": "limited", "message": message} for message in warnings),
        ],
        "sources": {
            "metrics": ["kpi_overview", "sales_total", "cash_flow", "payment_receive_summary", "sotephwar_inventory_value"],
            "trend": ["kpi_overview", "cash_flow", "sales_total"],
            "tables": [
                "top_income",
                "sotephwar_product_ranking",
                "top_expense_categories",
                "recent_payment_receipts",
                "list_transactions",
            ],
        },
    }


def executive_insight(filters):
    return _cached(
        "insight",
        filters,
        INSIGHT_CACHE_TTL_SECONDS,
        lambda: _build_executive_insight(filters),
    )


def _build_executive_insight(filters):
    dashboard, _ = executive_dashboard(filters)
    evidence = {
        "filter_label": dashboard["filter_label"],
        "metrics": dashboard["metrics"],
        "cash_flow": {
            "total_inflow": dashboard["cash_flow"]["total_inflow"],
            "total_outflow": dashboard["cash_flow"]["total_outflow"],
            "net_cash_flow": dashboard["cash_flow"]["net_cash_flow"],
        },
        "top_customers": dashboard["top_customers"][:5],
        "top_expense_categories": dashboard["top_expense_categories"][:5],
        "data_quality": dashboard["data_quality"],
    }
    prompt = f"""
You are Qwen acting as BigShot's executive narrative assistant.

The JSON below contains figures already calculated by the canonical Business Intelligence engine.
Do not calculate, recompute, estimate, derive, rank, or invent any number.
Do not display any number, amount, percentage, date, currency name, or currency symbol.
Refer to business direction qualitatively, for example strong, weak, rising, concentrated, or unavailable.
All numeric presentation is handled by deterministic dashboard widgets outside Qwen.

Return exactly these headings:
Executive Summary
Business Risks
Opportunities
Recommendations
Management Conclusion

Write concise CEO/CFO language. Under each heading provide exactly one bullet point
with no more than twenty words.
If data quality marks a metric unavailable, state the limitation without estimating it.

Validated BI evidence:
{json.dumps(evidence, default=str, ensure_ascii=False)}
"""
    text = ask_ai(prompt, timeout=90).strip()
    if not text:
        raise RuntimeError("Qwen returned an empty executive narrative.")
    if re.search(r"\d|[$€£¥]", text) or re.search(
        r"\b(?:mmk|kyat|kyats|dollar|dollars|percent|percentage)\b",
        text,
        flags=re.IGNORECASE,
    ):
        raise RuntimeError("Qwen narrative included prohibited numeric or currency content.")
    return {"narrative": text, "source": "qwen", "calculation_source": "canonical_bi_engine"}
