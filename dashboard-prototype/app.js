const pageConfig = {
  executive: {
    title: "Executive Dashboard",
    subtitle: "A thirty-second view of performance, cash and operational risk."
  },
  payments: {
    title: "Payment Analytics",
    subtitle: "Milestone 2 — collections, aging and payment history.",
    eyebrow: "RECEIVABLES & COLLECTIONS",
    headline: "Payment Analytics is scheduled for Milestone 2.",
    description: "The navigation and global filter contract are ready. Page-specific implementation begins after Milestone 1 acceptance.",
    kpis: ["Outstanding Receivables", "Collection Rate", "Received This Period", "Overdue Customers"],
    primary: "Collection and outstanding trend",
    breakdown: "Payment status distribution",
    table: "Customer aging and payment history"
  },
  inventory: {
    title: "Inventory Dashboard",
    subtitle: "Milestone 2 — stock position and movement by location.",
    eyebrow: "STOCK & OPERATIONS",
    headline: "Inventory Dashboard is scheduled for Milestone 2.",
    description: "Version 1 will show validated quantities. Inventory value remains unavailable until unit-cost data exists in the BI engine.",
    kpis: ["Stock Units", "Active Locations", "Production Volume", "Near Stock Out"],
    primary: "Stock movement timeline",
    breakdown: "Stock by product",
    table: "Inventory by location"
  },
  customers: {
    title: "Customer Dashboard",
    subtitle: "Milestone 3 — customer revenue and collection behaviour.",
    eyebrow: "CUSTOMER INTELLIGENCE",
    headline: "Customer Dashboard is scheduled for Milestone 3.",
    description: "Customer ranking and payment behaviour will use canonical sales and receivable reports.",
    kpis: ["Active Customers", "Top Customer Revenue", "Outstanding Customers", "Average Collection"],
    primary: "Revenue by customer trend",
    breakdown: "Customer payment behaviour",
    table: "Revenue and outstanding ranking"
  },
  farm: {
    title: "Farm Dashboard",
    subtitle: "Milestone 3 — Farm financial and operating performance.",
    eyebrow: "FARM MANAGEMENT",
    headline: "Farm Dashboard is scheduled for Milestone 3.",
    description: "Financial metrics will use canonical Farm BI filters.",
    kpis: ["Farm Revenue", "Farm Expenses", "Farm Profit", "Farm Cash Flow"],
    primary: "Farm revenue and expense trend",
    breakdown: "Expense mix",
    table: "Farm customer and crop performance"
  },
  "sote-phwar": {
    title: "Sote Phwar Dashboard",
    subtitle: "Milestone 3 — sales, production, inventory and dealers.",
    eyebrow: "SOTE PHWAR MANAGEMENT",
    headline: "Sote Phwar Dashboard is scheduled for Milestone 3.",
    description: "Sales will use Sotephwar_Transection and inventory will use the canonical movement ledger.",
    kpis: ["Sote Phwar Revenue", "Net Profit", "Production Units", "Outstanding"],
    primary: "Sales, production and collection trend",
    breakdown: "Product sales mix",
    table: "Dealer performance"
  },
  financial: {
    title: "Financial Dashboard",
    subtitle: "Milestone 4 — profit and loss, cash flow and comparisons.",
    eyebrow: "FINANCIAL CONTROL",
    headline: "Financial Dashboard is scheduled for Milestone 4.",
    description: "Balance sheet remains future-ready. Only validated BI outputs will be displayed.",
    kpis: ["Revenue", "Expenses", "Net Profit", "Net Cash Flow"],
    primary: "Monthly and yearly comparison",
    breakdown: "Revenue and expense breakdown",
    table: "Profit and loss detail"
  },
  insights: {
    title: "AI Insights",
    subtitle: "Milestone 4 — full Qwen management narrative.",
    eyebrow: "QWEN MANAGEMENT NARRATIVE",
    headline: "AI Insights is scheduled for Milestone 4.",
    description: "Milestone 1 includes the Executive summary panel. Qwen receives calculated BI outputs only.",
    kpis: ["Risk Signals", "Opportunities", "Recommended Actions", "CEO Priorities"],
    primary: "Trend interpretation",
    breakdown: "Risk severity",
    table: "Management action register"
  }
};

