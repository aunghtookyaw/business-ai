const pageConfig = {
  executive: {
    title: "Executive Dashboard",
    subtitle: "A thirty-second view of performance, cash and operational risk."
  },
  payments: {
    title: "Payment Analytics",
    subtitle: "Collections, invoice-age analysis and canonical payment history."
  },
  inventory: {
    title: "Inventory Dashboard",
    subtitle: "Milestone 2 — stock position and movement by location.",
    eyebrow: "STOCK & OPERATIONS",
    headline: "Inventory Dashboard is scheduled for Milestone 2.",
    description: "Version 1 shows validated quantities and Formula Engine inventory value by location.",
    kpis: ["Stock Units", "Active Locations", "Production Volume", "Near Stock Out"],
    primary: "Stock movement timeline",
    breakdown: "Stock by product",
    table: "Inventory by location"
  },
  "farm-production": {
    title: "Farm Production",
    subtitle: "Read-only vegetable production trends by crop, farm area and unit."
  },
  "farm-voucher": {
    title: "Farm Voucher",
    subtitle: "Create, validate, preview, print and atomically submit Farm sales vouchers."
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

const startupScreen = document.getElementById("startupScreen");
const loginScreen = document.getElementById("loginScreen");
const loginForm = document.getElementById("loginForm");
const loginUsername = document.getElementById("loginUsername");
const loginPassword = document.getElementById("loginPassword");
const loginButton = document.getElementById("loginButton");
const loginError = document.getElementById("loginError");
const content = document.getElementById("dashboardContent");
const executiveTemplate = document.getElementById("executiveTemplate");
const moduleTemplate = document.getElementById("moduleTemplate");
const farmProductionTemplate = document.getElementById("farmProductionTemplate");
const inventoryTemplate = document.getElementById("inventoryTemplate");
const farmVoucherTemplate = document.getElementById("farmVoucherTemplate");
const paymentsTemplate = document.getElementById("paymentsTemplate");
const pageTitle = document.getElementById("pageTitle");
const pageSubtitle = document.getElementById("pageSubtitle");
const sidebar = document.getElementById("sidebar");
const toast = document.getElementById("toast");
const expandedFilters = document.getElementById("expandedFilters");
const currentYear = new Date().getFullYear();
let activePage = "executive";
let periodType = "year";
let refreshTimer;
let initializedDashboard = false;
let authenticatedUser = null;

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

function formatMmk(value) {
  if (value === null || value === undefined) return "—";
  return `${Number(value || 0).toLocaleString()} MMK`;
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
  } else if (page === "farm-production") {
    content.appendChild(farmProductionTemplate.content.cloneNode(true));
    initializeFarmProduction();
  } else if (page === "inventory") {
    content.appendChild(inventoryTemplate.content.cloneNode(true));
    loadInventoryDashboard();
  } else if (page === "payments") {
    content.appendChild(paymentsTemplate.content.cloneNode(true));
    loadPaymentsDashboard();
  } else if (page === "farm-voucher") {
    content.appendChild(farmVoucherTemplate.content.cloneNode(true));
    initializeFarmVoucher();
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

async function loadPaymentsDashboard(refresh = false) {
  if (activePage !== "payments") return;
  setLoading(true);
  removeDashboardError();
  try {
    const payload = await apiJson("/api/dashboard/payments", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(filterPayload(refresh))
    });
    renderPaymentsDashboard(payload.data);
  } catch (error) { showDashboardError(error.message); }
  finally { setLoading(false); }
}

function renderPaymentsDashboard(data) {
  const metrics = data.metrics || {};
  setText("paymentsInvoiced", formatAmount(metrics.invoiced));
  setText("paymentsReceived", formatAmount(metrics.received));
  setText("paymentsOutstanding", formatAmount(metrics.outstanding));
  setText("paymentsRate", `${Number(metrics.collection_rate_percent || 0).toFixed(1)}%`);
  setText("paymentsVoucherCount", formatFull(metrics.voucher_count));
  const aging = data.aging || {};
  const agingMax = Math.max(1, ...Object.values(aging).map(Number));
  document.getElementById("paymentsAging").innerHTML = ["0-30", "31-60", "61-90", "90+"].map(bucket =>
    `<div><span>${bucket} days</span><strong>${formatMmk(aging[bucket] || 0)}</strong><i style="--value:${Number(aging[bucket] || 0) / agingMax * 100}%"></i></div>`
  ).join("");
  document.getElementById("paymentsCustomersBody").innerHTML = (data.customer_balances || []).map(row =>
    `<tr><td>${escapeHtml(row.customer || "—")}</td><td>${formatFull(row.outstanding_balance)} MMK</td></tr>`
  ).join("") || '<tr><td colspan="2"><div class="empty-state">No customer balances match this scope.</div></td></tr>';
  document.getElementById("paymentsInvoicesBody").innerHTML = (data.invoices || []).map(row =>
    `<tr><td>${escapeHtml(row.customer || "—")}</td><td>${escapeHtml(row.sector)}</td><td>${escapeHtml(row.voucher_number)}</td><td>${formatDate(row.invoice_date)}</td><td>${formatFull(row.invoice_amount)}</td><td>${formatFull(row.received_amount)}</td><td>${formatFull(row.outstanding_balance)}</td><td><span class="pill ${row.payment_status === "Paid" ? "good" : row.payment_status === "Partial" ? "warn" : "alert-pill"}">${row.payment_status}</span></td></tr>`
  ).join("") || '<tr><td colspan="8"><div class="empty-state">No vouchers match this scope.</div></td></tr>';
  document.getElementById("paymentsHistoryBody").innerHTML = (data.recent_payments || []).map(row =>
    `<tr><td>${formatDate(row.receive_date)}</td><td>${escapeHtml(row.customer || "—")}</td><td>${escapeHtml(row.sector)}</td><td>${escapeHtml(row.voucher_number)}</td><td>${formatFull(row.receive_amount)}</td><td>${escapeHtml(row.payment_method || "—")}</td><td>${escapeHtml(row.reference_number || "—")}</td></tr>`
  ).join("") || '<tr><td colspan="7"><div class="empty-state">No payment receipts match this scope.</div></td></tr>';
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
  if (response.status === 401) {
    showLogin("Please sign in to continue.");
    throw new Error(payload.error || "Authentication required");
  }
  if (!response.ok || !payload.ok) throw new Error(payload.error || `Request failed: ${response.status}`);
  return payload;
}

function showLogin(message = "") {
  authenticatedUser = null;
  initializedDashboard = false;
  clearTimeout(refreshTimer);
  document.querySelectorAll(".app-authenticated").forEach(element => element.classList.remove("visible"));
  loginScreen.classList.remove("hidden");
  loginError.textContent = message;
  loginPassword.value = "";
  setTimeout(() => loginUsername.focus(), 0);
}

function showDashboard(user) {
  authenticatedUser = user;
  document.querySelectorAll(".app-authenticated").forEach(element => element.classList.add("visible"));
  loginScreen.classList.add("hidden");
  document.getElementById("signedInUser").textContent = user?.username || "Master";
  document.getElementById("signedInRole").textContent = `${user?.role || "Admin"} View`;
}

async function currentSession() {
  const payload = await apiJson("/api/auth/session");
  return payload;
}

async function login(username, password) {
  const payload = await apiJson("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password })
  });
  return payload.user;
}

async function logout() {
  try {
    await apiJson("/api/auth/logout", { method: "POST" });
  } finally {
    history.replaceState(null, "", location.pathname);
    content.innerHTML = "";
    showLogin("");
  }
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
  const inventoryRows = data.inventory.stock || [];
  setText("metricInventoryValue", formatFull(inventoryRows.reduce((total, row) => total + Number(row.stock_qty || row.qty || 0), 0)));
  setText("metricMargin", metrics.profit_margin_percent === null ? "Unavailable for customer scope" : `${metrics.profit_margin_percent}% profit margin`);
  setText("metricPeriodLabel", data.filter_label);
  setText("expenseTotalPanel", formatAmount(metrics.expenses));

  renderFinancialTrend(data.trend);
  renderCash(data.cash_flow, data.trend);
  renderCollections(data.receivables, data.trend);
  renderInventory(inventoryRows);
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
  rows.forEach(row => {
    const current = byLocation.get(row.store) || { quantity: 0 };
    current.quantity += Number(row.stock_qty || row.qty || 0);
    byLocation.set(row.store, current);
  });
  const values = [...byLocation.entries()].sort((a, b) => b[1].quantity - a[1].quantity).slice(0, 6);
  const max = Math.max(...values.map(row => row[1].quantity), 1);
  container.innerHTML = values.length ? values.map(([store, summary]) => `
    <p><span>${escapeHtml(store)}</span><strong>${formatFull(summary.quantity)} bottles</strong><i style="--value:${summary.quantity / max * 100}%"></i></p>
  `).join("") : '<div class="empty-state">No inventory rows match the selected scope.</div>';
}

const analyticsColors = ["#176b5d", "#d6a84b", "#4d7ea8", "#9b5de5", "#d95d39", "#2a9d8f", "#7f5539", "#e76f51"];

function isoDate(value) {
  return value.toISOString().slice(0, 10);
}

function selectedValues(select) {
  return [...select.selectedOptions].map(option => Number(option.value));
}

async function initializeFarmProduction() {
  const end = new Date();
  const start = new Date(end); start.setDate(start.getDate() - 29);
  document.getElementById("farmStartDate").value = isoDate(start);
  document.getElementById("farmEndDate").value = isoDate(end);
  document.querySelectorAll("[data-farm-days]").forEach(button => button.addEventListener("click", () => {
    const nextEnd = new Date(); const nextStart = new Date(nextEnd);
    nextStart.setDate(nextStart.getDate() - Number(button.dataset.farmDays) + 1);
    document.getElementById("farmStartDate").value = isoDate(nextStart);
    document.getElementById("farmEndDate").value = isoDate(nextEnd);
    loadFarmProduction();
  }));
  ["farmStartDate", "farmEndDate", "farmGrouping"].forEach(id => document.getElementById(id).addEventListener("change", () => loadFarmProduction()));
  document.getElementById("farmAreaFilter").addEventListener("change", handleFarmAreaChange);
  document.getElementById("farmFieldToggle").addEventListener("click", () => toggleFarmSelector("farmFieldPanel", "farmFieldToggle"));
  document.getElementById("farmVegetableToggle").addEventListener("click", () => toggleFarmSelector("farmVegetablePanel", "farmVegetableToggle"));
  document.getElementById("farmFieldApply").addEventListener("click", () => applyFarmSelector("farmFieldPanel", "farmFieldToggle"));
  document.getElementById("farmVegetableApply").addEventListener("click", () => applyFarmSelector("farmVegetablePanel", "farmVegetableToggle"));
  document.getElementById("farmCropSearch").addEventListener("input", filterFarmCropChoices);
  document.getElementById("farmTotalsSearch").addEventListener("input", filterFarmVegetableTotals);
  document.getElementById("farmSelectAll").addEventListener("click", () => setAllFarmCrops(true));
  document.getElementById("farmClearAll").addEventListener("click", () => setAllFarmCrops(false));
  await loadFarmProduction();
}

function farmPayload() {
  const filters = {
    start_date: document.getElementById("farmStartDate").value,
    end_date: document.getElementById("farmEndDate").value,
    grouping: document.getElementById("farmGrouping").value,
    farm_area_ids: [...document.querySelectorAll(".farm-area-check:checked")].filter(input => input.value !== "all").map(input => Number(input.value)),
  };
  const cropInputs = [...document.querySelectorAll(".farm-crop-check")];
  if (cropInputs.length) filters.crop_ids = cropInputs.filter(input => input.checked).map(input => Number(input.value));
  return {filters};
}

async function loadFarmProduction() {
  const error = document.getElementById("farmProductionError");
  error.innerHTML = ""; content.classList.add("loading-state");
  try {
    const payload = await apiJson("/api/dashboard/farm-production", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(farmPayload())});
    renderFarmProduction(payload.data);
  } catch (exc) {
    error.innerHTML = `<div class="data-error">${escapeHtml(exc.message)}</div>`;
  } finally { content.classList.remove("loading-state"); }
}

