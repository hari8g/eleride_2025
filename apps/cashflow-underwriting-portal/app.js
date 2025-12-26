const DASHBOARD_JSON_URL = "data/dashboard.json";

function showFatal(message, details = "") {
  const pill = document.getElementById("generatedAt");
  if (pill) pill.textContent = "Load error";

  const container = document.querySelector(".container");
  const panel = document.createElement("section");
  panel.className = "panel";
  panel.innerHTML = `
    <div class="panel-head">
      <h2>Frontend failed to load data</h2>
      <div class="muted">Fix: use the local server URL (not file://)</div>
    </div>
    <div style="padding:14px">
      <div style="font-weight:900; margin-bottom:8px">${message}</div>
      <div class="muted" style="white-space:pre-wrap">${details}</div>
      <div class="muted" style="margin-top:10px">
        If you opened this file directly, run:
        <code>python scripts/serve_dashboard.py --port 0 --dir frontend</code>
        and open the printed <code>http://127.0.0.1:PORT</code> URL.
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

function pickFirst(arr) {
  if (!Array.isArray(arr) || arr.length === 0) return null;
  return arr[0];
}

function card(label, value, hint = "") {
  const c = el("div", { class: "card" });
  c.appendChild(el("div", { class: "label", text: label }));
  c.appendChild(el("div", { class: "value", text: value }));
  if (hint) c.appendChild(el("div", { class: "hint", text: hint }));
  return c;
}

function badgeEligible(v) {
  const ok = String(v) === "1" || v === 1 || v === true;
  return el("span", { class: `badge ${ok ? "good" : "bad"}`, text: ok ? "YES" : "NO" });
}

function badgeTier(t) {
  const tier = String(t || "").toUpperCase();
  const cls = tier === "A" ? "tierA" : tier === "B" ? "tierB" : tier === "C" ? "tierC" : "tierD";
  return el("span", { class: `badge ${cls}`, text: tier || "—" });
}

function sanitizeText(s) {
  return String(s ?? "").toLowerCase().trim();
}

function drawSparkline(canvas, points) {
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  const values = points
    .map((p) => Number(p.net_payout))
    .filter((v) => Number.isFinite(v));
  if (values.length < 2) {
    ctx.fillStyle = "rgba(0,0,0,0.6)";
    ctx.font = "bold 16px ui-sans-serif, system-ui";
    ctx.textAlign = "center";
    ctx.fillText("Not enough history", w / 2, h / 2);
    return;
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min;
  
  // Padding: left (for Y-axis labels), right, top, bottom (for X-axis labels)
  const padLeft = 70;
  const padRight = 20;
  const padTop = 30;
  const padBottom = 50;
  const chartW = w - padLeft - padRight;
  const chartH = h - padTop - padBottom;
  const chartX = padLeft;
  const chartY = padTop;

  const xStep = chartW / (values.length - 1);
  const yScale = range > 0 ? chartH / range : 0;

  // Helper to get Y position
  const getY = (val) => chartY + chartH - (val - min) * yScale;

  // Background
  ctx.fillStyle = "rgba(249, 250, 251, 1)";
  ctx.fillRect(chartX, chartY, chartW, chartH);

  // Grid lines (horizontal - for Y-axis)
  const yTicks = 5;
  ctx.strokeStyle = "rgba(0,0,0,0.1)";
  ctx.lineWidth = 1;
  ctx.setLineDash([2, 2]);
  for (let i = 0; i <= yTicks; i++) {
    const yVal = min + (range * i) / yTicks;
    const y = getY(yVal);
    ctx.beginPath();
    ctx.moveTo(chartX, y);
    ctx.lineTo(chartX + chartW, y);
    ctx.stroke();
  }
  ctx.setLineDash([]);

  // Grid lines (vertical - for X-axis, every 4th point or so)
  const xTickInterval = Math.max(1, Math.floor(values.length / 8));
  ctx.strokeStyle = "rgba(0,0,0,0.05)";
  for (let i = 0; i < values.length; i += xTickInterval) {
    const x = chartX + i * xStep;
    ctx.beginPath();
    ctx.moveTo(x, chartY);
    ctx.lineTo(x, chartY + chartH);
    ctx.stroke();
  }

  // Y-axis labels (₹ amounts)
  ctx.fillStyle = "rgba(0,0,0,0.7)";
  ctx.font = "11px ui-sans-serif, system-ui";
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  for (let i = 0; i <= yTicks; i++) {
    const yVal = min + (range * i) / yTicks;
    const y = getY(yVal);
    ctx.fillText(`₹${fmtINR(yVal)}`, chartX - 10, y);
  }

  // X-axis labels (week labels)
  ctx.fillStyle = "rgba(0,0,0,0.7)";
  ctx.font = "10px ui-sans-serif, system-ui";
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  const labelInterval = Math.max(1, Math.floor(values.length / 10));
  for (let i = 0; i < values.length; i += labelInterval) {
    const x = chartX + i * xStep;
    const point = points[i];
    let label = "";
    if (point.week_id) label = String(point.week_id);
    else if (point.year && point.month && point.week) {
      label = `${point.year}-${String(point.month).padStart(2, "0")}-W${point.week}`;
    } else {
      label = `W${i + 1}`;
    }
    ctx.fillText(label, x, chartY + chartH + 8);
  }

  // Axes lines
  ctx.strokeStyle = "rgba(0,0,0,0.3)";
  ctx.lineWidth = 2;
  // X-axis
  ctx.beginPath();
  ctx.moveTo(chartX, chartY + chartH);
  ctx.lineTo(chartX + chartW, chartY + chartH);
  ctx.stroke();
  // Y-axis
  ctx.beginPath();
  ctx.moveTo(chartX, chartY);
  ctx.lineTo(chartX, chartY + chartH);
  ctx.stroke();

  // Main line
  ctx.strokeStyle = "rgba(37, 99, 235, 0.9)";
  ctx.lineWidth = 3;
  ctx.beginPath();
  for (let i = 0; i < values.length; i++) {
    const x = chartX + i * xStep;
    const y = getY(values[i]);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();

  // Data points
  for (let i = 0; i < values.length; i++) {
    const x = chartX + i * xStep;
    const y = getY(values[i]);
    ctx.fillStyle = i === values.length - 1 ? "rgba(124, 92, 255, 1)" : "rgba(37, 99, 235, 0.8)";
    ctx.beginPath();
    ctx.arc(x, y, i === values.length - 1 ? 5 : 3, 0, Math.PI * 2);
    ctx.fill();
    // White border for last point
    if (i === values.length - 1) {
      ctx.strokeStyle = "rgba(255,255,255,0.9)";
      ctx.lineWidth = 2;
      ctx.stroke();
    }
  }

  // Title/Summary at top
  ctx.fillStyle = "rgba(0,0,0,0.8)";
  ctx.font = "bold 13px ui-sans-serif, system-ui";
  ctx.textAlign = "left";
  ctx.textBaseline = "top";
  ctx.fillText(`Net payout over ${values.length} weeks`, chartX, 8);
  
  ctx.fillStyle = "rgba(0,0,0,0.6)";
  ctx.font = "11px ui-sans-serif, system-ui";
  ctx.fillText(`Min: ₹${fmtINR(min)} • Max: ₹${fmtINR(max)} • Latest: ₹${fmtINR(values[values.length - 1])}`, chartX, 24);
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

function buildPortfolioUI(data) {
  const lender = pickFirst(data.portfolio?.lender) || {};
  const threepl = pickFirst(data.portfolio?.threepl) || {};
  const wc = pickFirst(data.portfolio?.threepl_working_capital) || {};

  function tierCard(p, tier) {
    const c = Number(p[`tier_${tier}_count`] || 0);
    const ead = Number(p[`tier_${tier}_ead_sum`] || 0);
    const pdTerm = Number(p[`tier_${tier}_pd_term`] || 0);
    const lgd = Number(p[`tier_${tier}_lgd`] || 0);
    const elSum = Number(p[`tier_${tier}_expected_loss_sum`] || 0);
    return card(
      `Tier ${tier}`,
      `${fmtINR(c)} riders`,
      `EAD ₹${fmtINR(ead)} • PD ${fmtFloat(pdTerm * 100, 1)}% • LGD ${fmtFloat(lgd * 100, 0)}% • EL ₹${fmtINR(elSum)}`
    );
  }

  const lenderCards = document.getElementById("portfolioCards");
  lenderCards.replaceChildren(
    card("Approved riders", `${lender.riders_approved ?? "—"} / ${lender.riders_total ?? "—"}`, `Approval rate ${fmtFloat((lender.approval_rate ?? 0) * 100, 1)}%`),
    card("Exposure (₹)", `₹${fmtINR(lender.gross_exposure_sum)}`, `Avg ticket ₹${fmtINR(lender.avg_ticket)}`),
    card(
      "Deduction share",
      `${fmtFloat((lender.deduction_share_weighted_of_forecast ?? 0) * 100, 1)}%`,
      `p50 ${fmtFloat((lender.deduction_pct_forecast_p50 ?? 0) * 100, 1)}% • p90 ${fmtFloat((lender.deduction_pct_forecast_p90 ?? 0) * 100, 1)}%`
    ),
    card("Expected loss (₹)", `₹${fmtINR(lender.expected_loss_sum)}`, `EL rate ${fmtFloat((lender.expected_loss_rate ?? 0) * 100, 2)}%`),
    tierCard(lender, "A"),
    tierCard(lender, "B"),
    tierCard(lender, "C")
  );

  // Lender cost stack (required yield + implied APR)
  const csWrap = document.getElementById("lenderCostStack");
  const csCards = document.getElementById("lenderCostCards");
  const csCoc = document.getElementById("csCoc");
  const csOps = document.getElementById("csOps");
  const csMargin = document.getElementById("csMargin");

  const isLenderTabActive = !document.getElementById("portfolioCards").classList.contains("hidden");
  if (csWrap) csWrap.classList.toggle("hidden", !isLenderTabActive);

  function readNum(el, def) {
    const v = Number(el?.value);
    return Number.isFinite(v) ? v : def;
  }

  const cocPct = readNum(csCoc, 14) / 100;
  const opsPerDisbursal = readNum(csOps, 40);
  const marginPct = readNum(csMargin, 5) / 100;

  const ead = Number(lender.gross_exposure_sum || 0);
  const elSum = Number(lender.expected_loss_sum || 0);
  const elRateTerm = ead > 0 ? elSum / ead : 0;
  const termYears = Number(lender.term_years_mean || 0) || (Number(lender.repayment_weeks_mean || 4) / 52);
  const annualize = (termRate) => (termYears > 0 ? termRate / termYears : 0);

  const elAnnual = annualize(elRateTerm);
  const opsTotal = Number(lender.riders_approved || 0) * opsPerDisbursal;
  const opsRateTerm = ead > 0 ? opsTotal / ead : 0;
  const opsAnnual = annualize(opsRateTerm);

  const requiredApr = cocPct + elAnnual + opsAnnual + marginPct;
  const currentApr = Number(lender.apr_weighted_by_ead || 0);

  if (csCards) {
    csCards.replaceChildren(
      card("Term (avg)", `${fmtFloat((Number(lender.repayment_weeks_mean || 0)), 1)} w`, `${fmtFloat(termYears * 12, 2)} months avg`),
      card("COC (annual)", `${fmtFloat(cocPct * 100, 1)}%`, "Cost of capital"),
      card("Expected loss (annual)", `${fmtFloat(elAnnual * 100, 1)}%`, `Term EL ${fmtFloat(elRateTerm * 100, 2)}%`),
      card("Ops + CAC (annual)", `${fmtFloat(opsAnnual * 100, 1)}%`, `₹${fmtINR(opsTotal)} total`),
      card("Margin (annual)", `${fmtFloat(marginPct * 100, 1)}%`, "Target margin"),
      card("Required APR", `${fmtFloat(requiredApr * 100, 1)}%`, "APR needed to hit required yield"),
      card("Current APR (weighted)", `${fmtFloat(currentApr * 100, 1)}%`, "From offer book (weighted by EAD)")
    );
  }

  const threeplCards = document.getElementById("threeplCards");
  threeplCards.replaceChildren(
    card("Approved riders", `${threepl.riders_approved ?? "—"} / ${threepl.riders_total ?? "—"}`, `Approval rate ${fmtFloat((threepl.approval_rate ?? 0) * 100, 1)}%`),
    card("Weekly WC freed (₹)", `₹${fmtINR(wc.working_capital_freed_estimate)}`, `Assume take-rate ${(wc.assumption_take_rate ?? 0) * 100}%`),
    card(
      "Deduction share",
      `${fmtFloat((threepl.deduction_share_weighted_of_forecast ?? 0) * 100, 1)}%`,
      `p50 ${fmtFloat((threepl.deduction_pct_forecast_p50 ?? 0) * 100, 1)}% • p90 ${fmtFloat((threepl.deduction_pct_forecast_p90 ?? 0) * 100, 1)}%`
    ),
    card("Weekly referral fees (₹)", `₹${fmtINR(wc.expected_weekly_referral_fee)}`, `Fee/advance ₹${fmtINR(wc.assumption_referral_fee_per_advance)}`),
    card("Interest rev-share (₹)", `₹${fmtINR(wc.expected_interest_revenue_share_term)}`, `Rev share ${(wc.assumption_revenue_share_of_interest ?? 0) * 100}%`),
    tierCard(threepl, "A"),
    tierCard(threepl, "B"),
    tierCard(threepl, "C")
  );
}

function getOffers(data, mode) {
  if (mode === "threepl") return data.tables?.threepl_offers || [];
  return data.tables?.lender_offers || [];
}

function renderOffersTable(data, mode, filters) {
  const offers = getOffers(data, mode);
  const body = document.getElementById("offersBody");
  const rowCount = document.getElementById("rowCount");

  const search = sanitizeText(filters.search);
  const tier = (filters.tier || "").toUpperCase();
  const eligible = filters.eligible;
  const minLimit = Number(filters.minLimit || 0);

  const filtered = offers.filter((o) => {
    const okTier = !tier || String(o.risk_tier || "").toUpperCase() === tier;
    const okElig = eligible === "" || String(o.eligible) === String(eligible);
    const okLimit = !Number.isFinite(minLimit) || Number(o.recommended_limit || 0) >= minLimit;
    if (!(okTier && okElig && okLimit)) return false;

    if (!search) return true;
    const hay =
      `${o.cee_name ?? ""} ${o.cee_id ?? ""} ${o.rider_id ?? ""} ${o.pan ?? ""} ${o.city ?? ""}`.toLowerCase();
    return hay.includes(search);
  });

  filtered.sort((a, b) => Number(b.recommended_limit || 0) - Number(a.recommended_limit || 0));

  body.replaceChildren();
  for (const o of filtered) {
    const tr = document.createElement("tr");
    tr.appendChild(el("td", {}, [badgeEligible(o.eligible)]));
    tr.appendChild(el("td", {}, [badgeTier(o.risk_tier)]));
    tr.appendChild(el("td", { text: o.cee_name || "—" }));
    tr.appendChild(el("td", { text: String(o.cee_id ?? "—") }));
    tr.appendChild(el("td", { text: o.city || "—" }));
    tr.appendChild(el("td", { class: "num", text: fmtINR(o.recommended_limit) }));
    tr.appendChild(el("td", { class: "num", text: fmtINR(o.recommended_weekly_deduction) }));
    tr.appendChild(
      el("td", {
        class: "num",
        text: `${fmtFloat((Number(o.deduction_pct_of_forecast_payout || 0)) * 100, 1)}%`,
      })
    );
    tr.appendChild(el("td", { class: "num", text: fmtINR(o.payout_forecast_weekly) }));
    tr.appendChild(el("td", { class: "num", text: fmtFloat(o.net_payout_cv, 2) }));
    tr.appendChild(el("td", { class: "num", text: fmtINR(o.active_weeks_worked) }));

    tr.addEventListener("click", () => openRiderDialog(data, o));
    body.appendChild(tr);
  }

  rowCount.textContent = `${filtered.length} riders shown (of ${offers.length})`;
}

function openRiderDialog(data, offer) {
  const dlg = document.getElementById("riderDialog");
  const title = document.getElementById("dlgTitle");
  const sub = document.getElementById("dlgSubtitle");
  const kv = document.getElementById("dlgOffer");
  const spark = document.getElementById("spark");
  const meta = document.getElementById("sparkMeta");

  title.textContent = offer.cee_name || "Rider";
  sub.textContent = `cee_id ${offer.cee_id ?? "—"} • tier ${offer.risk_tier ?? "—"} • eligible ${offer.eligible}`;

  const rows = [
    ["Recommended limit (₹)", `₹${fmtINR(offer.recommended_limit)}`],
    ["Weekly deduction (₹)", `₹${fmtINR(offer.recommended_weekly_deduction)}`],
    ["Deduction % (of forecast payout)", `${fmtFloat((Number(offer.deduction_pct_of_forecast_payout || 0)) * 100, 1)}%`],
    ["Deduction % (of mean payout)", `${fmtFloat((Number(offer.deduction_pct_of_mean_payout || 0)) * 100, 1)}%`],
    ["Forecast payout/wk (₹)", `₹${fmtINR(offer.payout_forecast_weekly)}`],
    ["APR", `${fmtFloat((offer.apr ?? 0) * 100, 1)}%`],
    ["Active weeks", `${offer.active_weeks_worked ?? "—"}`],
    ["Current streak (weeks)", `${offer.current_consecutive_active_weeks ?? "—"}`],
    ["Volatility (CV)", `${fmtFloat(offer.net_payout_cv, 2)}`],
    ["Cancel rate", `${fmtFloat((offer.cancel_rate ?? 0) * 100, 2)}%`],
    ["Decline reasons", offer.decline_reasons || "—"],
  ];
  kv.replaceChildren(
    ...rows.map(([k, v]) =>
      el("div", { class: "kv-row" }, [el("div", { class: "kv-k", text: k }), el("div", { class: "kv-v", text: v })])
    )
  );

  const series = data.series?.rider_week?.[String(offer.rider_key)] || [];
  drawSparkline(spark, series);
  const last = series.length ? series[series.length - 1].week_id : "—";
  meta.textContent = `Weeks: ${series.length} • Latest: ${last}`;

  dlg.showModal();
}

function wireUI(state) {
  // portfolio tabs
  const portTabs = document.querySelectorAll(".panel .tab[data-tab]");
  portTabs.forEach((btn) => {
    btn.addEventListener("click", () => {
      portTabs.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const tab = btn.dataset.tab;
      document.getElementById("portfolioCards").classList.toggle("hidden", tab !== "lender");
      document.getElementById("threeplCards").classList.toggle("hidden", tab !== "threepl");
      document.getElementById("lenderCostStack").classList.toggle("hidden", tab !== "lender");
    });
  });

  // offer tabs
  const offerTabs = document.querySelectorAll(".panel .tab[data-offers]");
  offerTabs.forEach((btn) => {
    btn.addEventListener("click", () => {
      offerTabs.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.offersMode = btn.dataset.offers;
      renderOffersTable(state.data, state.offersMode, state.filters);
    });
  });

  // filters
  const search = document.getElementById("search");
  const tier = document.getElementById("tier");
  const eligible = document.getElementById("eligible");
  const minLimit = document.getElementById("minLimit");
  const clearBtn = document.getElementById("clearBtn");

  function applyFilters() {
    state.filters = {
      search: search.value,
      tier: tier.value,
      eligible: eligible.value,
      minLimit: minLimit.value,
    };
    renderOffersTable(state.data, state.offersMode, state.filters);
  }
  [search, tier, eligible, minLimit].forEach((x) => x.addEventListener("input", applyFilters));
  clearBtn.addEventListener("click", () => {
    search.value = "";
    tier.value = "";
    eligible.value = "";
    minLimit.value = "";
    applyFilters();
  });

  // dialog close
  const dlg = document.getElementById("riderDialog");
  document.getElementById("dlgClose").addEventListener("click", () => dlg.close());
  dlg.addEventListener("click", (e) => {
    const rect = dlg.getBoundingClientRect();
    const inDialog = rect.top <= e.clientY && e.clientY <= rect.bottom && rect.left <= e.clientX && e.clientX <= rect.right;
    if (!inDialog) dlg.close();
  });

  // reload
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
        buildPortfolioUI(data);
        renderOffersTable(data, state.offersMode, state.filters);
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


  // cost stack inputs: recompute cards on change
  ["csCoc", "csOps", "csMargin"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("input", () => buildPortfolioUI(state.data));
  });
}

async function main() {
  const state = { data: null, offersMode: "lender", filters: {} };
  try {
    const data = await loadDashboard();
    state.data = data;
    document.getElementById("generatedAt").textContent = `Data: ${data.generated_at}`;
    buildPortfolioUI(data);
    wireUI(state);
    renderOffersTable(data, state.offersMode, state.filters);
  } catch (e) {
    console.error(e);
    showFatal("Dashboard load failed.", e?.message || String(e));
  }
}

main();