const content = document.getElementById("dashboardContent");
const executiveTemplate = document.getElementById("executiveTemplate");
const moduleTemplate = document.getElementById("moduleTemplate");
const pageTitle = document.getElementById("pageTitle");
const pageSubtitle = document.getElementById("pageSubtitle");
const sidebar = document.getElementById("sidebar");
const toast = document.getElementById("toast");
const expandedFilters = document.getElementById("expandedFilters");
const currentYear = new Date().getFullYear();
let activePage = "executive";
let periodType = "year";
let refreshTimer;

const filterElements = {
  year: document.getElementById("yearFilter"),
  month: document.getElementById("monthFilter"),
  week: document.getElementById("weekFilter"),
  rangeStart: document.getElementById("rangeStart"),
  rangeEnd: document.getElementById("rangeEnd"),
  sector: document.getElementById("sectorFilter"),
  businessUnit: document.getElementById("businessUnitFilter"),
  customer: document.getElementById("customerFilter"),
  category: document.getElementById("categoryFilter"),
  location: document.getElementById("locationFilter"),
  product: document.getElementById("productFilter"),
  paymentStatus: document.getElementById("paymentStatusFilter")
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatAmount(value) {
  if (value === null || value === undefined) return "—";
  const number = Number(value);
  const absolute = Math.abs(number);
  if (absolute >= 1_000_000_000) return `${(number / 1_000_000_000).toFixed(2)}B`;
  if (absolute >= 1_000_000) return `${(number / 1_000_000).toFixed(1)}M`;
  if (absolute >= 1_000) return `${(number / 1_000).toFixed(1)}K`;
  return number.toLocaleString();
}

function formatFull(value) {
  return Number(value || 0).toLocaleString();
}

function formatDate(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function initials(value) {
  return String(value || "—").split(/\s+/).slice(0, 2).map(word => word[0] || "").join("").toUpperCase();
}

function metricCard(label, index) {
  const values = ["Future milestone", "BI contract", "Read only", "Global filters"];
  return `
    <article class="metric-card">
      <div class="metric-label"><span>${escapeHtml(label)}</span><span class="metric-icon">${index + 1}</span></div>
      <strong>${values[index]}</strong>
      <p class="neutral">Implementation <span>not active in Milestone 1</span></p>
    </article>`;
}

function renderPage(page) {
  const config = pageConfig[page] || pageConfig.executive;
  activePage = page;
  pageTitle.textContent = config.title;
  pageSubtitle.textContent = config.subtitle;
  content.innerHTML = "";

  if (page === "executive") {
    content.appendChild(executiveTemplate.content.cloneNode(true));
    loadExecutiveDashboard();
  } else {
    const fragment = moduleTemplate.content.cloneNode(true);
    fragment.querySelector("#moduleEyebrow").textContent = config.eyebrow;
    fragment.querySelector("#moduleHeadline").textContent = config.headline;
    fragment.querySelector("#moduleDescription").textContent = config.description;
    fragment.querySelector("#moduleKpis").innerHTML = config.kpis.map(metricCard).join("");
    fragment.querySelector("#primaryChartTitle").textContent = config.primary;
    fragment.querySelector("#breakdownTitle").textContent = config.breakdown;
    fragment.querySelector("#tableTitle").textContent = config.table;
    content.appendChild(fragment);
  }

  document.querySelectorAll(".nav-item").forEach(item => {
    item.classList.toggle("active", item.dataset.page === page);
  });
  sidebar.classList.remove("open");
  history.replaceState(null, "", `#${page}`);
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove("show"), 3000);
}

function periodPayload() {
  if (periodType === "year") {
    return { type: "year", year: Number(filterElements.year.value || currentYear) };
  }
  if (periodType === "month") {
    const [year, month] = (filterElements.month.value || `${currentYear}-${String(new Date().getMonth() + 1).padStart(2, "0")}`).split("-");
    return { type: "month", year: Number(year), month: Number(month) };
  }
  if (periodType === "week") {
    return { type: "week", value: filterElements.week.value };
  }
  return { type: "range", start: filterElements.rangeStart.value, end: filterElements.rangeEnd.value };
}

function filterPayload(refresh = false) {
  return {
    refresh,
    filters: {
      period: periodPayload(),
      sector: filterElements.sector.value,
      business_unit: filterElements.businessUnit.value,
      customer: filterElements.customer.value,
      category: filterElements.category.value,
      product: filterElements.product.value,
      location: filterElements.location.value,
      payment_status: filterElements.paymentStatus.value
    }
  };
}

async function apiJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json();
  if (!response.ok || !payload.ok) throw new Error(payload.error || `Request failed: ${response.status}`);
  return payload;
}

