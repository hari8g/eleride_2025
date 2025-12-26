function byId(id) {
  return document.getElementById(id);
}

function setStatus(msg) {
  const pill = byId("statusPill");
  if (pill) pill.textContent = msg;
}

function fmtINR(n) {
  const x = Number(n);
  if (!Number.isFinite(x)) return "—";
  return x.toLocaleString("en-IN", { maximumFractionDigits: 0 });
}

function fmtPct(x, digits = 1) {
  const v = Number(x);
  if (!Number.isFinite(v)) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}

// CloudFront API URL (has valid SSL certificate)
const CLOUDFRONT_API_URL = "https://drqx7mgr0iu9c.cloudfront.net";

// Determine API base URL
function getApiBaseUrl() {
  // If running locally, use localhost
  if (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") {
    return "http://localhost:18080";
  }
  // Use CloudFront domain directly (has valid SSL)
  // This avoids SSL certificate issues with custom domain
  return CLOUDFRONT_API_URL;
}

async function api(path) {
  if (window.location.protocol === "file:") {
    throw new Error("Open via the local server URL, not file://");
  }
  const apiBase = getApiBaseUrl();
  const fullPath = apiBase ? `${apiBase}${path}` : `${CLOUDFRONT_API_URL}${path}`;
  
  // Use the API base URL (which is CloudFront with valid SSL)
  let lastError = null;
  const urlsToTry = [fullPath];
  
  for (const url of urlsToTry) {
    try {
      const res = await fetch(url, { cache: "no-store" });
      if (!res.ok) {
        if (res.status === 404) {
          lastError = new Error(`API endpoint not found: ${path}. The payslips feature requires a backend server. Please run the local server or deploy the backend API.`);
          continue;
        }
        lastError = new Error(`${path} failed: ${res.status} ${res.statusText}`);
        continue;
      }
      const contentType = res.headers.get("content-type");
      if (!contentType || !contentType.includes("application/json")) {
        lastError = new Error(`Expected JSON response from ${path}, got ${contentType || "unknown content type"}`);
        continue;
      }
      const text = await res.text();
      if (!text || text.trim() === "") {
        lastError = new Error(`Empty response from ${path}`);
        continue;
      }
      try {
        return JSON.parse(text);
      } catch (parseError) {
        lastError = new Error(`Invalid JSON response from ${path}: ${parseError.message}. Response: ${text.substring(0, 200)}`);
        continue;
      }
    } catch (fetchError) {
      // Network error (DNS failure, timeout, etc.) - try next URL
      lastError = fetchError;
      continue;
    }
  }
  
  // All URLs failed
  throw lastError || new Error(`Failed to connect to API. Tried: ${urlsToTry.join(", ")}`);
}

function option(value, label) {
  const o = document.createElement("option");
  o.value = value;
  o.textContent = label;
  return o;
}

function pill(cls, label, value) {
  return `<span class="pill2 ${cls}"><strong>${label}</strong> ${value}</span>`;
}

function clamp01(x) {
  const v = Number(x);
  if (!Number.isFinite(v)) return 0;
  return Math.max(0, Math.min(1, v));
}

