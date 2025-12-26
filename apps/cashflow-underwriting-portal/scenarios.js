const DASHBOARD_JSON_URL = "data/dashboard.json";

function showFatal(message, details = "") {
  const pill = document.getElementById("generatedAt");
  if (pill) pill.textContent = "Load error";

  const container = document.querySelector(".container");
  const panel = document.createElement("section");
  panel.className = "panel";
  panel.innerHTML = `
    <div class="panel-head">
      <h2>Scenario page failed to load data</h2>
      <div class="muted">Fix: use the local server URL (not file://)</div>
    </div>
    <div style="padding:14px">
      <div style="font-weight:900; margin-bottom:8px">${message}</div>
      <div class="muted" style="white-space:pre-wrap">${details}</div>
      <div class="muted" style="margin-top:10px">
        Run:
        <code>python scripts/serve_dashboard.py --port 0 --dir frontend</code>
        and open the printed <code>http://127.0.0.1:PORT/scenarios.html</code> URL.
      </div>
    </div>
  `;
  if (container) container.prepend(panel);
}

function fmtINR(n) {
  const x = Number(n);
  if (!Number.isFinite(x)) return "—";
  return x.toLocaleString("en-IN", { maximumFractionDigits: 0 });
}
function fmtFloat(n, digits = 2) {
  const x = Number(n);
  if (!Number.isFinite(x)) return "—";
  return x.toFixed(digits);
}

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else node.setAttribute(k, v);
  }
  for (const c of children) node.appendChild(c);
  return node;
}

function card(label, value, hint = "") {
  const c = el("div", { class: "card" });
  c.appendChild(el("div", { class: "label", text: label }));
  c.appendChild(el("div", { class: "value", text: value }));
  if (hint) c.appendChild(el("div", { class: "hint", text: hint }));
  return c;
}

const DASHBOARD_CACHE_KEY = "dashboard_data_cache";
const DASHBOARD_CACHE_TIMESTAMP_KEY = "dashboard_data_timestamp";

async function loadDashboard(forceRefresh = false) {
  if (window.location.protocol === "file:") {
    throw new Error(
      "You are opening the page via file://. Browsers block fetch() to local JSON in this mode. Please open via the local server (http://127.0.0.1:PORT)."
    );
  }
  
  // Check cache first (unless force refresh)
  if (!forceRefresh) {
    try {
      const cached = sessionStorage.getItem(DASHBOARD_CACHE_KEY);
      const cachedTime = sessionStorage.getItem(DASHBOARD_CACHE_TIMESTAMP_KEY);
      if (cached && cachedTime) {
        const data = JSON.parse(cached);
        // Cache is valid for 5 minutes
        const age = Date.now() - Number(cachedTime);
        if (age < 5 * 60 * 1000) {
          console.log("Using cached dashboard data");
          return data;
        }
      }
    } catch (e) {
      console.warn("Cache read failed, fetching fresh:", e);
    }
  }
  
  // Fetch fresh data
  const res = await fetch(`${DASHBOARD_JSON_URL}?t=${Date.now()}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to load ${DASHBOARD_JSON_URL}: ${res.status}`);
  const data = await res.json();
  
  // Cache it
  try {
    sessionStorage.setItem(DASHBOARD_CACHE_KEY, JSON.stringify(data));
    sessionStorage.setItem(DASHBOARD_CACHE_TIMESTAMP_KEY, String(Date.now()));
  } catch (e) {
    console.warn("Cache write failed:", e);
  }
  
  return data;
}

function getInputs() {
  const takeRate = Number(document.getElementById("takeRate").value) / 100; // per month
  const approvalOverride = Number(document.getElementById("approvalOverride").value) / 100;
  const useActualApproval = Boolean(document.getElementById("useActualApproval").checked);
  const utilization = Number(document.getElementById("utilization").value) / 100;
  const termWeeks = Math.max(1, Number(document.getElementById("termWeeks").value));
  const apr = Number(document.getElementById("apr").value) / 100;
  const cof = Number(document.getElementById("cof").value) / 100;
  const pd = Number(document.getElementById("pd").value) / 100;
  const lgd = Number(document.getElementById("lgd").value) / 100;
  const opex = Number(document.getElementById("opex").value);
  const refFee = Number(document.getElementById("refFee").value);
  const revShare = Number(document.getElementById("revShare").value) / 100;

  const futureRiders = Math.max(0, Number(document.getElementById("futureRiders").value));
  const futureApproval = Math.max(0, Math.min(1, Number(document.getElementById("futureApproval").value) / 100));
  const months = Math.max(1, Number(document.getElementById("months").value));
  const monthlyGrowth = Math.max(0, Number(document.getElementById("monthlyGrowth").value) / 100);

  return {
    takeRate,
    approvalOverride,
    useActualApproval,
    utilization,
    termWeeks,
    apr,
    cof,
    pd,
    lgd,
    opex,
    refFee,
    revShare,
    futureRiders,
    futureApproval,
    months,
    monthlyGrowth,
  };
}

