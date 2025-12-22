import React, { useEffect, useMemo, useState } from "react";
import { api, HttpError, LessorDashboard, LessorRole } from "../lib/api";
import { clearSession, loadSession, saveSession } from "../lib/session";
import logoPng from "../assets/eleride-logo.png";

type Tab = "portfolio" | "partners";

function MethodTip({ lines }: { lines: string[] }) {
  const [open, setOpen] = useState(false);
  return (
    <span
      className="tip"
      data-open={open ? "1" : "0"}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        className="tipBtn"
        aria-label="Buyback method"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        onBlur={() => setOpen(false)}
      >
        i
      </button>
      <div className="tipBody" role="tooltip">
        <div style={{ fontWeight: 1000, marginBottom: 6 }}>Buyback method (3 years)</div>
        <ul className="tipList">
          {lines.map((x) => (
            <li key={x}>{x}</li>
          ))}
        </ul>
      </div>
    </span>
  );
}

function clamp01(x: number) {
  return Math.max(0, Math.min(1, x));
}

function HBar({
  label,
  valueLabel,
  pct,
  tone,
}: {
  label: string;
  valueLabel: string;
  pct: number;
  tone: "ok" | "warn" | "bad";
}) {
  return (
    <div className="hbar">
      <div className="hbarTop">
        <div className="hbarLabel">{label}</div>
        <div className="hbarValue">{valueLabel}</div>
      </div>
      <div className="hbarTrack">
        <div className={`hbarFill hbarFill-${tone}`} style={{ width: `${Math.round(clamp01(pct) * 100)}%` }} />
      </div>
    </div>
  );
}

function StackBar({
  items,
}: {
  items: { label: string; pct: number; tone: "ok" | "warn" | "bad" | "neutral" }[];
}) {
  return (
    <div className="stackBar">
      {items.map((x) => (
        <div
          key={x.label}
          className={`stackBarSeg stackBarSeg-${x.tone}`}
          style={{ width: `${Math.round(clamp01(x.pct) * 100)}%` }}
          title={`${x.label}: ${Math.round(clamp01(x.pct) * 100)}%`}
        />
      ))}
    </div>
  );
}

function Donut({
  segments,
}: {
  segments: { label: string; pct: number; tone: "ok" | "warn" | "bad" }[];
}) {
  const r = 40;
  const c = 2 * Math.PI * r;
  let offset = 0;
  return (
    <svg width="110" height="110" viewBox="0 0 110 110" className="donut">
      <circle cx="55" cy="55" r={r} fill="none" stroke="rgba(15,23,42,0.08)" strokeWidth="12" />
      {segments.map((s) => {
        const dash = clamp01(s.pct) * c;
        const dashArr = `${dash} ${c - dash}`;
        const el = (
          <circle
            key={s.label}
            cx="55"
            cy="55"
            r={r}
            fill="none"
            className={`donutSeg donutSeg-${s.tone}`}
            strokeWidth="12"
            strokeDasharray={dashArr}
            strokeDashoffset={-offset}
            strokeLinecap="butt"
          />
        );
        offset += dash;
        return el;
      })}
      <circle cx="55" cy="55" r="28" fill="white" opacity="0.95" />
    </svg>
  );
}