function renderPayslip(p) {
  const el = byId("payslipView");
  const meta = byId("payslipMeta");
  if (!el) return;
  if (!p) {
    el.textContent = "";
    return;
  }

  const id = p.identity || {};
  const ops = p.ops || {};
  const pay = p.pay || {};

  if (meta) meta.textContent = `${id.period || ""} • cee_id ${id.cee_id || ""}`;

  const net = Number(pay.net_payout || 0);
  const gross = Number(pay.gross_earnings_est || 0);
  const deductions = Number(pay.deductions_amount || 0) + Number(pay.management_fee || 0) + Number(pay.gst || 0);

  const delivered = Number(ops.delivered_orders || 0);
  const cancelled = Number(ops.cancelled_orders || 0);
  const attendance = Number(ops.attendance || 0);
  const weekday = Number(ops.weekday_orders || 0);
  const weekend = Number(ops.weekend_orders || 0);
  const totalOrders = Math.max(0, delivered + cancelled);
  const cancelRate = totalOrders > 0 ? cancelled / totalOrders : 0;
  const weekendShare = (weekday + weekend) > 0 ? weekend / (weekday + weekend) : 0;

  const basePay = Number(pay.base_pay || 0);
  const incPay = Number(pay.incentive_total || 0);
  const arrearsPay = Number(pay.arrears_amount || 0);
  const fees = Number(pay.deductions_amount || 0) + Number(pay.management_fee || 0) + Number(pay.gst || 0);
  const totalForBar = Math.max(1, basePay + incPay + arrearsPay + Math.max(0, fees));
  const wBase = (basePay / totalForBar) * 100;
  const wInc = (incPay / totalForBar) * 100;
  const wArr = (arrearsPay / totalForBar) * 100;
  const wFees = (Math.max(0, fees) / totalForBar) * 100;

  // Gamified badges (simple, explainable heuristics)
  const badges = [];
  if (delivered >= 200) badges.push(pill("good", "Top Performer", "200+ deliveries"));
  else if (delivered >= 120) badges.push(pill("good", "Strong Week", "120+ deliveries"));
  else badges.push(pill("", "Deliveries", `${fmtINR(delivered)}`));

  if (attendance >= 6) badges.push(pill("good", "Consistency", `${fmtINR(attendance)} days worked`));
  else if (attendance >= 4) badges.push(pill("warn", "Regular", `${fmtINR(attendance)} days worked`));
  else badges.push(pill("warn", "Low days", `${fmtINR(attendance)} days`));

  if (weekendShare >= 0.35) badges.push(pill("good", "Weekend Warrior", fmtPct(weekendShare)));
  else badges.push(pill("", "Weekend share", fmtPct(weekendShare)));

  if (cancelRate <= 0.02) badges.push(pill("good", "Clean Ops", `cancel ${fmtPct(cancelRate)}`));
  else if (cancelRate <= 0.06) badges.push(pill("warn", "Watchlist", `cancel ${fmtPct(cancelRate)}`));
  else badges.push(pill("bad", "High cancels", `cancel ${fmtPct(cancelRate)}`));

  el.innerHTML = `
    <div class="payslip">
      <div class="payslip-hero">
        <div>
          <div class="payslip-brand">
            <img src="assets/eleride-logo.png" alt="eleRide" />
            <div>
              <div class="b1">Payslip</div>
              <div class="b2">System generated • INR (₹)</div>
            </div>
          </div>
          <div class="h-title" style="margin-top:10px">${id.cee_name ?? "—"}</div>
          <div class="h-sub">Period: <b>${id.period || "—"}</b> • Rider ID: <b>${id.cee_id || "—"}</b> • City: <b>${id.city || "—"}</b></div>
          <div class="h-sub">Mode: <b>${id.delivery_mode ?? "—"}</b> • Store: <b>${id.store ?? "—"}</b> • Provider: <b>${id.lmd_provider ?? "—"}</b></div>
          <div class="badge-row">${badges.join("")}</div>
        </div>
        <div class="chip">System generated</div>
      </div>

      <div class="kpi-row">
        <div class="kpi good">
          <div class="k">Net payout (₹)</div>
          <div class="v">₹${fmtINR(net)}</div>
        </div>
        <div class="kpi">
          <div class="k">Gross earnings (₹)</div>
          <div class="v">₹${fmtINR(gross)}</div>
        </div>
        <div class="kpi bad">
          <div class="k">Deductions + fees + GST (₹)</div>
          <div class="v">₹${fmtINR(deductions)}</div>
        </div>
        <div class="kpi">
          <div class="k">Delivered orders</div>
          <div class="v">${fmtINR(delivered)}</div>
        </div>
      </div>

      <!-- Removed long text columns (Rider details / Operations) in favor of gamified badges + KPI tiles -->
      <div class="kpi-row">
        <div class="kpi">
          <div class="k">Attendance (days)</div>
          <div class="v">${fmtINR(attendance)}</div>
        </div>
        <div class="kpi">
          <div class="k">Weekend share</div>
          <div class="v">${fmtPct(weekendShare)}</div>
        </div>
        <div class="kpi">
          <div class="k">Cancel rate</div>
          <div class="v">${fmtPct(cancelRate)}</div>
        </div>
        <div class="kpi">
          <div class="k">Distance (km)</div>
          <div class="v">${Number(ops.distance || 0).toFixed(2)}</div>
        </div>
      </div>

      <div class="callout">
        <h3>Payout breakdown</h3>
        <div class="muted">Visual split of earnings vs fees (all values in INR ₹).</div>
        <div class="bar" style="margin-top:10px">
          <div class="seg base" style="width:${wBase}%"></div>
          <div class="seg inc" style="width:${wInc}%"></div>
          <div class="seg arrears" style="width:${wArr}%"></div>
          <div class="seg fees" style="width:${wFees}%"></div>
        </div>
        <div class="legend">
          <span class="lg"><span class="sw base"></span>Base</span>
          <span class="lg"><span class="sw inc"></span>Incentives</span>
          <span class="lg"><span class="sw arrears"></span>Arrears</span>
          <span class="lg"><span class="sw fees"></span>Fees/GST</span>
        </div>
        <div class="table-wrap">
          <table class="table" style="min-width: 640px;">
            <thead>
              <tr>
                <th>Component</th>
                <th class="num">Amount (₹)</th>
              </tr>
            </thead>
            <tbody>
              <tr><td>Base pay</td><td class="num">₹${fmtINR(basePay)}</td></tr>
              <tr><td>Incentives</td><td class="num">₹${fmtINR(incPay)}</td></tr>
              <tr><td>Arrears</td><td class="num">₹${fmtINR(arrearsPay)}</td></tr>
              <tr><td><b>Gross earnings (est.)</b></td><td class="num"><b>${fmtINR(pay.gross_earnings_est)}</b></td></tr>
              <tr><td>Deductions</td><td class="num">₹${fmtINR(pay.deductions_amount)}</td></tr>
              <tr><td>Management fee</td><td class="num">₹${fmtINR(pay.management_fee)}</td></tr>
              <tr><td>GST</td><td class="num">₹${fmtINR(pay.gst)}</td></tr>
              <tr><td><b>Net payout</b></td><td class="num"><b>₹${fmtINR(pay.net_payout)}</b></td></tr>
            </tbody>
          </table>
        </div>
        <div class="muted" style="margin-top:10px">Generated by Cashflow Underwriting Engine • System generated.</div>
      </div>

      <div class="footer-card">
        <div style="display: flex; align-items: center; gap: 12px;">
          <img src="assets/eleride-logo.png" alt="eleRide" style="height: 32px; width: auto; border-radius: 8px;" />
          <div>
            <div class="msg">Thank you for riding with eleRide.</div>
            <div class="sub">
              This payslip is generated from the weekly payout system. If you find any discrepancy, please contact your fleet manager with Rider ID <b>${id.cee_id || "—"}</b>.
            </div>
          </div>
        </div>
        <div class="mark">₹</div>
      </div>
    </div>
  `;
}