function inferBaseFromOffers(offers) {
  const total = offers.length;
  const approved = offers.filter((o) => Number(o.eligible) === 1);
  const approvedCount = approved.length;
  const approvalRate = total ? approvedCount / total : 0;
  const avgLimit = approvedCount ? approved.reduce((s, o) => s + Number(o.recommended_limit || 0), 0) / approvedCount : 0;
  return { total, approvedCount, approvalRate, avgLimit };
}

function econForMonth({
  mode,
  riders,
  approvalRate,
  avgLimit,
  takeRate,
  utilization,
  termWeeks,
  apr,
  cof,
  pd,
  lgd,
  opexPerAdvance,
  refFee,
  revShare,
}) {
  const approved = riders * approvalRate;
  const advances = approved * takeRate;
  const principal = advances * avgLimit * utilization;

  // For 3PL: weekly working-capital freed is the weekly disbursal shifted off balance sheet.
  const WEEKS_PER_MONTH = 52 / 12; // ~4.3333
  const wcFreedWeekly = principal / WEEKS_PER_MONTH;

  const termYears = termWeeks / 52;
  const interest = principal * apr * termYears; // simple interest over term
  const funding = principal * cof * termYears;
  const expectedLoss = principal * pd * lgd;
  const opex = advances * opexPerAdvance;

  let revenue = 0;
  if (mode === "salary_advance_lender") {
    revenue = interest;
  } else {
    revenue = advances * refFee + (revShare * interest);
  }

  const net = revenue - funding - expectedLoss - opex;

  return {
    riders,
    approved,
    advances,
    principal,
    wcFreedWeekly,
    revenue,
    funding,
    expectedLoss,
    opex,
    net,
  };
}

function renderCards(containerId, stats, labelOverrides = {}, mode = "") {
  const c = document.getElementById(containerId);
  const label = (k, fallback) => labelOverrides[k] || fallback;
  const cards = [
    card(label("riders", "Riders"), `${fmtINR(stats.riders)}`),
    card(label("approved", "Approved"), `${fmtINR(stats.approved)}`, `Approval ${fmtFloat((stats.approved / Math.max(1, stats.riders)) * 100, 1)}%`),
    card("Advances / month", `${fmtFloat(stats.advances, 1)}`, `Take-rate applied`),
    card("Disbursed (₹)", `₹${fmtINR(stats.principal)}`, `Utilization applied`),
  ];

  if (mode === "3pl_operator") {
    cards.push(card("WC freed / week (₹)", `₹${fmtINR(stats.wcFreedWeekly)}`, "Weekly disbursal shifted off balance sheet"));
  }

  cards.push(
    card("Revenue (₹)", `₹${fmtINR(stats.revenue)}`),
    card("COF (₹)", `₹${fmtINR(stats.funding)}`),
    card("Expected loss (₹)", `₹${fmtINR(stats.expectedLoss)}`, `PD×LGD`),
    card("Net P&L (₹)", `₹${fmtINR(stats.net)}`)
  );
  c.replaceChildren(...cards);
}

function renderProjectionTable(rows) {
  const body = document.getElementById("projBody");
  body.replaceChildren();
  for (const r of rows) {
    const tr = document.createElement("tr");
    const cells = [
      r.month,
      fmtINR(r.riders),
      fmtINR(r.approved),
      fmtFloat(r.advances, 1),
      fmtINR(r.principal),
      fmtINR(r.wcFreedWeekly),
      fmtINR(r.revenue),
      fmtINR(r.funding),
      fmtINR(r.expectedLoss),
      fmtINR(r.opex),
      fmtINR(r.net),
    ];
    cells.forEach((v, i) => {
      const td = document.createElement("td");
      td.textContent = v;
      if (i >= 1) td.className = "num";
      tr.appendChild(td);
    });
    body.appendChild(tr);
  }
}