function AssuranceCurve({
  total,
  label,
}: {
  total: number;
  label: string;
}) {
  // Simple, product-style “assurance” curve: 0 → total over 36 months.
  // Not a market forecast; just a visual to communicate the 3y underwriting output.
  const w = 360;
  const h = 120;
  const pad = 10;
  const x0 = pad;
  const y0 = h - pad;
  const x1 = w - pad;
  const yTop = pad;

  const pts = [
    { m: 0, v: 0 },
    { m: 12, v: total * 0.35 },
    { m: 24, v: total * 0.7 },
    { m: 36, v: total },
  ];
  const toX = (m: number) => x0 + (m / 36) * (x1 - x0);
  const toY = (v: number) => y0 - (v / Math.max(1, total)) * (y0 - yTop);
  const d = `M ${toX(pts[0].m)} ${toY(pts[0].v)} ` + pts.slice(1).map((p) => `L ${toX(p.m)} ${toY(p.v)}`).join(" ");
  const area =
    `M ${toX(pts[0].m)} ${y0} ` +
    pts.map((p) => `L ${toX(p.m)} ${toY(p.v)}`).join(" ") +
    ` L ${toX(pts[pts.length - 1].m)} ${y0} Z`;

  return (
    <div className="curve">
      <div className="curveTop">
        <div className="curveLabel">{label}</div>
      </div>
      <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} className="curveSvg">
        <path d={area} className="curveArea" />
        <path d={d} className="curveLine" />
        <circle cx={toX(36)} cy={toY(total)} r="4.5" className="curveDot" />

        {/* axis ticks */}
        {[0, 12, 24, 36].map((m) => (
          <g key={m}>
            <line x1={toX(m)} y1={y0} x2={toX(m)} y2={y0 + 4} stroke="rgba(15,23,42,0.20)" strokeWidth="1" />
            <text x={toX(m)} y={h - 1} textAnchor="middle" fontSize="10" fill="rgba(102,112,133,1)">
              {m}m
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}

function safeMsg(e: unknown): string {
  if (e instanceof HttpError) {
    const body = e.body as any;
    const detail = body?.detail;
    if (typeof detail === "string") return detail;
    if (detail?.code) return `${detail.code}`;
    return `Request failed (${e.status}).`;
  }
  return (e as any)?.message ? String((e as any).message) : String(e);
}

function canSeed(role: LessorRole) {
  return role === "OWNER" || role === "ANALYST";
}

function money(n: number | null | undefined) {
  if (n == null) return "—";
  return `₹${Math.round(n).toLocaleString("en-IN")}`;
}

export function FinancingPortalApp() {
  const [sess, setSess] = useState(() => loadSession());
  const [tab, setTab] = useState<Tab>("portfolio");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // auth form
  const [mode, setMode] = useState<"signup" | "login">("login");
  const [phone, setPhone] = useState<string>(() => sess?.user_phone ?? "+919999000601");
  const [lessorName, setLessorName] = useState<string>("Eleride Leasing");
  const [lessorSlug, setLessorSlug] = useState<string>("eleride-leasing");
  const [otpRequestId, setOtpRequestId] = useState<string>("");
  const [otp, setOtp] = useState<string>("");
  const [devOtp, setDevOtp] = useState<string>("");

  // data
  const [dash, setDash] = useState<LessorDashboard | null>(null);
  const [partnerFocus, setPartnerFocus] = useState<string>("ALL");

  const buybackMethodLines = useMemo(
    () => [
      "Per vehicle cap: buyback ≤ 30% of purchase price (never higher).",
      "Maintenance discount: 2% per open ticket (max 10%).",
      "Battery discount: <20% → 5%, <40% → 2%.",
      "Usage discount: projected 3-year odometer >30k adds discount (up to 15%).",
      "Total discount capped at 25%. Portfolio/partner totals are sums across vehicles.",
    ],
    []
  );

  async function run(fn: () => Promise<void>) {
    setError(null);
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      setError(safeMsg(e));
    } finally {
      setBusy(false);
    }
  }

  function signOut() {
    clearSession();
    setSess(null);
    setTab("portfolio");
    setDash(null);
    setPartnerFocus("ALL");
    setOtpRequestId("");
    setOtp("");
    setDevOtp("");
  }

  async function refreshAll() {
    if (!sess?.token) return;
    const [d] = await Promise.all([api.dashboard(sess.token)]);
    setDash(d);
  }

  useEffect(() => {
    if (!sess?.token) return;
    refreshAll().catch(() => null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sess?.token]);

  if (!sess?.token) {
    return (
      <div className="authShell">
        <div className="card authCard stack">
          <div className="authLogoRow">
            <img className="authLogo" src={logoPng} alt="Eleride" />
          </div>
          <div>
            <div className="title">Financing Portal</div>
            <div className="helper">Track leased vehicles across fleet partners, performance, and buy-back underwriting exposure.</div>
          </div>

          {error ? <div className="error">{error}</div> : null}

          <div className="row">
            <button className={`btn ${mode === "login" ? "btnPrimary" : ""}`} onClick={() => setMode("login")}>
              Login
            </button>
            <button className={`btn ${mode === "signup" ? "btnPrimary" : ""}`} onClick={() => setMode("signup")}>
              Create tenant
            </button>
          </div>

          <div className="grid2">
            <div>
              <label>Phone</label>
              <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+919999000601" />
              <div className="helper">OTP-based access (dev OTP shown in dev env).</div>
            </div>
            <div>
              <label>Lessor slug</label>
              <input value={lessorSlug} onChange={(e) => setLessorSlug(e.target.value)} disabled={mode === "signup"} />
              <div className="helper">{mode === "login" ? "Required to choose tenant." : "Derived from name."}</div>
            </div>
          </div>

          {mode === "signup" ? (
            <div>
              <label>Lessor name</label>
              <input value={lessorName} onChange={(e) => setLessorName(e.target.value)} placeholder="Eleride Leasing" />
              <div className="helper">Tip: create with slug <b>eleride-leasing</b> for demo consistency.</div>
            </div>
          ) : null}

          <button
            className="btn btnPrimary"
            disabled={busy}
            onClick={() =>
              run(async () => {
                const r = await api.otpRequest({
                  phone: phone.trim(),
                  mode,
                  lessor_name: mode === "signup" ? lessorName.trim() : undefined,
                  lessor_slug: mode === "login" ? lessorSlug.trim() : undefined,
                });
                setOtpRequestId(r.request_id);
                setDevOtp((r as any).dev_otp ?? "");
              })
            }
          >
            {busy ? "Sending…" : "Send OTP"}
          </button>

          {otpRequestId ? (
            <div className="card stack" style={{ boxShadow: "none" }}>
              <div className="grid2">
                <div>
                  <label>OTP</label>
                  <input value={otp} onChange={(e) => setOtp(e.target.value)} placeholder="6-digit OTP" />
                  {devOtp ? <div className="helper">Dev OTP: {devOtp}</div> : null}
                </div>
                <div className="helper">
                  After verify, you’ll land in a portfolio view showing partners, leased fleet, and buyback estimates.
                </div>
              </div>
              <button
                className="btn btnPrimary"
                disabled={busy || otp.trim().length < 4}
                onClick={() =>
                  run(async () => {
                    const s = await api.otpVerify({ request_id: otpRequestId, otp: otp.trim() });
                    const next = {
                      token: s.access_token,
                      lessor_id: s.lessor_id,
                      lessor_name: s.lessor_name,
                      lessor_slug: s.lessor_slug,
                      user_phone: s.user_phone,
                      role: s.role,
                    } as const;
                    saveSession(next);
                    setSess(next);
                    setOtpRequestId("");
                    setOtp("");
                    setDevOtp("");
                    setTab("portfolio");
                  })
                }
              >
                {busy ? "Verifying…" : "Verify & Enter portal"}
              </button>
            </div>
          ) : null}
        </div>
      </div>
    );
  }

  const partners = dash?.partners ?? [];
  const maxLeased = Math.max(1, ...partners.map((p) => p.vehicles_leased));
  const partnerIds = useMemo(() => ["ALL", ...partners.map((p) => p.operator_id)], [partners]);
  const focusedPartners = useMemo(() => {
    if (partnerFocus === "ALL") return partners;
    return partners.filter((p) => p.operator_id === partnerFocus);
  }, [partners, partnerFocus]);

  // IMPORTANT: Topline values should follow the currently selected partner filter.
  // When partnerFocus === "ALL", it represents the full portfolio. Otherwise, it is scoped to that partner.
  const scopeLabel = partnerFocus === "ALL" ? "All partners" : partnerFocus;
  const scopedPartners = focusedPartners;
  const scopedBuybackTotal = useMemo(
    () => scopedPartners.reduce((a, p) => a + (p.est_buyback_value_inr || 0), 0),
    [scopedPartners],
  );
  const scopedLeasedTotal = useMemo(
    () => scopedPartners.reduce((a, p) => a + (p.vehicles_leased || 0), 0),
    [scopedPartners],
  );
  const scopedValuedTotal = useMemo(
    () => scopedPartners.reduce((a, p) => a + (p.vehicles_valued || 0), 0),
    [scopedPartners],
  );
  const scopedFleetActive = useMemo(
    () => scopedPartners.reduce((a, p) => a + (p.fleet_vehicles_active || 0), 0),
    [scopedPartners],
  );
  const scopedAvgBuybackPerValuedVehicle = scopedValuedTotal > 0 ? scopedBuybackTotal / scopedValuedTotal : 0;

  function riskBadge(p: any) {
    // Very rough underwriting proxy (frontend-only):
    // - maintenance ratio high => higher risk
    // - low battery count high => higher risk
    const denom = p.vehicles_leased > 0 ? p.vehicles_leased : 1;
    const maintRatio = p.fleet_open_tickets != null ? p.fleet_open_tickets / denom : 0;
    const lowBattRatio = p.fleet_low_battery != null ? p.fleet_low_battery / denom : 0;
    const score = maintRatio * 0.7 + lowBattRatio * 0.3;
    if (score >= 0.22) return { label: "High risk", cls: "statusPill stMaint" };
    if (score >= 0.10) return { label: "Medium risk", cls: "statusPill stOther" };
    return { label: "Low risk", cls: "statusPill stActive" };
  }

  const portfolioHealth = useMemo(() => {
    const leased = scopedPartners.reduce((a, p) => a + (p.vehicles_leased || 0), 0);
    // Covered/leased-subset health signals (derived from leased vehicles only)
    const active = scopedPartners.reduce((a, p) => a + (p.leased_vehicles_active || 0), 0);
    const maint = scopedPartners.reduce((a, p) => a + (p.leased_vehicles_in_maintenance || 0), 0);
    const lowBatt = scopedPartners.reduce((a, p) => a + (p.leased_low_battery || 0), 0);
    const inactive = Math.max(0, leased - active);
    const den = Math.max(1, leased);
    return {
      leased,
      active,
      maint,
      lowBatt,
      inactive,
      segs: [
        { label: "Active", pct: active / den, tone: "ok" as const },
        { label: "Maintenance", pct: maint / den, tone: "warn" as const },
        { label: "Low battery", pct: lowBatt / den, tone: "bad" as const },
        { label: "Other", pct: Math.max(0, 1 - (active + maint + lowBatt) / den), tone: "neutral" as const },
      ],
    };
  }, [scopedPartners]);

  const riskMix = useMemo(() => {
    const buckets: Record<"Low risk" | "Medium risk" | "High risk", { count: number; buyback: number; tone: "ok" | "warn" | "bad" }> =
      {
        "Low risk": { count: 0, buyback: 0, tone: "ok" },
        "Medium risk": { count: 0, buyback: 0, tone: "warn" },
        "High risk": { count: 0, buyback: 0, tone: "bad" },
      };
    for (const p of scopedPartners) {
      const r = riskBadge(p).label as "Low risk" | "Medium risk" | "High risk";
      buckets[r].count += 1;
      buckets[r].buyback += p.est_buyback_value_inr || 0;
    }
    const total = Math.max(1, scopedPartners.length);
    return {
      totalPartners: scopedPartners.length,
      segments: (Object.keys(buckets) as (keyof typeof buckets)[]).map((k) => ({
        label: k,
        pct: buckets[k].count / total,
        tone: buckets[k].tone,
        count: buckets[k].count,
        buyback: buckets[k].buyback,
      })),
    };
  }, [scopedPartners]);

  const buybackExposure = useMemo(() => {
    const sorted = [...scopedPartners].sort((a, b) => (b.est_buyback_value_inr || 0) - (a.est_buyback_value_inr || 0));
    const max = Math.max(1, ...sorted.map((p) => p.est_buyback_value_inr || 0));
    return { sorted, max };
  }, [scopedPartners]);

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <img className="brandLogo" src={logoPng} alt="Eleride" />
          <div>Financing Portal</div>
        </div>
        <div className="brandSub">
          Tenant: <b>{sess.lessor_slug}</b>
          <div>Role: {sess.role}</div>
        </div>

        <div className="nav">
          <button className={`navBtn ${tab === "portfolio" ? "navBtnActive" : ""}`} onClick={() => setTab("portfolio")}>
            Portfolio
          </button>
          <button className={`navBtn ${tab === "partners" ? "navBtnActive" : ""}`} onClick={() => setTab("partners")}>
            Fleet partners
          </button>
        </div>

        <div style={{ marginTop: 18 }} className="stack">
          <button className="btn" disabled={busy} onClick={() => run(refreshAll)}>
            Refresh
          </button>
          <button
            className="btn btnPrimary"
            disabled={busy || !canSeed(sess.role)}
            onClick={() =>
              run(async () => {
                const r = await api.seedDemo(sess.token, 10);
                await refreshAll();
                setError(`Seeded demo leases. Vehicles created: ${r.vehicles_created}`);
              })
            }
          >
            Seed demo portfolio
          </button>
          <button className="btn btnDanger" onClick={signOut}>
            Sign out
          </button>
        </div>
      </aside>

      <main className="main">
        <div className="topbar">
          <div>
            <div className="title">
              {tab === "portfolio" ? "Portfolio overview" : "Fleet partner underwriting"}
            </div>
            <div className="helper">{sess.lessor_name}</div>
          </div>
          <div className="row">
            <div className="pill">{sess.user_phone}</div>
            <div className="pill">API: {api.base}</div>
          </div>
        </div>

        {error ? <div className="error">{error}</div> : null}

        {tab === "portfolio" ? (
          <div className="stack">
            <div className="kpiRow">
              <div className="kpi">
                <div className="kpiValue">{dash ? scopedLeasedTotal : "—"}</div>
                <div className="kpiLabel">Vehicles leased (scope)</div>
              </div>
              <div className="kpi">
                <div className="kpiValue">{dash ? scopedFleetActive : "—"}</div>
                <div className="kpiLabel">Active (fleet, scope)</div>
              </div>
              <div className="kpi">
                <div className="kpiValue">{money(scopedBuybackTotal || null)}</div>
                <div className="kpiLabel kpiLabelRow">
                  Estimated buyback (3 years, scope: {scopeLabel}) <MethodTip lines={buybackMethodLines} />
                </div>
              </div>
            </div>

            <div className="card stack">
              <div className="row" style={{ justifyContent: "space-between" }}>
                <div style={{ fontWeight: 1000 }}>Partner distribution</div>
                <div className="pill">{partners.length} partners</div>
              </div>
              <div className="barRow">
                {partners.map((p) => (
                  <div key={p.operator_id} className="barItem">
                    <div className="barTop">
                      <div>
                        <div className="barName">{p.operator_id}</div>
                        <div className="helper">
                          Fleet: {p.fleet_vehicles_active} active • {p.fleet_open_tickets} open tickets • avg batt {p.fleet_avg_battery_pct ?? "—"}%
                        </div>
                      </div>
                      <div className="tag">{p.vehicles_leased} vehicles</div>
                      <div className="tag">{money(p.est_buyback_value_inr)}</div>
                    </div>
                    <div className="barTrack">
                      <div className="barFill" style={{ width: `${Math.round((p.vehicles_leased / maxLeased) * 100)}%` }} />
                    </div>
                  </div>
                ))}
                {partners.length === 0 ? <div className="helper">No data yet. Click “Seed demo portfolio”.</div> : null}
              </div>
            </div>

            <div className="grid2">
              <div className="card stack">
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <div style={{ fontWeight: 1000 }}>Value offering (buyback assurance)</div>
                  <div className="row">
                    <div className="pill">Scope: {scopeLabel}</div>
                    <div className="row">
                      <div className="helper">Filter:</div>
                      <select value={partnerFocus} onChange={(e) => setPartnerFocus(e.target.value)}>
                        {partnerIds.map((p) => (
                          <option key={p} value={p}>
                            {p === "ALL" ? "All partners" : p}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                </div>
                <div className="helper">
                  Communicate outcome, not complexity: portfolio buyback value at 3 years with a hard 30% cap per vehicle, discounted by fleet health.
                </div>
                <AssuranceCurve
                  total={scopedBuybackTotal}
                  label={`Assured buyback at 36 months (${scopeLabel}): ${money(scopedBuybackTotal)}`}
                />
                <div className="divider" />
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <div style={{ fontWeight: 1000 }}>Portfolio health mix</div>
                  <div className="pill">{portfolioHealth.leased} vehicles</div>
                </div>
                <StackBar items={portfolioHealth.segs} />
                <div className="legendRow">
                  <span className="legendItem legendItem-ok">Active</span>
                  <span className="legendItem legendItem-warn">Maintenance</span>
                  <span className="legendItem legendItem-bad">Low battery</span>
                  <span className="legendItem legendItem-neutral">Other</span>
                </div>
              </div>

              <div className="card stack">
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <div style={{ fontWeight: 1000 }}>Exposure view</div>
                  <div className="pill">By partner buyback</div>
                </div>
                <div className="helper">Shows where buyback assurance is concentrated across partners (tone = risk badge).</div>
                <div className="chartGrid2">
                  <div className="cardMini stack" style={{ boxShadow: "none" }}>
                    <div className="row" style={{ justifyContent: "space-between" }}>
                      <div style={{ fontWeight: 1000 }}>Risk mix</div>
                      <div className="pill">{riskMix.totalPartners} partners</div>
                    </div>
                    <div className="donutRow">
                      <Donut segments={riskMix.segments.map((s) => ({ label: s.label, pct: s.pct, tone: s.tone }))} />
                      <div className="donutLegend">
                        {riskMix.segments.map((s) => (
                          <div key={s.label} className="donutLegendItem">
                            <span className={`dot dot-${s.tone}`} />
                            <div>
                              <div style={{ fontWeight: 1000 }}>{s.label}</div>
                              <div className="helper">
                                {s.count} partners • {money(s.buyback)}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="cardMini stack" style={{ boxShadow: "none" }}>
                    <div className="row" style={{ justifyContent: "space-between" }}>
                      <div style={{ fontWeight: 1000 }}>Top partner exposure</div>
                      <div className="pill">relative</div>
                    </div>
                    <div className="hbarList">
                      {buybackExposure.sorted.slice(0, 6).map((p) => {
                        const r = riskBadge(p).label;
                        const tone = r === "High risk" ? "bad" : r === "Medium risk" ? "warn" : "ok";
                        return (
                          <HBar
                            key={p.operator_id}
                            label={p.operator_id}
                            valueLabel={money(p.est_buyback_value_inr)}
                            pct={(p.est_buyback_value_inr || 0) / buybackExposure.max}
                            tone={tone}
                          />
                        );
                      })}
                      {partners.length === 0 ? <div className="helper">Seed demo portfolio to see charts.</div> : null}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        ) : null}

        {tab === "partners" ? (
          <div className="stack">
            <div className="card stack">
              <div className="row" style={{ justifyContent: "space-between" }}>
                <div style={{ fontWeight: 1000 }}>Buyback assurance (scope underwriting)</div>
                <div className="pill">{scopeLabel}</div>
              </div>
              <div className="kpiRow">
                <div className="kpi">
                  <div className="kpiValue">{money(scopedBuybackTotal)}</div>
                  <div className="kpiLabel kpiLabelRow">
                    Estimated buyback (3 years, scope: {scopeLabel}) <MethodTip lines={buybackMethodLines} />
                  </div>
                </div>
                <div className="kpi">
                  <div className="kpiValue">{dash ? scopedLeasedTotal : "—"}</div>
                  <div className="kpiLabel">Vehicles leased (scope)</div>
                </div>
                <div className="kpi">
                  <div className="kpiValue">{money(scopedAvgBuybackPerValuedVehicle || null)}</div>
                  <div className="kpiLabel">Avg buyback / valued vehicle</div>
                  {dash ? (
                    <div className="helper">
                      Valued: {scopedValuedTotal} • Unpriced: {Math.max(0, scopedLeasedTotal - scopedValuedTotal)}
                    </div>
                  ) : null}
                </div>
              </div>

              <div className="divider" />
              <div className="row" style={{ justifyContent: "space-between" }}>
                <div style={{ fontWeight: 1000 }}>Partner focus</div>
                <div className="row">
                  <div className="helper">Filter:</div>
                  <select value={partnerFocus} onChange={(e) => setPartnerFocus(e.target.value)}>
                    {partnerIds.map((p) => (
                      <option key={p} value={p}>
                        {p === "ALL" ? "All partners" : p}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            </div>

            <div className="card stack">
              <div className="row" style={{ justifyContent: "space-between" }}>
                <div style={{ fontWeight: 1000 }}>Partner underwriting view</div>
                <div className="pill">3y buyback is capped at ≤30% of purchase price</div>
              </div>

              <table className="table">
                <thead>
                  <tr>
                    <th>Partner</th>
                    <th>Risk</th>
                    <th>Leased</th>
                    <th title="Active leases with a current vehicle snapshot (used for buyback valuation)">Valued</th>
                        <th>Active (fleet)</th>
                        <th>Open tickets</th>
                    <th>Low batt</th>
                    <th>Avg batt</th>
                    <th>Est buyback (3y, cap 30%)</th>
                  </tr>
                </thead>
                <tbody>
                  {focusedPartners.map((p) => {
                    const r = riskBadge(p);
                    return (
                      <tr key={p.operator_id}>
                        <td style={{ fontWeight: 1000 }}>{p.operator_id}</td>
                        <td>
                          <span className={r.cls}>{r.label}</span>
                        </td>
                        <td>{p.vehicles_leased}</td>
                        <td title={`Unpriced leases: ${Math.max(0, (p.vehicles_leased || 0) - (p.vehicles_valued || 0))}`}>
                          {p.vehicles_valued}
                        </td>
                        <td title="Total active vehicles in the fleet (operator portal)">{p.fleet_vehicles_active}</td>
                        <td title="Vehicles with at least one OPEN maintenance ticket (operator portal)">{p.fleet_open_tickets}</td>
                        <td>{p.fleet_low_battery}</td>
                        <td>{p.fleet_avg_battery_pct ?? "—"}%</td>
                        <td style={{ fontWeight: 1000 }}>{money(p.est_buyback_value_inr)}</td>
                      </tr>
                    );
                  })}
                  {partners.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="helper">
                        No partner data yet. Click “Seed demo portfolio”.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}
      </main>
    </div>
  );
}