async function loadDimensions() {
  const payload = await apiJson("/api/dashboard/dimensions");
  const data = payload.data;
  setOptions(filterElements.year, data.years.map(value => ({ value, label: value })), String(currentYear), false);
  setOptions(filterElements.sector, data.sectors.map(value => ({ value, label: value })));
  setOptions(filterElements.businessUnit, data.business_units);
  setOptions(filterElements.customer, data.customers.map(value => ({ value, label: value })));
  setOptions(filterElements.category, data.categories.map(value => ({ value, label: value })));
  setOptions(filterElements.product, data.products.map(value => ({ value, label: value })));
  setOptions(filterElements.location, data.locations.map(value => ({ value, label: value })));
  setOptions(filterElements.paymentStatus, data.payment_statuses.map(value => ({ value, label: value })));
}

function setOptions(select, options, selected = "", includeCurrent = true) {
  const first = includeCurrent ? select.options[0]?.outerHTML || '<option value="">All</option>' : "";
  select.innerHTML = first + options.map(option =>
    `<option value="${escapeHtml(option.value)}">${escapeHtml(option.label)}</option>`
  ).join("");
  select.value = selected;
}

function setLoading(loading) {
  content.classList.toggle("loading-state", loading);
  document.getElementById("refreshDashboard").disabled = loading;
}

async function loadExecutiveDashboard(refresh = false) {
  if (activePage !== "executive") return;
  setLoading(true);
  removeDashboardError();
  try {
    const payload = await apiJson("/api/dashboard/executive", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(filterPayload(refresh))
    });
    renderExecutiveData(payload.data);
    if (new URLSearchParams(location.search).get("noai") === "1") {
      const lead = document.getElementById("insightLead");
      if (lead) lead.querySelector("p").textContent = "Qwen narrative loads separately from calculated dashboard figures.";
    } else {
      loadExecutiveInsight();
    }
    if (payload.cached) showToast("Dashboard loaded from the 30-second read-only cache.");
  } catch (error) {
    showDashboardError(error.message);
  } finally {
    setLoading(false);
  }
}

function renderExecutiveData(data) {
  const metrics = data.metrics;
  setText("metricRevenue", formatAmount(metrics.revenue));
  setText("metricExpenses", formatAmount(metrics.expenses));
  setText("metricProfit", formatAmount(metrics.net_profit));
  setText("metricCash", formatAmount(metrics.cash_received));
  setText("metricOutstanding", formatAmount(metrics.outstanding_receivables));
  setText("metricInventoryValue", metrics.inventory_value === null ? "Unavailable" : formatAmount(metrics.inventory_value));
  setText("metricMargin", metrics.profit_margin_percent === null ? "Unavailable for customer scope" : `${metrics.profit_margin_percent}% profit margin`);
  setText("metricPeriodLabel", data.filter_label);
  setText("expenseTotalPanel", formatAmount(metrics.expenses));

  renderFinancialTrend(data.trend);
  renderCash(data.cash_flow, data.trend);
  renderCollections(data.receivables, data.trend);
  renderInventory(data.inventory.stock || []);
  renderTopCustomers(data.top_customers || []);
  renderRankList("expenseCategories", data.top_expense_categories || [], row => row.category, row => `${row.transaction_count} transactions`, row => formatAmount(row.amount));
  renderRankList("topProducts", data.top_products || [], row => row.product, row => `${formatFull(row.quantity)} units`, row => formatAmount(row.total_amount));
  renderPayments(data.recent_payments || []);
  renderTransactions(data.recent_transactions || []);
}