function computePresentAndFuture(state, inputs, base, approvalRatePresent) {
  const present = econForMonth({
    mode: state.mode,
    riders: base.total,
    approvalRate: approvalRatePresent,
    avgLimit: base.avgLimit,
    takeRate: inputs.takeRate,
    utilization: inputs.utilization,
    termWeeks: inputs.termWeeks,
    apr: inputs.apr,
    cof: inputs.cof,
    pd: inputs.pd,
    lgd: inputs.lgd,
    opexPerAdvance: inputs.opex,
    refFee: inputs.refFee,
    revShare: inputs.revShare,
  });

  const rows = [];
  let riders = inputs.futureRiders;
  for (let m = 1; m <= inputs.months; m++) {
    const stats = econForMonth({
      mode: state.mode,
      riders,
      approvalRate: inputs.futureApproval,
      avgLimit: base.avgLimit,
      takeRate: inputs.takeRate,
      utilization: inputs.utilization,
      termWeeks: inputs.termWeeks,
      apr: inputs.apr,
      cof: inputs.cof,
      pd: inputs.pd,
      lgd: inputs.lgd,
      opexPerAdvance: inputs.opex,
      refFee: inputs.refFee,
      revShare: inputs.revShare,
    });
    rows.push({ month: `M${m}`, ...stats });
    riders = riders * (1 + inputs.monthlyGrowth);
  }
  const futureLast = rows[rows.length - 1];
  return { present, futureLast };
}