function renderFarmProduction(data) {
  const area = document.getElementById("farmAreaFilter");
  if (!area.children.length) area.innerHTML = `<label aria-label="All Fields"><input class="farm-area-check" type="checkbox" value="all" checked><i aria-hidden="true">✓</i><span>All Fields</span></label>${data.available_farm_areas.map(row => {const short=row.area_name.replace(/\s+Farm$/i,""); return `<label aria-label="${escapeHtml(row.area_name)}"><input class="farm-area-check" type="checkbox" value="${row.id}"><i aria-hidden="true">✓</i><span class="short-label">${escapeHtml(short)}</span><span class="full-label">${escapeHtml(row.area_name)}</span></label>`;}).join("")}`;
  const choices = document.getElementById("farmCropChoices");
  if (!choices.children.length) choices.innerHTML = data.available_crops.map(row => `<label><input class="farm-crop-check" type="checkbox" value="${row.id}" ${data.selected_crop_ids.includes(row.id) ? "checked" : ""}><span>${escapeHtml(row.crop_name)}</span></label>`).join("");
  choices.querySelectorAll("input").forEach(input => { if (!input.dataset.bound) { input.dataset.bound="1"; input.addEventListener("change", handleFarmCropChange); }});
  updateFarmSelectorSummaries();
  const totals = data.totals || [];
  document.getElementById("farmProductionKpis").innerHTML = totals.length ? totals.map((row,index) => `<article class="metric-card"><div class="metric-label"><span>Overall Production</span><span class="metric-icon">${index+1}</span></div><strong>${formatFull(row.quantity)}</strong><small>${escapeHtml(row.unit)} · selected fields</small></article>`).join("") : '<div class="empty-state">No production exists for this selection.</div>';
  setText("farmLastData", data.last_data_date ? `Last data ${formatDate(data.last_data_date)}` : "No data");
  renderFarmFieldSummary(data.summary_by_area || []);
  renderFarmVegetableTotals(data.summary_by_crop || []);
  renderFarmTrend(data.combined_rows || []);
  const combinedRows=data.combined_rows||[];
  document.getElementById("farmProductionBody").innerHTML = combinedRows.length ? combinedRows.map(row => `<tr><td>${escapeHtml(formatDate(row.production_date))}</td><td>${escapeHtml(row.crop_name)}</td><td>${escapeHtml(row.farm_area)}</td><td>${formatFull(row.quantity)}</td><td>${escapeHtml(row.unit || "Unspecified")}</td></tr>`).join("") : '<tr><td colspan="5"><div class="empty-state">No production exists for this period and selection.</div></td></tr>';
}

