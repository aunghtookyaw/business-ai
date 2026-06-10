from dataclasses import asdict, dataclass, field


BUSINESSES = {
    "sote_phwar",
    "farm",
    "factory",
    "extension",
    "inventory",
    "customers",
    "financial_obligation",
}

OUTPUTS = {"text", "pdf", "excel"}


@dataclass
class BIIntent:
    business: str = ""
    module: str = ""
    report: str = ""
    period: dict = field(default_factory=dict)
    output: str = ""
    customer: str = ""
    category: str = ""
    categories: list = field(default_factory=list)
    product: str = ""
    store: str = ""

    def to_dict(self):
        data = asdict(self)
        return {
            key: value
            for key, value in data.items()
            if value not in ("", None, {}) and value != []
        }


def intent_from_state(state):
    return BIIntent(
        business=state.get("business", ""),
        module=state.get("module", ""),
        report=state.get("report", ""),
        period=state.get("period") or {},
        output=state.get("output", ""),
        customer=state.get("customer", ""),
        category=state.get("category", ""),
        categories=state.get("categories") or [],
        product=state.get("product", ""),
        store=state.get("store", ""),
    )


def validate_intent(intent):
    missing = []
    if intent.business not in BUSINESSES:
        missing.append("business")
    if not intent.module:
        missing.append("module")
    if not intent.report:
        missing.append("report")
    if not intent.period:
        missing.append("period")
    if intent.output not in OUTPUTS:
        missing.append("output")

    if intent.report in {
        "sales_by_customer",
        "customer_history",
        "customer_sales",
        "customer_profitability",
        "outstanding_balance",
    } and not intent.customer:
        missing.append("customer")
    if intent.report in {"expense_by_category", "expense_detail"} and not intent.category and not intent.categories:
        missing.append("category")

    return missing