function buildSensitivityRows(state, inputs, base, approvalRatePresent) {
  const basePF = computePresentAndFuture(state, inputs, base, approvalRatePresent);
  const basePresentNet = basePF.present.net;
  const baseFutureNet = basePF.futureLast.net;
  const baseWC = state.mode === "3pl_operator" ? basePF.present.wcFreedWeekly : 0;

  // Define low/high for each variable (one-at-a-time)
  const defs = [
    { key: "takeRate", label: "Take-rate (%/month)", unit: "%", low: Math.max(0, inputs.takeRate * 100 - 10), high: Math.min(100, inputs.takeRate * 100 + 10), apply: (v) => ({ ...inputs, takeRate: v / 100 }) },
    { key: "approvalRatePresent", label: "Approval rate present (%)", unit: "%", low: Math.max(0, approvalRatePresent * 100 - 5), high: Math.min(100, approvalRatePresent * 100 + 5), applyApproval: true },
    { key: "utilization", label: "Utilization (%)", unit: "%", low: Math.max(0, inputs.utilization * 100 - 10), high: Math.min(100, inputs.utilization * 100 + 10), apply: (v) => ({ ...inputs, utilization: v / 100 }) },
    { key: "termWeeks", label: "Term (weeks)", unit: "w", low: Math.max(1, inputs.termWeeks - 2), high: Math.min(24, inputs.termWeeks + 2), apply: (v) => ({ ...inputs, termWeeks: v }) },
    { key: "apr", label: "APR (%)", unit: "%", low: Math.max(0, inputs.apr * 100 - 5), high: Math.min(100, inputs.apr * 100 + 5), apply: (v) => ({ ...inputs, apr: v / 100 }) },
    { key: "cof", label: "COF (%)", unit: "%", low: Math.max(0, inputs.cof * 100 - 3), high: Math.min(100, inputs.cof * 100 + 3), apply: (v) => ({ ...inputs, cof: v / 100 }) },
    { key: "pd", label: "PD over term (%)", unit: "%", low: Math.max(0, inputs.pd * 100 - 1), high: Math.min(100, inputs.pd * 100 + 1), apply: (v) => ({ ...inputs, pd: v / 100 }) },
    { key: "lgd", label: "LGD (%)", unit: "%", low: Math.max(0, inputs.lgd * 100 - 5), high: Math.min(100, inputs.lgd * 100 + 5), apply: (v) => ({ ...inputs, lgd: v / 100 }) },
    { key: "opex", label: "OpEx per disbursal (₹)", unit: "₹", low: Math.max(0, inputs.opex - 10), high: inputs.opex + 10, apply: (v) => ({ ...inputs, opex: v }) },
    { key: "refFee", label: "3PL referral fee (₹)", unit: "₹", low: Math.max(0, inputs.refFee - 25), high: inputs.refFee + 25, apply: (v) => ({ ...inputs, refFee: v }) },
    { key: "revShare", label: "3PL rev-share (%)", unit: "%", low: Math.max(0, inputs.revShare * 100 - 5), high: Math.min(100, inputs.revShare * 100 + 5), apply: (v) => ({ ...inputs, revShare: v / 100 }) },
    { key: "futureRiders", label: "Future start riders (M1)", unit: "", low: Math.max(0, Math.round(inputs.futureRiders * 0.8)), high: Math.round(inputs.futureRiders * 1.2), apply: (v) => ({ ...inputs, futureRiders: v }) },
    { key: "futureApproval", label: "Future approval (%)", unit: "%", low: Math.max(0, inputs.futureApproval * 100 - 5), high: Math.min(100, inputs.futureApproval * 100 + 5), apply: (v) => ({ ...inputs, futureApproval: v / 100 }) },
    { key: "monthlyGrowth", label: "Monthly growth (%)", unit: "%", low: Math.max(0, inputs.monthlyGrowth * 100 - 2), high: inputs.monthlyGrowth * 100 + 2, apply: (v) => ({ ...inputs, monthlyGrowth: v / 100 }) },
  ];

  const rows = [];
  for (const d of defs) {
    const baseVal = d.applyApproval ? approvalRatePresent * 100 : (d.key === "termWeeks" ? inputs.termWeeks : (d.key === "opex" ? inputs.opex : (d.key === "futureRiders" ? inputs.futureRiders : (d.key === "monthlyGrowth" ? inputs.monthlyGrowth * 100 : (d.key === "futureApproval" ? inputs.futureApproval * 100 : (d.key === "refFee" ? inputs.refFee : (d.key === "revShare" ? inputs.revShare * 100 : (d.key === "pd" ? inputs.pd * 100 : (d.key === "lgd" ? inputs.lgd * 100 : (d.key === "cof" ? inputs.cof * 100 : (d.key === "apr" ? inputs.apr * 100 : (d.key === "utilization" ? inputs.utilization * 100 : inputs.takeRate * 100))))))))))));

    const lowInputs = d.applyApproval ? inputs : d.apply(d.low);
    const highInputs = d.applyApproval ? inputs : d.apply(d.high);

    const lowApproval = d.applyApproval ? d.low / 100 : approvalRatePresent;
    const highApproval = d.applyApproval ? d.high / 100 : approvalRatePresent;

    const lowPF = computePresentAndFuture(state, lowInputs, base, lowApproval);
    const highPF = computePresentAndFuture(state, highInputs, base, highApproval);

    const lowPresentNet = lowPF.present.net;
    const highPresentNet = highPF.present.net;
    const lowFutureNet = lowPF.futureLast.net;
    const highFutureNet = highPF.futureLast.net;

    const lowWC = state.mode === "3pl_operator" ? lowPF.present.wcFreedWeekly : 0;
    const highWC = state.mode === "3pl_operator" ? highPF.present.wcFreedWeekly : 0;

    rows.push({
      variable: d.label,
      low: d.low,
      base: baseVal,
      high: d.high,
      dLowPresent: lowPresentNet - basePresentNet,
      dHighPresent: highPresentNet - basePresentNet,
      dLowFuture: lowFutureNet - baseFutureNet,
      dHighFuture: highFutureNet - baseFutureNet,
      dLowWC: lowWC - baseWC,
      dHighWC: highWC - baseWC,
    });
  }
  return { basePresentNet, baseFutureNet, baseWC, rows };
}

function renderChips(basePresentNet, baseFutureNet, baseWC, mode) {
  const elChips = document.getElementById("sensChips");
  if (!elChips) return;
  const chips = [
    { k: "Present P&L", v: `₹${fmtINR(basePresentNet)}` },
    { k: "Future P&L", v: `₹${fmtINR(baseFutureNet)}` },
  ];
  if (mode === "3pl_operator") chips.push({ k: "WC / week", v: `₹${fmtINR(baseWC)}` });
  elChips.replaceChildren(
    ...chips.map((c) =>
      el("div", { class: "chip" }, [
        el("span", { text: c.k }),
        el("b", { text: c.v }),
      ])
    )
  );
}