function handleFarmAreaChange(event) {
  const all=document.querySelector('.farm-area-check[value="all"]'), individuals=[...document.querySelectorAll('.farm-area-check:not([value="all"])')];
  if(event.target.value==="all"&&event.target.checked) individuals.forEach(input=>input.checked=false);
  else if(event.target.value!=="all"&&event.target.checked) all.checked=false;
  if(!all.checked&&!individuals.some(input=>input.checked)) all.checked=true;
  updateFarmSelectorSummaries();
  if(!isMobileFarmFilters()) loadFarmProduction();
}

function isMobileFarmFilters(){return window.matchMedia("(max-width: 768px)").matches;}
function toggleFarmSelector(panelId,toggleId){const panel=document.getElementById(panelId),toggle=document.getElementById(toggleId),open=!panel.classList.contains("open"); panel.classList.toggle("open",open); toggle.setAttribute("aria-expanded",String(open));}
function applyFarmSelector(panelId,toggleId){document.getElementById(panelId).classList.remove("open"); document.getElementById(toggleId).setAttribute("aria-expanded","false"); updateFarmSelectorSummaries(); loadFarmProduction();}
function handleFarmCropChange(){updateFarmSelectorSummaries(); if(!isMobileFarmFilters())loadFarmProduction();}
function updateFarmSelectorSummaries(){
  const all=document.querySelector('.farm-area-check[value="all"]'),selected=[...document.querySelectorAll('.farm-area-check:not([value="all"]):checked')];
  const fieldText=all?.checked||!selected.length?"All Fields":selected.map(input=>input.closest("label").querySelector(".short-label")?.textContent||input.closest("label").getAttribute("aria-label")).join(", ");
  setText("farmFieldCount",fieldText); const fieldToggle=document.getElementById("farmFieldToggle"); if(fieldToggle)fieldToggle.innerHTML=`Fields: ${escapeHtml(fieldText)} <span>▾</span>`;
  const cropCount=document.querySelectorAll(".farm-crop-check:checked").length; setText("farmVegetableCount",`${cropCount} selected`); const cropToggle=document.getElementById("farmVegetableToggle"); if(cropToggle)cropToggle.innerHTML=`Vegetables: ${cropCount} selected <span>▾</span>`;
}

