const pageConfig = {
  executive: {
    title: "Executive Dashboard",
    subtitle: "A thirty-second view of performance, cash and operational risk."
  },
  payments: {
    title: "Payment Analytics",
    subtitle: "Collections, aging, customer payment history and receivable risk.",
    eyebrow: "RECEIVABLES & COLLECTIONS",
    headline: "Turn outstanding balances into accountable collection actions.",
    description: "All values map to payment and voucher summaries provided by the Business Intelligence engine.",
    kpis: ["Outstanding Receivables", "Collection Rate", "Received This Period", "Overdue Customers"],
    primary: "Collection and outstanding trend",
    breakdown: "Payment status distribution",
    table: "Customer aging and payment history"
  },
  inventory: {
    title: "Inventory Dashboard",
    subtitle: "Stock position, movement and operating availability by location.",
    eyebrow: "STOCK & OPERATIONS",
    headline: "See where stock is, how it moved and where attention is required.",
    description: "Version 1 shows validated quantities. Value, turnover, fast-moving and dead-stock metrics remain unavailable until the BI engine receives cost and aging models.",
    kpis: ["Stock Units", "Active Locations", "Production Volume", "Near Stock Out"],
    primary: "Stock movement timeline",
    breakdown: "Stock by product",
    table: "Inventory by location"
  },
  customers: {
    title: "Customer Dashboard",
    subtitle: "Revenue concentration, collection behaviour and customer performance.",
    eyebrow: "CUSTOMER INTELLIGENCE",
    headline: "Balance growth opportunity with concentration and collection risk.",
    description: "Customer ranking and payment behaviour use canonical sales and receivable reports.",
    kpis: ["Active Customers", "Top Customer Revenue", "Outstanding Customers", "Average Collection"],
    primary: "Revenue by customer trend",
    breakdown: "Customer payment behaviour",
    table: "Revenue and outstanding ranking"
  },
  farm: {
    title: "Farm Dashboard",
    subtitle: "Farm revenue, cost, cash flow and operating performance.",
    eyebrow: "FARM MANAGEMENT",
    headline: "Connect commercial results with farm operating activity.",
    description: "Financial metrics come from canonical Farm BI filters; crop and farm inventory views appear only where validated source data exists.",
    kpis: ["Farm Revenue", "Farm Expenses", "Farm Profit", "Farm Cash Flow"],
    primary: "Farm revenue and expense trend",
    breakdown: "Expense mix",
    table: "Farm customer and crop performance"
  },
  "sote-phwar": {
    title: "Sote Phwar Dashboard",
    subtitle: "Sales, production, inventory, dealers and receivables.",
    eyebrow: "SOTE PHWAR MANAGEMENT",
    headline: "Manage growth, stock availability and dealer collections together.",
    description: "Sales use Sotephwar_Transection; inventory uses the movement ledger; expenses use canonical Sote Phwar sector filters.",
    kpis: ["Sote Phwar Revenue", "Net Profit", "Production Units", "Outstanding"],
    primary: "Sales, production and collection trend",
    breakdown: "Product sales mix",
    table: "Dealer performance"
  },
  financial: {
    title: "Financial Dashboard",
    subtitle: "Profit and loss, cash flow and period comparisons.",
    eyebrow: "FINANCIAL CONTROL",
    headline: "A CFO view of profitability, cash conversion and cost movement.",
    description: "Balance sheet remains future-ready. Version 1 presents only validated profit, cash flow, revenue, expense and comparison outputs.",
    kpis: ["Revenue", "Expenses", "Net Profit", "Net Cash Flow"],
    primary: "Monthly and yearly comparison",
    breakdown: "Revenue and expense breakdown",
    table: "Profit and loss detail"
  },
  insights: {
    title: "AI Insights",
    subtitle: "Executive narrative generated from validated BI results.",
    eyebrow: "QWEN MANAGEMENT NARRATIVE",
    headline: "Explain what changed, why it matters and what management should do.",
    description: "Qwen receives calculated BI outputs only. It does not calculate KPIs or query the database.",
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

function metricCard(label, index) {
  const values = ["BI output", "Validated", "Read only", "Global filter"];
  return `
    <article class="metric-card">
      <div class="metric-label"><span>${label}</span><span class="metric-icon">${index + 1}</span></div>
      <strong>${values[index]}</strong>
      <p class="neutral">API contract <span>defined in Phase 1</span></p>
    </article>`;
}

function renderPage(page) {
  const config = pageConfig[page] || pageConfig.executive;
  pageTitle.textContent = config.title;
  pageSubtitle.textContent = config.subtitle;
  content.innerHTML = "";

  if (page === "executive") {
    content.appendChild(executiveTemplate.content.cloneNode(true));
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
  showToast.timer = setTimeout(() => toast.classList.remove("show"), 2600);
}

document.addEventListener("click", event => {
  const nav = event.target.closest("[data-page]");
  if (nav) renderPage(nav.dataset.page);

  const action = event.target.closest("[data-toast]");
  if (action) showToast(action.dataset.toast);

  if (event.target.closest(".theme-toggle")) {
    const dark = document.documentElement.dataset.theme === "dark";
    document.documentElement.dataset.theme = dark ? "light" : "dark";
  }
});

document.getElementById("menuButton").addEventListener("click", () => sidebar.classList.toggle("open"));
document.getElementById("moreFilters").addEventListener("click", () => {
  document.getElementById("expandedFilters").classList.toggle("open");
});
document.querySelectorAll(".period-chip").forEach(button => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".period-chip").forEach(item => item.classList.remove("active"));
    button.classList.add("active");
    showToast(`${button.textContent} period selected. All widgets share this filter in Version 1.`);
  });
});

renderPage(location.hash.replace("#", "") || "executive");