function fmtDelta(n) {
  const x = Number(n);
  if (!Number.isFinite(x)) return { text: "—", cls: "delta-zero" };
  if (x === 0) return { text: "0", cls: "delta-zero" };
  const sign = x > 0 ? "+" : "−";
  return { text: `${sign}₹${fmtINR(Math.abs(x))}`, cls: x > 0 ? "delta-pos" : "delta-neg" };
}

function renderSensitivity(rows) {
  const body = document.getElementById("sensBody");
  if (!body) return;
  body.replaceChildren();

  for (const r of rows) {
    const tr = document.createElement("tr");
    // variable + range
    tr.appendChild(el("td", { text: r.variable }));
    tr.appendChild(el("td", { class: "num", text: String(Math.round(Number(r.low) || 0)).toLocaleString("en-IN") }));
    tr.appendChild(el("td", { class: "num", text: String(Math.round(Number(r.base) || 0)).toLocaleString("en-IN") }));
    tr.appendChild(el("td", { class: "num", text: String(Math.round(Number(r.high) || 0)).toLocaleString("en-IN") }));

    // deltas
    const d1 = fmtDelta(r.dLowPresent);
    const d2 = fmtDelta(r.dHighPresent);
    const d3 = fmtDelta(r.dLowFuture);
    const d4 = fmtDelta(r.dHighFuture);
    const d5 = fmtDelta(r.dLowWC);
    const d6 = fmtDelta(r.dHighWC);

    [d1, d2, d3, d4, d5, d6].forEach((d) => {
      const td = document.createElement("td");
      td.className = `num ${d.cls}`;
      td.textContent = d.text;
      tr.appendChild(td);
    });

    body.appendChild(tr);
  }
}

function wireTabs(state) {
  const tabs = document.querySelectorAll(".tab[data-mode]");
  tabs.forEach((btn) => {
    btn.addEventListener("click", () => {
      tabs.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.mode = btn.dataset.mode;
      recompute(state);
    });
  });

  const viewTabs = document.querySelectorAll(".tab[data-view]");
  viewTabs.forEach((btn) => {
    btn.addEventListener("click", () => {
      viewTabs.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.view = btn.dataset.view || "scenario";
      applyView(state);
      recompute(state);
    });
  });
}

function applyView(state) {
  const isSens = state.view === "sensitivity";
  const scenarioBlock = document.getElementById("scenarioBlock");
  const presentPanel = document.getElementById("presentPanel");
  const futurePanel = document.getElementById("futurePanel");
  const projectionPanel = document.getElementById("projectionPanel");
  const sensitivityPanel = document.getElementById("sensitivityPanel");
  if (scenarioBlock) scenarioBlock.classList.toggle("hidden", isSens);
  if (presentPanel) presentPanel.classList.toggle("hidden", isSens);
  if (futurePanel) futurePanel.classList.toggle("hidden", isSens);
  if (projectionPanel) projectionPanel.classList.toggle("hidden", isSens);
  if (sensitivityPanel) sensitivityPanel.classList.toggle("hidden", !isSens);
}