function renderFarmFieldSummary(rows) {
  document.getElementById("farmFieldSummary").innerHTML=rows.map(row=>`<article class="summary-card"><h3>${escapeHtml(row.farm_area)}</h3><div class="summary-quantities">${(row.quantities_by_unit||[]).map(total=>`<strong>${formatFull(total.quantity)} <small>${escapeHtml(total.unit)}</small></strong>`).join("")||'<strong>0 <small>No production</small></strong>'}</div><p>${formatFull(row.crop_count)} vegetable varieties</p><p>Latest: ${row.latest_production_date?escapeHtml(formatDate(row.latest_production_date)):"No production"}</p></article>`).join("")||'<div class="empty-state">No active fields are available.</div>';
}

function renderFarmVegetableTotals(rows) {
  document.getElementById("farmVegetableTotals").innerHTML=rows.map(row=>{const change=row.percentage_change===null?"No valid previous comparison":`${Number(row.percentage_change)>=0?"+":""}${Number(row.percentage_change).toFixed(1)}% vs previous period`; return `<article class="summary-card vegetable-total-card" data-crop-name="${escapeHtml(row.crop_name.toLowerCase())}"><h3>${escapeHtml(row.crop_name)}</h3><strong>${formatFull(row.quantity)} <small>${escapeHtml(row.unit)}</small></strong><p class="${Number(row.percentage_change)>=0?"positive":"negative"}">${escapeHtml(change)}</p></article>`;}).join("")||'<div class="empty-state">No vegetables were produced for this selection.</div>';
  filterFarmVegetableTotals();
}