function setText(id, value) {
  const element = document.getElementById(id);
  if (element) element.textContent = value;
}

function linePath(values, width = 820, height = 240, padding = 10, scaleMinimum, scaleMaximum) {
  if (!values.length) return "";
  const maximum = scaleMaximum ?? Math.max(...values.map(value => Number(value || 0)));
  const minimum = scaleMinimum ?? Math.min(...values.map(value => Number(value || 0)), 0);
  const range = maximum - minimum || 1;
  return values.map((value, index) => {
    const x = values.length === 1 ? width / 2 : index * width / (values.length - 1);
    const y = padding + (height - padding * 2) * (1 - (Number(value || 0) - minimum) / range);
    return `${index ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
}

function renderFinancialTrend(trend) {
  const series = trend.flatMap(row => [row.revenue, row.expense, row.profit]).filter(value => value !== null).map(Number);
  const maximum = Math.max(...series, 1);
  const minimum = Math.min(...series, 0);
  const revenuePath = linePath(trend.map(row => row.revenue), 820, 240, 10, minimum, maximum);
  document.getElementById("revenueLine").setAttribute("d", revenuePath);
  document.getElementById("revenueArea").setAttribute("d", `${revenuePath} L820,260 L0,260 Z`);
  const expenses = trend.map(row => row.expense);
  const profits = trend.map(row => row.profit);
  document.getElementById("expenseLine").setAttribute("d", expenses.every(value => value === null) ? "" : linePath(expenses, 820, 240, 10, minimum, maximum));
  document.getElementById("profitLine").setAttribute("d", profits.every(value => value === null) ? "" : linePath(profits, 820, 240, 10, minimum, maximum));
  document.getElementById("trendYLabels").innerHTML = [
    maximum,
    minimum + (maximum - minimum) * 2 / 3,
    minimum + (maximum - minimum) / 3,
    minimum
  ].map(formatAmount).map(value => `<span>${escapeHtml(value)}</span>`).join("");
  const labels = trend.filter((_, index) => trend.length <= 7 || index % 2 === 0);
  document.getElementById("trendLabels").innerHTML = labels.map(row => `<span>${escapeHtml(row.label)}</span>`).join("");
}

function renderSparkline(id, values) {
  const svg = document.getElementById(id);
  if (!svg) return;
  svg.innerHTML = `<path d="${linePath(values, 320, 55, 5)}"></path>`;
}

function renderCash(cash, trend) {
  setText("cashNet", formatAmount(cash.net_cash_flow));
  setText("cashInflow", formatAmount(cash.total_inflow));
  setText("cashOutflow", formatAmount(cash.total_outflow));
  const max = Math.max(Number(cash.total_inflow || 0), Number(cash.total_outflow || 0), 1);
  document.getElementById("cashInflowBar").style.setProperty("--value", `${Number(cash.total_inflow || 0) / max * 100}%`);
  document.getElementById("cashOutflowBar").style.setProperty("--value", `${Number(cash.total_outflow || 0) / max * 100}%`);
  renderSparkline("cashTrend", trend.map(row => row.cash_flow));
}

function renderCollections(receivables, trend) {
  const rate = Number(receivables.collection_rate_percent || 0);
  setText("collectionRate", `${rate}%`);
  setText("collectionDonutValue", `${rate}%`);
  setText("collectionReceived", formatAmount(receivables.total_received));
  setText("collectionOutstanding", formatAmount(receivables.outstanding_receivables));
  document.getElementById("collectionDonut").style.background =
    `conic-gradient(var(--brand-2) 0 ${rate}%, var(--gold) ${rate}% 100%)`;
  renderSparkline("outstandingTrend", trend.map(row => row.outstanding));
}

function renderInventory(rows) {
  const container = document.getElementById("inventoryLocations");
  const byLocation = new Map();
  rows.forEach(row => byLocation.set(row.store, (byLocation.get(row.store) || 0) + Number(row.stock_qty || 0)));
  const values = [...byLocation.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6);
  const max = Math.max(...values.map(row => row[1]), 1);
  container.innerHTML = values.length ? values.map(([store, quantity]) => `
    <p><span>${escapeHtml(store)}</span><strong>${formatFull(quantity)}</strong><i style="--value:${quantity / max * 100}%"></i></p>
  `).join("") : '<div class="empty-state">No inventory rows match the selected scope.</div>';
}

function renderTopCustomers(rows) {
  const body = document.getElementById("topCustomersBody");
  body.innerHTML = rows.length ? rows.slice(0, 8).map(row => `
    <tr>
      <td><span class="table-avatar">${escapeHtml(initials(row.customer_name || row.item))}</span>${escapeHtml(row.customer_name || row.item || "Unknown")}</td>
      <td>${formatAmount(row.total_amount || row.amount)}</td>
      <td>${formatAmount(row.amount_received)}</td>
      <td>${formatAmount(row.outstanding_amount)}</td>
      <td>${formatFull(row.invoice_count)}</td>
    </tr>
  `).join("") : '<tr><td colspan="5"><div class="empty-state">No customer rows match the selected scope.</div></td></tr>';
}

function renderRankList(id, rows, label, detail, value) {
  const container = document.getElementById(id);
  container.innerHTML = rows.length ? rows.slice(0, 6).map((row, index) => `
    <p>
      <span class="rank">${String(index + 1).padStart(2, "0")}</span>
      <span><strong>${escapeHtml(label(row))}</strong><small>${escapeHtml(detail(row))}</small></span>
      <b>${escapeHtml(value(row))}</b>
    </p>
  `).join("") : '<div class="empty-state">No rows match the selected scope.</div>';
}

function renderPayments(rows) {
  const body = document.getElementById("recentPaymentsBody");
  body.innerHTML = rows.length ? rows.map(row => `
    <tr>
      <td>${escapeHtml(formatDate(row.receive_date))}</td>
      <td>${escapeHtml(row.customer || "—")}</td>
      <td>${escapeHtml(row.voucher_number)}</td>
      <td>${formatAmount(row.receive_amount)}</td>
      <td><span class="pill ${row.payment_status === "Paid" ? "good" : "warn"}">${escapeHtml(row.payment_status)}</span></td>
    </tr>
  `).join("") : '<tr><td colspan="5"><div class="empty-state">No payment rows match the selected scope.</div></td></tr>';
}

function renderTransactions(rows) {
  const body = document.getElementById("recentTransactionsBody");
  body.innerHTML = rows.length ? rows.map(row => `
    <tr>
      <td>${escapeHtml(formatDate(row.Date))}</td>
      <td>${escapeHtml(row.income_expense)}</td>
      <td>${escapeHtml(row.sector)}</td>
      <td>${escapeHtml(row.category)}</td>
      <td>${escapeHtml(row.item || "—")}</td>
      <td>${formatAmount(row.amount)}</td>
    </tr>
  `).join("") : '<tr><td colspan="6"><div class="empty-state">No transaction rows match the selected scope.</div></td></tr>';
}

async function loadExecutiveInsight() {
  const lead = document.getElementById("insightLead");
  const sections = document.getElementById("insightSections");
  if (!lead || !sections) return;
  lead.querySelector("p").textContent = "Loading Qwen executive narrative from validated BI evidence…";
  sections.innerHTML = "";
  try {
    const payload = await apiJson("/api/dashboard/insights/executive", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(filterPayload(false))
    });
    const parsed = parseNarrative(payload.data.narrative);
    lead.querySelector("p").textContent = parsed["Executive Summary"]?.join(" ") || "Executive narrative generated.";
    const labels = ["Business Risks", "Opportunities", "Recommendations", "Management Conclusion"];
    sections.innerHTML = labels.map(label => `
      <div class="insight-section"><strong>${label}</strong><p>${escapeHtml((parsed[label] || ["No narrative returned."]).join(" "))}</p></div>
    `).join("");
  } catch (error) {
    lead.querySelector("p").textContent = "Executive narrative is temporarily unavailable. All calculated dashboard figures remain available.";
    sections.innerHTML = `<div class="insight-section"><strong>Service status</strong><p>${escapeHtml(error.message)}</p></div>`;
  }
}

function parseNarrative(text) {
  const headings = ["Executive Summary", "Business Risks", "Opportunities", "Recommendations", "Management Conclusion"];
  const result = {};
  let current;
  String(text || "").split(/\r?\n/).forEach(raw => {
    const line = raw.replace(/^#+\s*/, "").replaceAll("**", "").trim();
    const heading = headings.find(value => line.toLowerCase() === value.toLowerCase());
    if (heading) {
      current = heading;
      result[current] = [];
    } else if (current && line) {
      result[current].push(line.replace(/^[-*•]\s*/, ""));
    }
  });
  return result;
}

function showDashboardError(message) {
  const error = document.createElement("div");
  error.id = "dashboardError";
  error.className = "data-error";
  error.textContent = `Dashboard data could not be loaded: ${message}`;
  content.prepend(error);
}

function removeDashboardError() {
  document.getElementById("dashboardError")?.remove();
}

function scheduleRefresh() {
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(() => {
    if (activePage === "executive") loadExecutiveDashboard();
  }, 250);
}

async function downloadExport(kind) {
  try {
    showToast(`Preparing ${kind.toUpperCase()} from the validated report renderer…`);
    const response = await fetch(`/api/dashboard/export/${kind}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(filterPayload(false))
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || "Export failed");
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `BigShot_Executive_Dashboard.${kind === "excel" ? "xlsx" : "pdf"}`;
    link.click();
    URL.revokeObjectURL(url);
  } catch (error) {
    showToast(error.message);
  }
}