function recompute(state) {
  const inputs = getInputs();

  const offers = state.mode === "3pl_operator" ? state.data.tables.threepl_offers : state.data.tables.lender_offers;
  const base = inferBaseFromOffers(offers);
  const approvalRatePresent = inputs.useActualApproval
    ? base.approvalRate
    : Math.max(0, Math.min(1, Number.isFinite(inputs.approvalOverride) ? inputs.approvalOverride : base.approvalRate));

  // Keep the input in sync when Auto is enabled
  if (inputs.useActualApproval) {
    const v = Math.round(base.approvalRate * 100);
    const elA = document.getElementById("approvalOverride");
    if (elA && String(elA.value) !== String(v)) elA.value = String(v);
  }

  document.getElementById("presentMeta").textContent =
    `Based on current underwriting output: ${base.approvedCount}/${base.total} approved • ` +
    `avg limit ₹${fmtINR(base.avgLimit)} • ` +
    `approval used ${(approvalRatePresent * 100).toFixed(1)}%` +
    (inputs.useActualApproval ? " (auto)" : " (manual)");

  const present = econForMonth({
    mode: state.mode,
    riders: base.total,
    approvalRate: approvalRatePresent,
    avgLimit: base.avgLimit,
    takeRate: inputs.takeRate,
    utilization: inputs.utilization,
    termWeeks: inputs.termWeeks,
    apr: inputs.apr,
    cof: inputs.cof,
    pd: inputs.pd,
    lgd: inputs.lgd,
    opexPerAdvance: inputs.opex,
    refFee: inputs.refFee,
    revShare: inputs.revShare,
  });
  renderCards("presentCards", present, {}, state.mode);

  // Future: scale from user-defined future riders + approval, then apply growth
  const rows = [];
  let riders = inputs.futureRiders;
  for (let m = 1; m <= inputs.months; m++) {
    const stats = econForMonth({
      mode: state.mode,
      riders,
      approvalRate: inputs.futureApproval,
      avgLimit: base.avgLimit, // keep constant for now; later we can link to tier mix
      takeRate: inputs.takeRate,
      utilization: inputs.utilization,
      termWeeks: inputs.termWeeks,
      apr: inputs.apr,
      cof: inputs.cof,
      pd: inputs.pd,
      lgd: inputs.lgd,
      opexPerAdvance: inputs.opex,
      refFee: inputs.refFee,
      revShare: inputs.revShare,
    });
    rows.push({ month: `M${m}`, ...stats });
    riders = riders * (1 + inputs.monthlyGrowth);
  }
  renderProjectionTable(rows);

  const last = rows[rows.length - 1];
  renderCards(
    "futureCards",
    last,
    { riders: `Riders (M${inputs.months})`, approved: `Approved (M${inputs.months})` },
    state.mode
  );

  // sensitivity (only when view active)
  if (state.view === "sensitivity") {
    const sensSort = document.getElementById("sensSort");
    const sortKey = sensSort ? String(sensSort.value || "future_abs") : "future_abs";

    const sens = buildSensitivityRows(state, inputs, base, approvalRatePresent);
    renderChips(sens.basePresentNet, sens.baseFutureNet, sens.baseWC, state.mode);

    const rows = sens.rows.slice();
    const score = (r) => {
      const abs = (x) => Math.abs(Number(x) || 0);
      if (sortKey === "present_abs") return Math.max(abs(r.dLowPresent), abs(r.dHighPresent));
      if (sortKey === "wc_abs") return Math.max(abs(r.dLowWC), abs(r.dHighWC));
      return Math.max(abs(r.dLowFuture), abs(r.dHighFuture));
    };
    rows.sort((a, b) => score(b) - score(a));
    renderSensitivity(rows);
  }
}

async function main() {
  const state = { data: null, mode: "salary_advance_lender", view: "scenario" };
  try {
    const data = await loadDashboard();
    state.data = data;
    document.getElementById("generatedAt").textContent = `Data: ${data.generated_at}`;
    const reloadBtn = document.getElementById("reloadBtn");
    if (reloadBtn) {
      reloadBtn.addEventListener("click", async (e) => {
        e.preventDefault();
        const btn = e.target;
        const originalText = btn.textContent;
        btn.disabled = true;
        btn.textContent = "Reloading...";
        const statusPill = document.getElementById("generatedAt");
        const originalStatus = statusPill ? statusPill.textContent : "";
        if (statusPill) statusPill.textContent = "Reloading...";
        
        try {
          // Clear cache and force refresh
          sessionStorage.removeItem(DASHBOARD_CACHE_KEY);
          sessionStorage.removeItem(DASHBOARD_CACHE_TIMESTAMP_KEY);
          const data = await loadDashboard(true);
          state.data = data;
          if (statusPill) statusPill.textContent = `Data: ${data.generated_at} (refreshed)`;
          recompute(state);
        } catch (e) {
          console.error(e);
          if (statusPill) statusPill.textContent = originalStatus || "Load error";
          alert("Reload failed: " + (e?.message || String(e)));
        } finally {
          btn.disabled = false;
          btn.textContent = originalText;
        }
      });
    }

    wireTabs(state);
    applyView(state);
    const inputs = document.querySelectorAll("input");
    inputs.forEach((i) => i.addEventListener("input", () => recompute(state)));
    const sensSort = document.getElementById("sensSort");
    if (sensSort) sensSort.addEventListener("input", () => recompute(state));
    recompute(state);
  } catch (e) {
    console.error(e);
    showFatal("Scenario page load failed.", e?.message || String(e));
  }
}

main();