function filterFarmVegetableTotals(){const input=document.getElementById("farmTotalsSearch"); if(!input)return; const query=input.value.trim().toLowerCase(); document.querySelectorAll(".vegetable-total-card").forEach(card=>card.hidden=!card.dataset.cropName.includes(query));}

function renderFarmTrend(rows) {
  const chart = document.getElementById("farmTrendChart"), legend=document.getElementById("farmLegend");
  if (!rows.length) { chart.innerHTML='<div class="empty-state">No production exists for this period and selection.</div>'; legend.innerHTML=""; return; }
  const units=[...new Set(rows.map(row=>row.unit||"Unspecified"))];
  let colorIndex=0; const legends=[];
  chart.innerHTML=units.map(unit=>{
    const unitRows=rows.filter(row=>(row.unit||"Unspecified")===unit), dates=[...new Set(unitRows.map(row=>row.production_date))].sort();
    const seriesKeys=[...new Set(unitRows.map(row=>String(row.crop_id)))];
    const maximum=Math.max(...unitRows.map(row=>Number(row.quantity)),1);
    const dense=dates.length>30;
    const lines=seriesKeys.map(key=>{const sample=unitRows.find(row=>String(row.crop_id)===key); const color=analyticsColors[colorIndex++%analyticsColors.length]; legends.push({label:`${sample.crop_name} · ${unit}`,color}); const values=dates.map(date=>Number(unitRows.find(row=>row.production_date===date&&String(row.crop_id)===key)?.quantity||0)); const points=dates.map((date,index)=>{const row=unitRows.find(item=>item.production_date===date&&String(item.crop_id)===key); if(!row)return ""; const x=dates.length===1?410:index*820/(dates.length-1), y=12+(220-24)*(1-Number(row.quantity)/maximum); const tooltip=`${date} · ${row.crop_name} · ${row.farm_area} · ${formatFull(row.quantity)} ${unit}`; return `<g class="farm-point-group"><circle class="farm-point-marker" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="2" fill="${color}" stroke="${color}"></circle><circle class="farm-point-hit" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="8"><title>${escapeHtml(tooltip)}</title></circle></g>`;}).join(""); return `<path d="${linePath(values,820,220,12,0,maximum)}" stroke="${color}"></path>${points}`;}).join("");
    return `<div><strong>${escapeHtml(unit)}</strong><svg class="${dense?"dense-series":""}" viewBox="0 0 820 240" preserveAspectRatio="none" aria-label="Farm production trend for ${escapeHtml(unit)}">${lines}</svg><div class="x-labels">${dates.filter((_,i)=>dates.length<8||i%Math.ceil(dates.length/7)===0).map(date=>`<span>${escapeHtml(date)}</span>`).join("")}</div></div>`;
  }).join("");
  legend.innerHTML=legends.map(row=>`<span><i style="background:${row.color}"></i>${escapeHtml(row.label)}</span>`).join("");
}

function filterFarmCropChoices() { const q=document.getElementById("farmCropSearch").value.toLowerCase(); document.querySelectorAll("#farmCropChoices label").forEach(label=>label.hidden=!label.textContent.toLowerCase().includes(q)); }
function setAllFarmCrops(checked) { document.querySelectorAll(".farm-crop-check").forEach(input=>input.checked=checked); updateFarmSelectorSummaries(); if(!isMobileFarmFilters())loadFarmProduction(); }

async function loadInventoryDashboard() {
  const error=document.getElementById("inventoryError"); error.innerHTML=""; content.classList.add("loading-state");
  try { const payload=await apiJson("/api/dashboard/inventory"); renderInventoryDashboard(payload.data); }
  catch(exc){ error.innerHTML=`<div class="data-error">${escapeHtml(exc.message)}</div>`; }
  finally { content.classList.remove("loading-state"); }
}