function showError(message) {
  const errorContainer = byId("errorContainer");
  const errorMessage = byId("errorMessage");
  const loadingIndicator = byId("loadingIndicator");
  const mainContent = byId("mainContent");
  
  if (errorContainer) errorContainer.style.display = "block";
  if (errorMessage) errorMessage.textContent = message;
  if (loadingIndicator) loadingIndicator.style.display = "none";
  if (mainContent) mainContent.style.display = "none";
  
  console.error("Payslips error:", message);
}

function showMainContent() {
  const loadingIndicator = byId("loadingIndicator");
  const mainContent = byId("mainContent");
  const errorContainer = byId("errorContainer");
  
  if (loadingIndicator) loadingIndicator.style.display = "none";
  if (errorContainer) errorContainer.style.display = "none";
  if (mainContent) mainContent.style.display = "block";
}

async function main() {
  console.log("Main function started");
  
  try {
    // Check if required elements exist
    const fileSel = byId("fileSel");
    const riderSel = byId("riderSel");
    const pdfBtn = byId("pdfBtn");
    const reloadBtn = byId("reloadBtn");

    if (!fileSel || !riderSel) {
      throw new Error("Required HTML elements not found. Check if payslips.html is loaded correctly.");
    }

    console.log("HTML elements found:", { fileSel: !!fileSel, riderSel: !!riderSel, pdfBtn: !!pdfBtn, reloadBtn: !!reloadBtn });

    reloadBtn?.addEventListener("click", () => window.location.reload());

    setStatus("Loading files…");
    console.log("Status set to: Loading files…");
    
    let files;
    try {
      files = await api("/api/data-files");
    } catch (e) {
      console.error("Failed to load files:", e);
      const errorMsg = `Failed to load files from API: ${e.message || String(e)}`;
      showError(errorMsg);
      setStatus("API unavailable");
      return;
    }
  const list = files.files || [];
  fileSel.replaceChildren(...list.map((f) => option(f, f)));
  
  // Show main content once files are loaded
  showMainContent();
  console.log("Main content displayed");

  let currentFile = ""; // Track current file to detect changes

  async function loadRiders() {
    const file = fileSel.value;
    
    // Skip if same file selected
    if (file === currentFile && riderSel.options.length > 0) {
      return;
    }
    
    currentFile = file;
    
    if (!file) {
      riderSel.replaceChildren();
      renderPayslip(null);
      setStatus("No file selected");
      return;
    }
    
    // Clear current state immediately
    riderSel.replaceChildren();
    renderPayslip(null);
    setStatus("Loading riders…");
    
    try {
      const data = await api(`/api/riders?file=${encodeURIComponent(file)}`);
      const riders = data.riders || [];
      
      // Update rider dropdown
      riderSel.replaceChildren(
        ...riders.map((r) => option(String(r.cee_id), `${r.cee_id} — ${r.cee_name || ""}`.trim()))
      );
      
      // Auto-select first rider and load payslip
      if (riders.length > 0) {
        riderSel.value = String(riders[0].cee_id);
        await loadPayslip();
      } else {
        renderPayslip(null);
        setStatus("No riders found in file");
      }
    } catch (e) {
      console.error("Failed to load riders:", e);
      setStatus("Error loading riders");
      renderPayslip(null);
      alert("Failed to load riders: " + (e?.message || String(e)));
    }
  }

  async function loadPayslip() {
    const file = fileSel.value;
    const ceeId = riderSel.value;
    if (!file || !ceeId) {
      renderPayslip(null);
      return;
    }
    setStatus("Loading payslip…");
    try {
      const p = await api(`/api/payslip?file=${encodeURIComponent(file)}&cee_id=${encodeURIComponent(ceeId)}`);
      renderPayslip(p);
      setStatus("Ready");
    } catch (e) {
      console.error("Failed to load payslip:", e);
      setStatus("Error loading payslip");
      renderPayslip(null);
      alert("Failed to load payslip: " + (e?.message || String(e)));
    }
  }

  pdfBtn.addEventListener("click", () => {
    const file = fileSel.value;
    const ceeId = riderSel.value;
    if (!file || !ceeId) {
      alert("Please select a file and rider first");
      return;
    }
    const url = `/api/payslip.pdf?file=${encodeURIComponent(file)}&cee_id=${encodeURIComponent(ceeId)}`;
    window.location.href = url;
  });

  // Use 'change' event for select elements (more reliable than 'input')
  fileSel.addEventListener("change", () => {
    console.log("File changed to:", fileSel.value);
    loadRiders();
  });
  riderSel.addEventListener("change", () => {
    console.log("Rider changed to:", riderSel.value);
    loadPayslip();
  });

    if (list.length) await loadRiders();
    else {
      setStatus("No .xlsx found in Data/");
      renderPayslip(null);
    }
  } catch (e) {
    console.error("Main function error:", e);
    showError(`Error: ${e?.message || String(e)}`);
    setStatus("Error");
  }
}

// Debug logging at the end (after all functions are defined)
console.log("Payslips.js loaded");
console.log("API Base URL:", getApiBaseUrl());
console.log("CloudFront URL:", CLOUDFRONT_API_URL);

// Initialize the application
main().catch((e) => {
  console.error("Unhandled error in main():", e);
  showError(`Unhandled error: ${e?.message || String(e)}`);
});