function updatePeriodControls() {
  document.querySelectorAll(".period-detail").forEach(item => item.classList.remove("visible"));
  if (periodType === "month") document.querySelector(".month-control").classList.add("visible");
  if (periodType === "week") document.querySelector(".week-control").classList.add("visible");
  if (periodType === "range") document.querySelectorAll(".range-control").forEach(item => item.classList.add("visible"));
  if (periodType !== "year") expandedFilters.classList.add("open");
}

document.addEventListener("click", event => {
  const nav = event.target.closest("[data-page]");
  if (nav) renderPage(nav.dataset.page);
  if (event.target.closest(".theme-toggle")) {
    const dark = document.documentElement.dataset.theme === "dark";
    document.documentElement.dataset.theme = dark ? "light" : "dark";
    localStorage.setItem("bigshot-dashboard-theme", document.documentElement.dataset.theme);
  }
});

document.getElementById("menuButton").addEventListener("click", () => sidebar.classList.toggle("open"));
document.getElementById("moreFilters").addEventListener("click", () => expandedFilters.classList.toggle("open"));
document.getElementById("refreshDashboard").addEventListener("click", () => loadExecutiveDashboard(true));
document.getElementById("exportPdf").addEventListener("click", () => downloadExport("pdf"));
document.getElementById("exportExcel").addEventListener("click", () => downloadExport("excel"));
document.getElementById("saveView").addEventListener("click", () => {
  localStorage.setItem("bigshot-dashboard-view", JSON.stringify({ periodType, ...filterPayload(false) }));
  showToast("View saved locally. No business data was stored.");
});
document.querySelectorAll(".period-chip").forEach(button => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".period-chip").forEach(item => item.classList.remove("active"));
    button.classList.add("active");
    periodType = button.dataset.periodType;
    updatePeriodControls();
    scheduleRefresh();
  });
});
Object.values(filterElements).forEach(element => element.addEventListener("change", scheduleRefresh));

async function initialize() {
  const today = new Date();
  filterElements.month.value = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`;
  const first = new Date(today.getFullYear(), 0, 1);
  const week = Math.ceil((((today - first) / 86400000) + first.getDay() + 1) / 7);
  filterElements.week.value = `${today.getFullYear()}-W${String(week).padStart(2, "0")}`;
  filterElements.rangeStart.value = `${today.getFullYear()}-01-01`;
  filterElements.rangeEnd.value = today.toISOString().slice(0, 10);
  document.documentElement.dataset.theme = localStorage.getItem("bigshot-dashboard-theme") || "light";
  try {
    await loadDimensions();
  } catch (error) {
    showToast(`Filter options unavailable: ${error.message}`);
  }
  renderPage(location.hash.replace("#", "") || "executive");
}

initialize();