function renderInventoryDashboard(data) {
  setText("inventoryLastUpdated", data.last_updated ? `Updated ${formatDate(data.last_updated)}` : "No data");
  document.getElementById("inventoryKpis").innerHTML=(data.bottle_totals||[]).map((row,index)=>`<article class="metric-card"><div class="metric-label"><span>${escapeHtml(row.bottle_type)}</span><span class="metric-icon">${index+1}</span></div><strong>${formatFull(row.current_quantity)}</strong><small>bottles</small></article>`).join("")||'<div class="empty-state">No current inventory.</div>';
  const types=data.bottle_types||[], colors=Object.fromEntries(types.map((type,i)=>[type,analyticsColors[i%analyticsColors.length]])), max=Math.max(...(data.store_totals||[]).map(row=>row.current_quantity),1);
  document.getElementById("inventoryStackedChart").innerHTML=(data.store_totals||[]).map(store=>{const segments=types.map(type=>{const row=data.stock.find(item=>item.store===store.store&&item.bottle_type===type); const qty=Number(row?.current_quantity||0); return `<span style="width:${qty/max*100}%;background:${colors[type]}" title="${escapeHtml(store.store)} · ${escapeHtml(type)} · ${formatFull(qty)}"></span>`;}).join(""); return `<div><label>${escapeHtml(store.store)} <strong>${formatFull(store.current_quantity)}</strong></label><p>${segments}</p></div>`;}).join("")||'<div class="empty-state">No current inventory.</div>';
  document.getElementById("inventoryLegend").innerHTML=types.map(type=>`<span><i style="background:${colors[type]}"></i>${escapeHtml(type)}</span>`).join("");
  const stores=(data.store_totals||[]).map(row=>row.store);
  document.getElementById("inventoryMatrix").innerHTML=`<thead><tr><th>Store</th>${types.map(type=>`<th>${escapeHtml(type)}</th>`).join("")}<th>Total</th></tr></thead><tbody>${stores.map(store=>`<tr><td>${escapeHtml(store)}</td>${types.map(type=>`<td>${formatFull(data.stock.find(row=>row.store===store&&row.bottle_type===type)?.current_quantity||0)}</td>`).join("")}<td>${formatFull(data.store_totals.find(row=>row.store===store).current_quantity)}</td></tr>`).join("")}</tbody>`;
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

let farmVoucherDraft = null;
let farmVoucherCustomers = [];

function voucherLineRow(line = {}) {
  return `<tr>
    <td><input data-voucher-field="description" value="${escapeHtml(line.description || "")}" placeholder="Product"></td>
    <td><input data-voucher-field="quantity" type="number" min="0" step="0.01" value="${escapeHtml(line.quantity ?? 1)}"></td>
    <td><input data-voucher-field="unit" value="${escapeHtml(line.unit || "")}" placeholder="kg / bunch"></td>
    <td><input data-voucher-field="unit_price" type="number" min="0" step="0.01" value="${escapeHtml(line.unit_price ?? 0)}"></td>
    <td data-voucher-amount>0</td><td><button class="line-remove" type="button" aria-label="Remove line">×</button></td>
  </tr>`;
}

function updateVoucherTotals() {
  let total = 0;
  document.querySelectorAll("#voucherLines tr").forEach(row => {
    const quantity = Number(row.querySelector('[data-voucher-field="quantity"]')?.value || 0);
    const price = Number(row.querySelector('[data-voucher-field="unit_price"]')?.value || 0);
    const amount = quantity * price;
    row.querySelector("[data-voucher-amount]").textContent = formatFull(amount);
    total += amount;
  });
  setText("voucherTotal", `${formatFull(total)} MMK`);
}

function collectVoucherForm() {
  const customer = farmVoucherCustomers.find(row => String(row.id) === document.getElementById("voucherCustomer").value);
  return {
    sector: "farm", voucher_number: document.getElementById("voucherNumber").value.trim(),
    voucher_date: document.getElementById("voucherDate").value,
    customer_id: customer?.id || null, customer_name: customer?.customer_name || "",
    payment_method: document.getElementById("voucherPaymentMethod").value.trim(),
    amount_received: document.getElementById("voucherReceived").value || "0",
    note: document.getElementById("voucherNote").value.trim(), version: farmVoucherDraft?.version,
    lines: Array.from(document.querySelectorAll("#voucherLines tr")).map(row => ({
      description: row.querySelector('[data-voucher-field="description"]').value.trim(),
      quantity: row.querySelector('[data-voucher-field="quantity"]').value,
      unit: row.querySelector('[data-voucher-field="unit"]').value.trim(),
      unit_price: row.querySelector('[data-voucher-field="unit_price"]').value
    }))
  };
}

function showVoucherErrors(errors = []) {
  document.getElementById("voucherErrors").innerHTML = errors.length
    ? `<div class="data-error">${errors.map(escapeHtml).join("<br>")}</div>` : "";
}

function fillVoucherForm(draft = null) {
  farmVoucherDraft = draft;
  document.getElementById("voucherNumber").value = draft?.voucher_number || "";
  document.getElementById("voucherDate").value = draft?.voucher_date || new Date().toISOString().slice(0, 10);
  document.getElementById("voucherCustomer").value = draft?.customer_id || "";
  document.getElementById("voucherPaymentMethod").value = draft?.payment_method || "";
  document.getElementById("voucherReceived").value = draft?.amount_received || "0";
  document.getElementById("voucherNote").value = draft?.note || "";
  document.getElementById("voucherLines").innerHTML = (draft?.lines?.length ? draft.lines : [{}]).map(voucherLineRow).join("");
  document.getElementById("voucherState").textContent = draft?.status || "draft";
  document.getElementById("voucherEditorTitle").textContent = draft ? `Farm Voucher #${draft.id}` : "New Farm Voucher";
  const submitted = draft?.status === "submitted";
  document.querySelectorAll(".voucher-workspace input,.voucher-workspace select,.voucher-workspace textarea").forEach(field => field.disabled = submitted);
  document.getElementById("voucherSubmit").disabled = draft?.status !== "previewed";
  document.getElementById("voucherPdf").disabled = !draft || !["previewed", "submitted"].includes(draft.status);
  showVoucherErrors(); updateVoucherTotals();
}

async function loadVoucherDrafts() {
  const payload = await apiJson("/api/vouchers/farm/drafts");
  document.getElementById("voucherDrafts").innerHTML = payload.drafts.map(draft =>
    `<button type="button" data-draft-id="${draft.id}"><strong>${escapeHtml(draft.voucher_number || `Draft ${draft.id}`)}</strong><span>${escapeHtml(draft.customer_name || "No customer")} · ${escapeHtml(draft.status)}</span></button>`
  ).join("") || '<div class="empty-state">No Farm Voucher drafts yet.</div>';
}

async function saveFarmVoucher() {
  const values = collectVoucherForm();
  const url = farmVoucherDraft ? `/api/vouchers/farm/drafts/${farmVoucherDraft.id}` : "/api/vouchers/farm/drafts";
  const payload = await apiJson(url, {method: farmVoucherDraft ? "PUT" : "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(values)});
  fillVoucherForm(payload.draft); await loadVoucherDrafts(); return payload.draft;
}

function renderVoucherPreview(voucher) {
  const panel = document.getElementById("voucherPreviewPanel"); panel.hidden = false;
  panel.innerHTML = `<div class="print-voucher"><h2>BigShot Farm Voucher</h2><p><b>Voucher:</b> ${escapeHtml(voucher.voucher_number)} · <b>Date:</b> ${escapeHtml(voucher.voucher_date)}</p><p><b>Customer:</b> ${escapeHtml(voucher.customer_name)}</p><table><thead><tr><th>Description</th><th>Qty</th><th>Unit</th><th>Price</th><th>Amount</th></tr></thead><tbody>${voucher.lines.map(line => `<tr><td>${escapeHtml(line.description)}</td><td>${escapeHtml(line.quantity)}</td><td>${escapeHtml(line.unit)}</td><td>${formatFull(line.unit_price)}</td><td>${formatFull(line.amount)}</td></tr>`).join("")}</tbody></table><p class="preview-total"><b>Total:</b> ${formatFull(voucher.total_amount)} MMK<br><b>Received:</b> ${formatFull(voucher.amount_received)} MMK<br><b>Outstanding:</b> ${formatFull(voucher.outstanding_balance)} MMK</p></div>`;
}

async function voucherWorkflow(action) {
  try {
    const draft = await saveFarmVoucher();
    const payload = await apiJson(`/api/vouchers/farm/drafts/${draft.id}/${action}`, {method: "POST"});
    fillVoucherForm(payload.draft);
    if (payload.voucher) renderVoucherPreview(payload.voucher);
    await loadVoucherDrafts(); showToast(`Farm Voucher ${action} complete.`);
  } catch (error) { showVoucherErrors(error.errors || [error.message]); }
}

async function initializeFarmVoucher() {
  try {
    const customers = await apiJson("/api/vouchers/farm/customers"); farmVoucherCustomers = customers.customers;
    document.getElementById("voucherCustomer").innerHTML = '<option value="">Select Customer Master</option>' + farmVoucherCustomers.map(row => `<option value="${row.id}">${escapeHtml(row.customer_name)} · ${escapeHtml(row.customer_code || row.id)}</option>`).join("");
    fillVoucherForm(); await loadVoucherDrafts();
    document.getElementById("voucherNew").onclick = () => fillVoucherForm();
    document.getElementById("voucherAddLine").onclick = () => { document.getElementById("voucherLines").insertAdjacentHTML("beforeend", voucherLineRow()); updateVoucherTotals(); };
    document.getElementById("voucherLines").addEventListener("input", updateVoucherTotals);
    document.getElementById("voucherLines").addEventListener("click", event => { if (event.target.matches(".line-remove")) { event.target.closest("tr").remove(); updateVoucherTotals(); } });
    document.getElementById("voucherDrafts").addEventListener("click", async event => { const button = event.target.closest("[data-draft-id]"); if (!button) return; const payload = await apiJson(`/api/vouchers/farm/drafts/${button.dataset.draftId}`); fillVoucherForm(payload.draft); });
    document.getElementById("voucherSave").onclick = () => saveFarmVoucher().then(() => showToast("Draft saved.")).catch(error => showVoucherErrors([error.message]));
    document.getElementById("voucherValidate").onclick = () => voucherWorkflow("validate");
    document.getElementById("voucherPreview").onclick = () => voucherWorkflow("preview");
    document.getElementById("voucherPdf").onclick = () => { if (farmVoucherDraft) location.href = `/api/vouchers/farm/drafts/${farmVoucherDraft.id}/pdf`; };
    document.getElementById("voucherSubmit").onclick = async () => { if (!farmVoucherDraft || !confirm("Submit this validated Farm Voucher to farm_transection? This cannot be edited afterward.")) return; try { const payload = await apiJson(`/api/vouchers/farm/drafts/${farmVoucherDraft.id}/submit`, {method:"POST"}); fillVoucherForm(payload.draft); await loadVoucherDrafts(); showToast(`Submitted as Farm transaction ${payload.transaction_id}.`); } catch (error) { showVoucherErrors([error.message]); } };
  } catch (error) { showDashboardError(error.message); }
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
    if (activePage === "payments") loadPaymentsDashboard();
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
    if (response.status === 401) {
      showLogin("Please sign in to continue.");
      return;
    }
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

function initialPage() {
  const hashPage = location.hash.replace("#", "");
  if (pageConfig[hashPage]) return hashPage;
  const pathPage = location.pathname.replace(/^\/+/, "");
  if (pageConfig[pathPage]) return pathPage;
  return "executive";
}

document.addEventListener("click", event => {
  const nav = event.target.closest("[data-page]");
  if (nav) {
    if (!authenticatedUser) return showLogin("Please sign in to continue.");
    renderPage(nav.dataset.page);
  }
  if (event.target.closest(".theme-toggle")) {
    const dark = document.documentElement.dataset.theme === "dark";
    document.documentElement.dataset.theme = dark ? "light" : "dark";
    localStorage.setItem("bigshot-dashboard-theme", document.documentElement.dataset.theme);
  }
});

loginForm.addEventListener("submit", async event => {
  event.preventDefault();
  loginError.textContent = "";
  loginButton.disabled = true;
  try {
    const user = await login(loginUsername.value.trim(), loginPassword.value);
    showDashboard(user);
    await initializeDashboard();
  } catch (error) {
    showLogin(error.message);
  } finally {
    loginButton.disabled = false;
  }
});

document.querySelectorAll(".logout-button").forEach(button => {
  button.addEventListener("click", logout);
});
document.getElementById("menuButton").addEventListener("click", () => sidebar.classList.toggle("open"));
document.getElementById("moreFilters").addEventListener("click", () => expandedFilters.classList.toggle("open"));
document.getElementById("refreshDashboard").addEventListener("click", () => activePage === "payments" ? loadPaymentsDashboard(true) : loadExecutiveDashboard(true));
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

async function initializeDashboard() {
  if (initializedDashboard) return;
  initializedDashboard = true;
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
  renderPage(initialPage());
}

async function initialize() {
  document.documentElement.dataset.theme = localStorage.getItem("bigshot-dashboard-theme") || "light";
  try {
    const session = await currentSession();
    if (session.authenticated) {
      showDashboard(session.user);
      await initializeDashboard();
    } else {
      showLogin(new URLSearchParams(location.search).get("login") === "required" ? "Please sign in to continue." : "");
    }
  } catch (error) {
    showLogin(error.message);
  } finally {
    startupScreen.hidden = true;
  }
}

initialize();
