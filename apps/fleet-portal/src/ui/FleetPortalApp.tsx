import React, { useEffect, useMemo, useState } from "react";
import { api, HttpError, InboxDetail, InboxItem, Maintenance, OperatorRole, Vehicle } from "../lib/api";
import { clearSession, loadSession, saveSession } from "../lib/session";
import logoPng from "../assets/eleride-logo.png";

type Tab = "portfolio" | "inbox" | "vehicles" | "vehicle";

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

function tagClassForState(s: string) {
  if (s === "ONBOARDED") return "tag tagOk";
  if (s === "CONTACTED") return "tag tagWarn";
  if (s === "REJECTED") return "tag tagBad";
  return "tag";
}

function buildOsmEmbed(lat: number, lon: number) {
  const delta = 0.02;
  const left = lon - delta;
  const right = lon + delta;
  const top = lat + delta;
  const bottom = lat - delta;
  const marker = `${encodeURIComponent(lat)},${encodeURIComponent(lon)}`;
  return `https://www.openstreetmap.org/export/embed.html?bbox=${left}%2C${bottom}%2C${right}%2C${top}&layer=mapnik&marker=${marker}`;
}

function buildOsmEmbedBBox(b: { left: number; bottom: number; right: number; top: number }) {
  return `https://www.openstreetmap.org/export/embed.html?bbox=${b.left}%2C${b.bottom}%2C${b.right}%2C${b.top}&layer=mapnik`;
}

function fmtDt(s: string | null | undefined) {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleString();
  } catch {
    return s;
  }
}

function minutesUntil(ts: string | null | undefined): number | null {
  if (!ts) return null;
  const t = new Date(ts).getTime();
  if (!Number.isFinite(t)) return null;
  return Math.round((t - Date.now()) / 60000);
}

type MaintenanceFeedItem = {
  record_id: string;
  vehicle_id: string;
  registration_number: string;
  vehicle_status: string;
  model?: string | null;
  category: string;
  description: string;
  status: string;
  created_at: string;
  updated_at?: string | null;
  expected_ready_at?: string | null;
  expected_takt_hours?: number | null;
  assigned_to_user_id?: string | null;
};

function canUpdateInbox(role: OperatorRole) {
  return role === "OWNER" || role === "ADMIN" || role === "OPS";
}

function canManageVehicles(role: OperatorRole) {
  return role === "OWNER" || role === "ADMIN";
}

export function FleetPortalApp() {
  const [sess, setSess] = useState(() => loadSession());
  const [tab, setTab] = useState<Tab>("portfolio");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // auth form
  const [mode, setMode] = useState<"signup" | "login">("login");
  const [phone, setPhone] = useState<string>(() => sess?.user_phone ?? "+919999000401");
  const [operatorName, setOperatorName] = useState<string>("Eleride Fleet");
  const [operatorSlug, setOperatorSlug] = useState<string>("eleride-fleet");
  const [otpRequestId, setOtpRequestId] = useState<string>("");
  const [otp, setOtp] = useState<string>("");
  const [devOtp, setDevOtp] = useState<string>("");

  // data
  const [inbox, setInbox] = useState<InboxItem[]>([]);
  const [selectedReqId, setSelectedReqId] = useState<string>("");
  const [selectedReq, setSelectedReq] = useState<InboxDetail | null>(null);
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [selectedVehicleId, setSelectedVehicleId] = useState<string>("");
  const selectedVehicle = useMemo(() => vehicles.find((v) => v.id === selectedVehicleId) ?? null, [vehicles, selectedVehicleId]);
  const [maintenance, setMaintenance] = useState<Maintenance[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [vehicleFilter, setVehicleFilter] = useState<"ALL" | "ACTIVE" | "IN_MAINTENANCE" | "INACTIVE" | "LOW_BATT">("ALL");
  const [inboxHighlightCount, setInboxHighlightCount] = useState(0);
  const [maintHighlightCount, setMaintHighlightCount] = useState(0);
  const [maintFeed, setMaintFeed] = useState<MaintenanceFeedItem[]>([]);
  const [maintFeedTotalOpen, setMaintFeedTotalOpen] = useState<number>(0);

  const LS_INBOX_LAST_SEEN = useMemo(() => `eleride.fleet_portal.inbox.last_seen.${operatorSlug}`, [operatorSlug]);
  const LS_MAINT_LAST_SEEN = useMemo(() => `eleride.fleet_portal.maint.last_seen.${operatorSlug}`, [operatorSlug]);

  function lastSeen(key: string): number {
    const v = localStorage.getItem(key);
    const n = v ? Number(v) : 0;
    return Number.isFinite(n) ? n : 0;
  }
  function markSeen(key: string) {
    localStorage.setItem(key, String(Date.now()));
  }

  // vehicle creation
  const [newReg, setNewReg] = useState("MH12AB1234");
  const [newVehicleType, setNewVehicleType] = useState<"EV Scooter" | "EV Bike" | "EV 3W">("EV Scooter");
  const [newMake, setNewMake] = useState("Ola");
  const [newVariant, setNewVariant] = useState("S1 Pro");
  const [newYear, setNewYear] = useState<string>("2025");
  const [newColor, setNewColor] = useState("White");
  const [newBatteryKwh, setNewBatteryKwh] = useState<string>("3.0");
  const [newOwnership, setNewOwnership] = useState<"OWNED" | "LEASED">("LEASED");
  const [newLeasingPartner, setNewLeasingPartner] = useState<string>("Eleride Leasing");
  const [newNotes, setNewNotes] = useState<string>("New vehicle, ready for onboarding.");

  // maintenance creation
  const [maintCategory, setMaintCategory] = useState("GENERAL");
  const [maintDesc, setMaintDesc] = useState("Brake pads check");
  const [maintCost, setMaintCost] = useState<string>("0");
  const [maintTaktHrs, setMaintTaktHrs] = useState<string>("24");

  function parseMeta(meta?: string | null): Record<string, any> | null {
    if (!meta) return null;
    try {
      const v = JSON.parse(meta);
      if (!v || typeof v !== "object") return null;
      return v as Record<string, any>;
    } catch {
      return null;
    }
  }

  function buildVehicleMetaString(): string {
    const meta: Record<string, any> = {
      make: newMake.trim() || undefined,
      variant: newVariant.trim() || undefined,
      year: newYear.trim() || undefined,
      color: newColor.trim() || undefined,
      battery_kwh: newBatteryKwh.trim() || undefined,
      ownership: newOwnership,
      leasing_partner: newOwnership === "LEASED" ? (newLeasingPartner.trim() || undefined) : undefined,
      notes: newNotes.trim() || undefined,
    };
    for (const k of Object.keys(meta)) if (meta[k] == null || meta[k] === "") delete meta[k];
    return JSON.stringify(meta);
  }

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
    setTab("inbox");
    setInbox([]);
    setSelectedReqId("");
    setSelectedReq(null);
    setVehicles([]);
    setSelectedVehicleId("");
    setMaintenance([]);
    setOtpRequestId("");
    setOtp("");
    setDevOtp("");
  }

  async function refreshInbox() {
    if (!sess?.token) return;
    const res = await api.inboxList(sess.token);
    const items = res.items ?? [];
    setInbox(items);

    // highlight new or updated since last seen
    const ts = lastSeen(LS_INBOX_LAST_SEEN);
    const c = items.filter((it) => {
      const created = new Date(it.created_at).getTime();
      const upd = it.inbox_updated_at ? new Date(it.inbox_updated_at).getTime() : 0;
      return (Number.isFinite(created) && created > ts) || (Number.isFinite(upd) && upd > ts);
    }).length;
    setInboxHighlightCount(c);
  }

  async function refreshVehicles() {
    if (!sess?.token) return;
    const res = await api.vehiclesList(sess.token);
    setVehicles(res.items ?? []);
  }

  async function refreshSummary() {
    if (!sess?.token) return;
    const s = await api.dashboardSummary(sess.token);
    setSummary(s);
  }

  async function refreshMaintHighlights() {
    if (!sess?.token) return;
    const res = await api.openMaintenanceFeed(sess.token);
    const items = (res.items ?? []) as MaintenanceFeedItem[];
    setMaintFeed(items);
    setMaintFeedTotalOpen(res.total_open ?? items.length);
    const ts = lastSeen(LS_MAINT_LAST_SEEN);
    const c = items.filter((it) => {
      const created = new Date(it.created_at).getTime();
      const upd = it.updated_at ? new Date(it.updated_at).getTime() : 0;
      return (Number.isFinite(created) && created > ts) || (Number.isFinite(upd) && upd > ts);
    }).length;
    setMaintHighlightCount(c);
  }

  async function refreshMaintenance(vehicle_id: string) {
    if (!sess?.token) return;
    const res = await api.maintenanceList(sess.token, vehicle_id);
    setMaintenance(res.items ?? []);
  }

  useEffect(() => {
    if (!sess?.token) return;
    refreshInbox().catch(() => null);
    refreshVehicles().catch(() => null);
    refreshSummary().catch(() => null);
    refreshMaintHighlights().catch(() => null);

    const t = window.setInterval(() => {
      refreshInbox().catch(() => null);
      refreshSummary().catch(() => null);
      refreshMaintHighlights().catch(() => null);
    }, 10000);
    return () => window.clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sess?.token]);

  useEffect(() => {
    if (!sess?.token || !selectedReqId) {
      setSelectedReq(null);
      return;
    }
    api.inboxDetail(sess.token, selectedReqId)
      .then(setSelectedReq)
      .catch(() => setSelectedReq(null));
  }, [sess?.token, selectedReqId]);

  useEffect(() => {
    if (selectedVehicleId) {
      refreshMaintenance(selectedVehicleId).catch(() => null);
    } else {
      setMaintenance([]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedVehicleId]);

  if (!sess?.token) {
    return (
      <div className="authShell">
        <div className="card authCard stack">
          <div className="authLogoRow">
            <img className="authLogo" src={logoPng} alt="Eleride" />
          </div>
          <div>
            <div className="title">Fleet Portal</div>
            <div className="helper">Multi-tenant operator dashboard for rider intake + vehicle lifecycle.</div>
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
              <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+919999000401" />
              <div className="helper">OTP-based access (dev OTP shown in dev env).</div>
            </div>
            <div>
              <label>Operator slug</label>
              <input
                value={operatorSlug}
                onChange={(e) => setOperatorSlug(e.target.value)}
                placeholder="eleride-fleet"
                disabled={mode === "signup"}
              />
              <div className="helper">{mode === "login" ? "Required to choose tenant." : "Will be derived from name."}</div>
            </div>
          </div>

          {mode === "signup" ? (
            <div>
              <label>Operator name</label>
              <input value={operatorName} onChange={(e) => setOperatorName(e.target.value)} placeholder="Eleride Fleet" />
              <div className="helper">
                Tip: if you want rider requests to show up immediately, create tenant with name “Eleride Fleet”
                (slug becomes <b>eleride-fleet</b>).
              </div>
            </div>
          ) : null}

          <button
            className="btn btnPrimary"
            disabled={busy}
            onClick={() =>
              run(async () => {
                const r = await api.operatorOtpRequest({
                  phone: phone.trim(),
                  mode,
                  operator_name: mode === "signup" ? operatorName.trim() : undefined,
                  operator_slug: mode === "login" ? operatorSlug.trim() : undefined,
                });
                setOtpRequestId(r.request_id);
                setDevOtp(r.dev_otp ?? "");
              })
            }
          >
            {busy ? "Sending…" : "Send OTP"}
          </button>

          {otpRequestId ? (
            <div className="card stack" style={{ background: "rgba(255,255,255,0.02)" }}>
              <div className="grid2">
                <div>
                  <label>OTP</label>
                  <input value={otp} onChange={(e) => setOtp(e.target.value)} placeholder="6-digit OTP" />
                  {devOtp ? <div className="helper">Dev OTP: {devOtp}</div> : null}
                </div>
                <div className="helper">
                  After verify, you’ll land in a tenant-scoped dashboard. Role-based actions are enforced by the backend.
                </div>
              </div>
              <button
                className="btn btnPrimary"
                disabled={busy || otp.trim().length < 4}
                onClick={() =>
                  run(async () => {
                    const s = await api.operatorOtpVerify({ request_id: otpRequestId, otp: otp.trim() });
                    const next = {
                      token: s.access_token,
                      operator_id: s.operator_id,
                      operator_name: s.operator_name,
                      operator_slug: s.operator_slug,
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

  const filteredVehicles = useMemo(() => {
    const base = vehicles;
    if (vehicleFilter === "ALL") return base;
    if (vehicleFilter === "LOW_BATT") return base.filter((v) => v.battery_pct != null && v.battery_pct < 20);
    return base.filter((v) => v.status === vehicleFilter);
  }, [vehicles, vehicleFilter]);

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <img className="brandLogo" src={logoPng} alt="Eleride" />
          <div>Fleet Portal</div>
        </div>
        <div className="brandSub">
          Tenant: <b>{sess.operator_slug}</b>
          <div>Role: {sess.role}</div>
        </div>

        <div className="nav">
          <button className={`navBtn ${tab === "portfolio" ? "navBtnActive" : ""}`} onClick={() => setTab("portfolio")}>
            Portfolio
          </button>
          <button
            className={`navBtn ${tab === "inbox" ? "navBtnActive" : ""}`}
            onClick={() => {
              markSeen(LS_INBOX_LAST_SEEN);
              setInboxHighlightCount(0);
              setTab("inbox");
            }}
          >
            Inbox (Riders) {inboxHighlightCount > 0 ? <span className="badgeNew" style={{ marginLeft: 8 }}>{inboxHighlightCount}</span> : null}
          </button>
          <button className={`navBtn ${tab === "vehicles" ? "navBtnActive" : ""}`} onClick={() => setTab("vehicles")}>
            Vehicles
          </button>
          {selectedVehicle ? (
            <button className={`navBtn ${tab === "vehicle" ? "navBtnActive" : ""}`} onClick={() => setTab("vehicle")}>
              Vehicle: {selectedVehicle.registration_number}
            </button>
          ) : null}
        </div>

        <div style={{ marginTop: 18 }} className="stack">
          <button className="btn" disabled={busy} onClick={() => run(refreshInbox)}>
            Refresh inbox
          </button>
          <button className="btn" disabled={busy} onClick={() => run(refreshVehicles)}>
            Refresh vehicles
          </button>
          <button className="btn" disabled={busy} onClick={() => run(refreshSummary)}>
            Refresh portfolio
          </button>
          <button
            className="btn btnPrimary"
            disabled={busy || !canManageVehicles(sess.role)}
            onClick={() =>
              run(async () => {
                const r = await api.seedDemo(sess.token, 28);
                await refreshVehicles();
                await refreshSummary();
                setError(`Seeded demo fleet: ${r.vehicles_created} vehicles created.`);
              })
            }
          >
            Seed demo fleet
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
              {tab === "portfolio"
                ? "Portfolio overview"
                : tab === "inbox"
                  ? "Incoming rider interest"
                  : tab === "vehicles"
                    ? "Fleet"
                    : "Vehicle lifecycle"}
            </div>
            <div className="helper">{sess.operator_name}</div>
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
              <div className="kpi" onClick={() => { setVehicleFilter("ALL"); setTab("vehicles"); }}>
                <div className="kpiValue">{summary?.vehicles_total ?? vehicles.length}</div>
                <div className="kpiLabel">Total vehicles</div>
                <div className="kpiHint">Click to view all vehicles</div>
              </div>
              <div className="kpi" onClick={() => { setVehicleFilter("ACTIVE"); setTab("vehicles"); }}>
                <div className="kpiValue">{summary?.vehicles_active ?? vehicles.filter(v => v.status === "ACTIVE").length}</div>
                <div className="kpiLabel">Active</div>
                <div className="kpiHint">Running in arenas</div>
              </div>
              <div className="kpi" onClick={() => { setVehicleFilter("IN_MAINTENANCE"); setTab("vehicles"); }}>
                <div className="kpiValue">{summary?.vehicles_in_maintenance ?? vehicles.filter(v => v.status === "IN_MAINTENANCE").length}</div>
                <div className="kpiLabel">In maintenance</div>
                <div className="kpiHint">Work orders open</div>
              </div>
              <div
                className="kpi"
                onClick={() => {
                  setVehicleFilter("IN_MAINTENANCE");
                  markSeen(LS_MAINT_LAST_SEEN);
                  setMaintHighlightCount(0);
                  setTab("vehicles");
                }}
                title="Tickets assigned to the maintenance team (OPEN maintenance_records)"
              >
                <div className="kpiValue">{summary?.open_maintenance_ticket_count ?? "—"}</div>
                <div className="kpiLabel">Maintenance tickets (open)</div>
                <div className="kpiHint">
                  Assigned: {summary?.open_maintenance_assigned_ticket_count ?? "—"} • Unassigned:{" "}
                  {summary?.open_maintenance_unassigned_ticket_count ?? "—"} • Overdue: {summary?.open_maintenance_overdue_count ?? "—"}
                </div>
              </div>
              <div className="kpi" onClick={() => { setVehicleFilter("LOW_BATT"); setTab("vehicles"); }}>
                <div className="kpiValue">{summary?.low_battery_count ?? vehicles.filter(v => (v.battery_pct ?? 100) < 20).length}</div>
                <div className="kpiLabel">Low battery (&lt;20%)</div>
                <div className="kpiHint">Needs charging rotation</div>
              </div>
            </div>

            <div className="grid2">
              <div className="card stack">
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <div style={{ fontWeight: 1000 }}>Operations map (demo)</div>
                  <div className="pill">Avg battery: {summary?.avg_battery_pct != null ? `${summary.avg_battery_pct}%` : "—"}</div>
                </div>
                <FleetMapPanel
                  vehicles={vehicles}
                  selectedVehicleId={selectedVehicleId}
                  onSelect={(id) => {
                    setSelectedVehicleId(id);
                    // keep user on portfolio, just select for details
                  }}
                />
                <div className="helper">
                  Vehicles are clustered around Pune “arenas” (Wakad, Hinjewadi, Chinchwad, Kharadi, etc). Green=Active, Amber=Maintenance, Gray=Inactive.
                </div>
              </div>

              <div className="card stack">
                <div style={{ fontWeight: 1000 }}>Arenas</div>
                <div className="arenaGrid">
                  {(summary?.arenas ?? []).slice(0, 6).map((a: any) => (
                    <div key={a.name} className="arenaCard">
                      <div className="arenaName">{a.name}</div>
                      <div className="arenaMeta">
                        <span className="tag">{a.vehicles_total} total</span>
                        <span className="tag tagOk">{a.vehicles_active} active</span>
                        <span className="tag tagWarn">{a.vehicles_in_maintenance} maint</span>
                        <span className="tag">avg batt {a.avg_battery_pct != null ? `${a.avg_battery_pct}%` : "—"}</span>
                      </div>
                    </div>
                  ))}
                  {!summary?.arenas?.length ? <div className="helper">No fleet data yet. Click “Seed demo fleet”.</div> : null}
                </div>
                <div className="divider" />
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <div style={{ fontWeight: 1000 }}>Rider intake</div>
                  <div className="row">
                    {maintHighlightCount > 0 ? <span className="badgeNew">Maint updates: {maintHighlightCount}</span> : null}
                    <div className="pill">Open maintenance (vehicles): {summary?.open_maintenance_count ?? "—"}</div>
                  </div>
                </div>
                <div
                  className="kpi"
                  onClick={() => {
                    markSeen(LS_INBOX_LAST_SEEN);
                    setInboxHighlightCount(0);
                    setTab("inbox");
                  }}
                  style={{ cursor: "pointer" }}
                  title="Click to open Inbox"
                >
                  <div className="kpiValue">{summary?.inbox_new ?? "—"}</div>
                  <div className="kpiLabel">New rider requests (unresponded)</div>
                  <div className="kpiHint">Click to view incoming requests</div>
                </div>
                <div className="row">
                  <span className="tag">{summary?.inbox_new ?? "—"} new</span>
                  <span className="tag tagWarn">{summary?.inbox_contacted ?? "—"} contacted</span>
                  <span className="tag tagOk">{summary?.inbox_onboarded ?? "—"} onboarded</span>
                  <span className="tag tagBad">{summary?.inbox_rejected ?? "—"} rejected</span>
                </div>
                <button
                  className="btn btnPrimary"
                  onClick={() => {
                    markSeen(LS_INBOX_LAST_SEEN);
                    setInboxHighlightCount(0);
                    setTab("inbox");
                  }}
                >
                  Open inbox
                </button>

                <div className="divider" />
                <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
                  <div style={{ fontWeight: 1000 }}>Maintenance feed</div>
                  <div className="row">
                    <div className="pill">{maintFeedTotalOpen} open (vehicles)</div>
                    <button
                      className="btn"
                      disabled={busy}
                      onClick={() =>
                        run(async () => {
                          await refreshMaintHighlights();
                        })
                      }
                    >
                      Refresh
                    </button>
                    <button
                      className="btn"
                      disabled={busy}
                      onClick={() => {
                        markSeen(LS_MAINT_LAST_SEEN);
                        setMaintHighlightCount(0);
                      }}
                      title="Mark all current maintenance items as seen (clears highlight badges)"
                    >
                      Mark seen
                    </button>
                  </div>
                </div>
                <div className="helper">
                  Shows OPEN maintenance vehicles. “UPDATED” means ETA/takt or assignment changed since you last viewed.
                </div>

                <div className="miniList" style={{ maxHeight: 220 }}>
                  {maintFeed.length === 0 ? <div className="helper">No open maintenance tickets right now.</div> : null}
                  {maintFeed.slice(0, 8).map((m) => {
                    const ts = lastSeen(LS_MAINT_LAST_SEEN);
                    const created = new Date(m.created_at).getTime();
                    const upd = m.updated_at ? new Date(m.updated_at).getTime() : 0;
                    const isNew = Number.isFinite(created) && created > ts;
                    const isUpd = !isNew && Number.isFinite(upd) && upd > ts;
                    const etaMin = minutesUntil(m.expected_ready_at ?? null);
                    const etaLabel =
                      etaMin == null ? "ETA —" : etaMin <= 0 ? "ETA due" : etaMin < 60 ? `ETA ${etaMin}m` : `ETA ${Math.round(etaMin / 60)}h`;
                    const assigned = m.assigned_to_user_id ? "Assigned" : "Unassigned";
                    return (
                      <div
                        key={m.record_id}
                        className={`miniRow ${isNew || isUpd ? "rowPulse" : ""}`}
                        onClick={() => {
                          // jump to vehicle lifecycle page for this vehicle
                          setSelectedVehicleId(m.vehicle_id);
                          setTab("vehicle");
                        }}
                        title={`${m.registration_number} • ${m.category} • ${etaLabel}`}
                      >
                        <div style={{ minWidth: 0 }}>
                          <div className="miniPrimary">{m.registration_number}</div>
                          <div className="miniSecondary" style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                            {m.category} • {etaLabel} • {assigned}
                          </div>
                          <div className="miniSecondary">
                            Updated: {fmtDt(m.updated_at ?? null)} • Created: {fmtDt(m.created_at)}
                          </div>
                        </div>
                        <div className="miniSecondary" style={{ textAlign: "right" }}>
                          {isNew ? <span className="badgeNew">NEW</span> : isUpd ? <span className="badgeNew">UPDATED</span> : null}
                        </div>
                      </div>
                    );
                  })}
                  {maintFeedTotalOpen > maintFeed.length ? (
                    <div className="helper" style={{ marginTop: 8 }}>
                      Showing {maintFeed.length} of {maintFeedTotalOpen} open maintenance vehicles.
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
          </div>
        ) : null}

        {tab === "inbox" ? (
          <div className="grid2">
            <div className="card stack">
              <div className="row" style={{ justifyContent: "space-between" }}>
                <div className="helper">Rider requests are created by the platform when a rider taps “Connect me”.</div>
                <div className="pill">{inbox.length} requests</div>
              </div>
              <table className="table">
                <thead>
                  <tr>
                    <th>Rider</th>
                    <th>Lane</th>
                    <th>Pickup</th>
                    <th>Status</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {inbox.map((it) => {
                    const ts = lastSeen(LS_INBOX_LAST_SEEN);
                    const created = new Date(it.created_at).getTime();
                    const upd = it.inbox_updated_at ? new Date(it.inbox_updated_at).getTime() : 0;
                    const isNew = Number.isFinite(created) && created > ts;
                    const isUpd = !isNew && Number.isFinite(upd) && upd > ts;
                    return (
                    <tr
                      key={it.supply_request_id}
                      className={isNew || isUpd ? "rowPulse" : undefined}
                      style={{ cursor: "pointer" }}
                      onClick={() => {
                        markSeen(LS_INBOX_LAST_SEEN);
                        setInboxHighlightCount(0);
                        setSelectedReqId(it.supply_request_id);
                      }}
                    >
                      <td>
                        <div style={{ fontWeight: 900 }}>{it.rider.name ?? "—"}</div>
                        <div className="helper">{it.rider.phone}</div>
                      </td>
                      <td>
                        <div style={{ fontWeight: 900 }}>{it.lane_id}</div>
                        <div className="helper">{new Date(it.created_at).toLocaleString()}</div>
                      </td>
                      <td className="helper">{it.pickup_location ?? "—"}</td>
                      <td>
                        <span className={tagClassForState(it.state)}>{it.state}</span>
                      </td>
                      <td className="helper">
                        {isNew ? <span className="badgeNew">NEW</span> : isUpd ? <span className="badgeNew">UPDATED</span> : null} View →
                      </td>
                    </tr>
                  )})}
                  {inbox.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="helper">
                        No requests yet. Create one from the rider app by clicking “Connect me”.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>

            <div className="detailPanel stack">
              <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <div className="title" style={{ fontSize: 16 }}>Request details</div>
                  <div className="helper">Click a request to see full rider details.</div>
                </div>
                {selectedReqId ? (
                  <button className="btn" onClick={() => { setSelectedReqId(""); setSelectedReq(null); }}>
                    Close
                  </button>
                ) : null}
              </div>
              <div className="divider" />

              {!selectedReqId ? (
                <div className="helper">No request selected.</div>
              ) : !selectedReq ? (
                <div className="helper">Loading…</div>
              ) : (
                <>
                  <div className="kvGrid">
                    <div className="kv">
                      <div className="kvLabel">Rider name</div>
                      <div className="kvValue">{selectedReq.rider.name ?? "—"}</div>
                    </div>
                    <div className="kv">
                      <div className="kvLabel">Phone</div>
                      <div className="kvValue">{selectedReq.rider.phone}</div>
                    </div>
                    <div className="kv">
                      <div className="kvLabel">Rider status</div>
                      <div className="kvValue">{selectedReq.rider.status}</div>
                    </div>
                    <div className="kv">
                      <div className="kvLabel">Preferred zones</div>
                      <div className="kvValue">{(selectedReq.rider.preferred_zones ?? []).join(", ") || "—"}</div>
                    </div>
                    <div className="kv">
                      <div className="kvLabel">Address</div>
                      <div className="kvValue">{selectedReq.rider.address ?? "—"}</div>
                    </div>
                    <div className="kv">
                      <div className="kvLabel">Emergency contact</div>
                      <div className="kvValue">{selectedReq.rider.emergency_contact ?? "—"}</div>
                    </div>
                  </div>

                  <div className="divider" />
                  <div style={{ fontWeight: 1000 }}>Request context</div>
                  <div className="kvGrid">
                    <div className="kv">
                      <div className="kvLabel">Lane</div>
                      <div className="kvValue">{selectedReq.lane_id}</div>
                    </div>
                    <div className="kv">
                      <div className="kvLabel">Pickup location</div>
                      <div className="kvValue">{selectedReq.pickup_location ?? "—"}</div>
                    </div>
                    <div className="kv">
                      <div className="kvLabel">Time window</div>
                      <div className="kvValue">{selectedReq.time_window ?? "—"}</div>
                    </div>
                    <div className="kv">
                      <div className="kvLabel">Requirements</div>
                      <div className="kvValue">{selectedReq.requirements ?? "—"}</div>
                    </div>
                    <div className="kv">
                      <div className="kvLabel">Inbox state</div>
                      <div className="kvValue">{selectedReq.state}</div>
                    </div>
                    <div className="kv">
                      <div className="kvLabel">Created</div>
                      <div className="kvValue">{new Date(selectedReq.created_at).toLocaleString()}</div>
                    </div>
                  </div>

                  <div className="divider" />
                  <div className="row">
                    <button
                      className="btn"
                      disabled={!canUpdateInbox(sess.role) || busy}
                      onClick={() =>
                        run(async () => {
                          await api.inboxSetState(sess.token, selectedReq.supply_request_id, { state: "CONTACTED", note: "Called rider" });
                          await refreshInbox();
                          setSelectedReq(await api.inboxDetail(sess.token, selectedReq.supply_request_id));
                        })
                      }
                    >
                      Mark contacted
                    </button>
                    <button
                      className="btn btnPrimary"
                      disabled={!canUpdateInbox(sess.role) || busy}
                      onClick={() =>
                        run(async () => {
                          await api.inboxSetState(sess.token, selectedReq.supply_request_id, { state: "ONBOARDED", note: "Vehicle assigned" });
                          await refreshInbox();
                          setSelectedReq(await api.inboxDetail(sess.token, selectedReq.supply_request_id));
                        })
                      }
                    >
                      Onboarded
                    </button>
                    <button
                      className="btn btnDanger"
                      disabled={!canUpdateInbox(sess.role) || busy}
                      onClick={() =>
                        run(async () => {
                          await api.inboxSetState(sess.token, selectedReq.supply_request_id, { state: "REJECTED", note: "No slots" });
                          await refreshInbox();
                          setSelectedReq(await api.inboxDetail(sess.token, selectedReq.supply_request_id));
                        })
                      }
                    >
                      Reject
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        ) : null}

        {tab === "vehicles" ? (
          <div className="stack">
            <div className="card stack">
              <div className="row" style={{ justifyContent: "space-between" }}>
                <div style={{ fontWeight: 1000 }}>Fleet health</div>
                <div className="row">
                  <span className="pill">Filter: {vehicleFilter}</span>
                  <button className="btn" onClick={() => setVehicleFilter("ALL")}>All</button>
                  <button className="btn" onClick={() => setVehicleFilter("ACTIVE")}>Active</button>
                  <button className="btn" onClick={() => setVehicleFilter("IN_MAINTENANCE")}>Maintenance</button>
                  <button className="btn" onClick={() => setVehicleFilter("LOW_BATT")}>Low batt</button>
                </div>
              </div>
              <FleetMapPanel
                vehicles={filteredVehicles}
                selectedVehicleId={selectedVehicleId}
                onSelect={(id) => {
                  setSelectedVehicleId(id);
                }}
              />
              <div className="helper">Showing {filteredVehicles.length} vehicles on the map.</div>
            </div>

            {canManageVehicles(sess.role) ? (
              <div className="card stack">
                <div style={{ fontWeight: 900 }}>Add vehicle</div>
                <div className="grid2">
                  <div>
                    <label>Registration number</label>
                    <input value={newReg} onChange={(e) => setNewReg(e.target.value)} placeholder="MH12AB1234" />
                    <div className="helper">Use the official registration number (unique vehicle ID).</div>
                  </div>
                  <div>
                    <label>Vehicle type</label>
                    <select value={newVehicleType} onChange={(e) => setNewVehicleType(e.target.value as any)}>
                      <option value="EV Scooter">EV Scooter</option>
                      <option value="EV Bike">EV Bike</option>
                      <option value="EV 3W">EV 3W</option>
                    </select>
                  </div>
                </div>

                <div className="grid2">
                  <div>
                    <label>Make (brand)</label>
                    <input value={newMake} onChange={(e) => setNewMake(e.target.value)} placeholder="Ola / Ather / TVS…" />
                  </div>
                  <div>
                    <label>Variant / trim</label>
                    <input value={newVariant} onChange={(e) => setNewVariant(e.target.value)} placeholder="S1 Pro / 450X…" />
                  </div>
                </div>

                <div className="grid2">
                  <div>
                    <label>Year</label>
                    <input value={newYear} onChange={(e) => setNewYear(e.target.value)} inputMode="numeric" placeholder="2025" />
                  </div>
                  <div>
                    <label>Color</label>
                    <input value={newColor} onChange={(e) => setNewColor(e.target.value)} placeholder="White" />
                  </div>
                </div>

                <div className="grid2">
                  <div>
                    <label>Battery capacity (kWh)</label>
                    <input
                      value={newBatteryKwh}
                      onChange={(e) => setNewBatteryKwh(e.target.value)}
                      inputMode="decimal"
                      placeholder="3.0"
                    />
                  </div>
                  <div>
                    <label>Ownership</label>
                    <select value={newOwnership} onChange={(e) => setNewOwnership(e.target.value as any)}>
                      <option value="OWNED">Owned</option>
                      <option value="LEASED">Leased</option>
                    </select>
                  </div>
                </div>

                {newOwnership === "LEASED" ? (
                  <div>
                    <label>Leasing partner</label>
                    <input value={newLeasingPartner} onChange={(e) => setNewLeasingPartner(e.target.value)} placeholder="Eleride Leasing" />
                  </div>
                ) : null}

                <div>
                  <label>Notes</label>
                  <textarea value={newNotes} onChange={(e) => setNewNotes(e.target.value)} placeholder="Condition, allocation, special remarks…" />
                </div>

                <div className="helper">
                  Stored as structured vehicle metadata (operators won’t type JSON). You can later bind a telematics device in the vehicle page.
                </div>
                <button
                  className="btn btnPrimary"
                  disabled={busy}
                  onClick={() =>
                    run(async () => {
                      const reg = newReg.trim().toUpperCase();
                      const model = `${newVehicleType}${newMake.trim() ? ` • ${newMake.trim()}` : ""}${newVariant.trim() ? ` ${newVariant.trim()}` : ""}`.trim();
                      const meta = buildVehicleMetaString();
                      await api.vehicleCreate(sess.token, { registration_number: reg, model, meta });
                      await refreshVehicles();
                    })
                  }
                >
                  Add vehicle
                </button>
              </div>
            ) : null}

            <div className="card stack">
              <div className="row" style={{ justifyContent: "space-between" }}>
                <div style={{ fontWeight: 900 }}>Fleet vehicles</div>
                <div className="pill">{filteredVehicles.length} vehicles</div>
              </div>
              <table className="table">
                <thead>
                  <tr>
                    <th>Registration</th>
                    <th>Arena</th>
                    <th>Status</th>
                    <th>Last seen</th>
                    <th>Odo / Battery</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {filteredVehicles.map((v) => (
                    <tr key={v.id}>
                      <td style={{ fontWeight: 900 }}>{v.registration_number}</td>
                      <td className="helper">{arenaFor(v.last_lat, v.last_lon)}</td>
                      <td>
                        <span className={v.status === "ACTIVE" ? "tag tagOk" : v.status === "IN_MAINTENANCE" ? "tag tagWarn" : "tag"}>
                          {v.status}
                        </span>
                      </td>
                      <td className="helper">{v.last_telemetry_at ? new Date(v.last_telemetry_at).toLocaleString() : "—"}</td>
                      <td className="helper">
                        {v.odometer_km != null ? `${v.odometer_km.toFixed(1)} km` : "—"} /{" "}
                        {v.battery_pct != null ? `${v.battery_pct.toFixed(0)}%` : "—"}
                      </td>
                      <td>
                        <button
                          className="btn btnPrimary"
                          onClick={() => {
                            setSelectedVehicleId(v.id);
                            setTab("vehicle");
                          }}
                        >
                          Open
                        </button>
                      </td>
                    </tr>
                  ))}
                  {filteredVehicles.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="helper">
                        No vehicles yet.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}

        {tab === "vehicle" ? (
          <div className="stack">
            {!selectedVehicle ? (
              <div className="card">Pick a vehicle from Vehicles.</div>
            ) : (
              <>
                <div className="card stack">
                  <div className="row" style={{ justifyContent: "space-between" }}>
                    <div>
                      <div className="title">{selectedVehicle.registration_number}</div>
                      <div className="helper">{selectedVehicle.model ?? "—"}</div>
                    </div>
                    <div className="row">
                      <span className="pill">Status: {selectedVehicle.status}</span>
                      <button className="btn" onClick={() => setTab("vehicles")}>
                        Back
                      </button>
                    </div>
                  </div>

                  <div className="grid2">
                    <div className="stack">
                      <div className="row">
                        <span className="tag">Odo: {selectedVehicle.odometer_km != null ? `${selectedVehicle.odometer_km.toFixed(1)} km` : "—"}</span>
                        <span className="tag">Battery: {selectedVehicle.battery_pct != null ? `${selectedVehicle.battery_pct.toFixed(0)}%` : "—"}</span>
                        <span className="tag">Last: {selectedVehicle.last_telemetry_at ? new Date(selectedVehicle.last_telemetry_at).toLocaleString() : "—"}</span>
                      </div>

                      {selectedVehicle.last_lat != null && selectedVehicle.last_lon != null ? (
                        <div className="mapFrame">
                          <iframe title="map" src={buildOsmEmbed(selectedVehicle.last_lat, selectedVehicle.last_lon)} loading="lazy" />
                        </div>
                      ) : (
                        <div className="helper">No telemetry yet. Post telemetry to see live location.</div>
                      )}
                    </div>

                    <div className="stack">
                      <div className="card stack" style={{ boxShadow: "none", background: "rgba(255,255,255,0.02)" }}>
                        <div style={{ fontWeight: 900 }}>Vehicle details</div>
                        {(() => {
                          const m = parseMeta(selectedVehicle.meta);
                          if (!m) return <div className="helper">No structured details saved yet.</div>;
                          const keys = Object.keys(m);
                          if (!keys.length) return <div className="helper">No structured details saved yet.</div>;
                          return (
                            <div className="kvGrid">
                              {keys.map((k) => (
                                <React.Fragment key={k}>
                                  <div className="kvKey">{k.replace(/_/g, " ")}</div>
                                  <div className="kvValue">{String(m[k])}</div>
                                </React.Fragment>
                              ))}
                            </div>
                          );
                        })()}
                      </div>

                      <div className="card stack" style={{ boxShadow: "none", background: "rgba(255,255,255,0.02)" }}>
                        <div style={{ fontWeight: 900 }}>Telematics mapping</div>
                        <div className="helper">Bind a device ID to this vehicle (registration number is the fleet vehicle ID).</div>
                        <DeviceBind
                          disabled={!canManageVehicles(sess.role) || busy}
                          onBind={(device_id, provider) =>
                            run(async () => {
                              await api.deviceBind(sess.token, selectedVehicle.id, { device_id, provider });
                            })
                          }
                        />
                      </div>

                      <div className="card stack" style={{ boxShadow: "none", background: "rgba(255,255,255,0.02)" }}>
                        <div style={{ fontWeight: 900 }}>Telemetry ingest (demo)</div>
                        <div className="helper">Push sample telemetry to update vehicle location & vitals.</div>
                        <button
                          className="btn btnPrimary"
                          disabled={busy}
                          onClick={() =>
                            run(async () => {
                              await api.telemetryIngest(sess.token, selectedVehicle.id, {
                                lat: 18.5204 + Math.random() * 0.01,
                                lon: 73.8567 + Math.random() * 0.01,
                                speed_kph: 22 + Math.random() * 10,
                                odometer_km: (selectedVehicle.odometer_km ?? 1200) + 1.2,
                                battery_pct: Math.max(10, (selectedVehicle.battery_pct ?? 60) - 0.4),
                              });
                              await refreshVehicles();
                            })
                          }
                        >
                          Send sample telemetry
                        </button>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="card stack">
                  <div className="row" style={{ justifyContent: "space-between" }}>
                    <div style={{ fontWeight: 900 }}>Maintenance</div>
                    <div className="pill">{maintenance.length} records</div>
                  </div>

                  <div className="grid2">
                    <div className="stack">
                      <table className="table">
                        <thead>
                          <tr>
                            <th>Status</th>
                            <th>Category</th>
                            <th>Description</th>
                            <th>Cost</th>
                            <th>ETA active</th>
                            <th>Created</th>
                            <th></th>
                          </tr>
                        </thead>
                        <tbody>
                          {maintenance.map((m) => (
                            <tr key={m.id}>
                              <td>
                                <span className={m.status === "OPEN" ? "tag tagWarn" : "tag tagOk"}>{m.status}</span>
                              </td>
                              <td className="helper">{m.category}</td>
                              <td className="helper">{m.description}</td>
                              <td className="helper">{m.cost_inr != null ? `₹${m.cost_inr}` : "—"}</td>
                              <td className="helper">
                                {m.status === "OPEN" && m.expected_ready_at
                                  ? new Date(m.expected_ready_at).toLocaleString()
                                  : "—"}
                              </td>
                              <td className="helper">{new Date(m.created_at).toLocaleString()}</td>
                              <td>
                                {m.status === "OPEN" ? (
                                  <button
                                    className="btn"
                                    disabled={busy || (sess.role !== "OWNER" && sess.role !== "ADMIN" && sess.role !== "MAINT")}
                                    onClick={() =>
                                      run(async () => {
                                        await api.maintenanceClose(sess.token, selectedVehicle.id, m.id);
                                        await refreshVehicles();
                                        await refreshMaintenance(selectedVehicle.id);
                                      })
                                    }
                                  >
                                    Mark active
                                  </button>
                                ) : null}
                              </td>
                            </tr>
                          ))}
                          {maintenance.length === 0 ? (
                            <tr>
                              <td colSpan={7} className="helper">
                                No maintenance records yet.
                              </td>
                            </tr>
                          ) : null}
                        </tbody>
                      </table>
                    </div>

                    <div className="stack">
                      <div className="card stack" style={{ boxShadow: "none", background: "rgba(255,255,255,0.02)" }}>
                        <div style={{ fontWeight: 900 }}>Create maintenance ticket</div>
                        <div className="grid2">
                          <div>
                            <label>Category</label>
                            <input value={maintCategory} onChange={(e) => setMaintCategory(e.target.value)} />
                          </div>
                          <div>
                            <label>Estimated cost (₹)</label>
                            <input value={maintCost} onChange={(e) => setMaintCost(e.target.value)} inputMode="numeric" />
                          </div>
                        </div>
                        <div>
                          <label>Expected takt time (hours)</label>
                          <input value={maintTaktHrs} onChange={(e) => setMaintTaktHrs(e.target.value)} inputMode="numeric" />
                          <div className="helper">Used to compute ETA for the vehicle to become ACTIVE again.</div>
                        </div>
                        <div>
                          <label>Description</label>
                          <textarea value={maintDesc} onChange={(e) => setMaintDesc(e.target.value)} />
                        </div>
                        <button
                          className="btn btnPrimary"
                          disabled={busy || (sess.role !== "OWNER" && sess.role !== "ADMIN" && sess.role !== "MAINT")}
                          onClick={() =>
                            run(async () => {
                              await api.maintenanceCreate(sess.token, selectedVehicle.id, {
                                category: maintCategory,
                                description: maintDesc,
                                cost_inr: Number.isFinite(Number(maintCost)) ? Number(maintCost) : null,
                                expected_takt_hours: Number.isFinite(Number(maintTaktHrs)) ? Number(maintTaktHrs) : 24,
                              });
                              await refreshVehicles();
                              await refreshMaintenance(selectedVehicle.id);
                            })
                          }
                        >
                          Create ticket
                        </button>
                        <div className="helper">Role-gated: OWNER/ADMIN/MAINT.</div>
                      </div>
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>
        ) : null}
      </main>
    </div>
  );
}

function DeviceBind(props: { disabled: boolean; onBind: (device_id: string, provider?: string) => void }) {
  const [deviceId, setDeviceId] = useState("tmx-0001");
  const [provider, setProvider] = useState("demo");
  return (
    <div className="stack">
      <div className="grid2">
        <div>
          <label>Device ID</label>
          <input value={deviceId} onChange={(e) => setDeviceId(e.target.value)} />
        </div>
        <div>
          <label>Provider</label>
          <input value={provider} onChange={(e) => setProvider(e.target.value)} />
        </div>
      </div>
      <button className="btn btnPrimary" disabled={props.disabled} onClick={() => props.onBind(deviceId.trim(), provider.trim())}>
        Bind device
      </button>
    </div>
  );
}

function arenaFor(lat?: number | null, lon?: number | null): string {
  if (lat == null || lon == null) return "—";
  const arenas = [
    { name: "Wakad", lat: 18.5975, lon: 73.77 },
    { name: "Hinjewadi", lat: 18.596, lon: 73.74 },
    { name: "Chinchwad", lat: 18.629, lon: 73.8 },
    { name: "Kharadi", lat: 18.5518, lon: 73.9467 },
    { name: "Hadapsar", lat: 18.5089, lon: 73.926 },
    { name: "Koregaon Park", lat: 18.5362, lon: 73.894 },
    { name: "Baner", lat: 18.559, lon: 73.7868 },
  ];
  let best = arenas[0];
  let bestD = Infinity;
  for (const a of arenas) {
    const d = (lat - a.lat) * (lat - a.lat) + (lon - a.lon) * (lon - a.lon);
    if (d < bestD) {
      bestD = d;
      best = a;
    }
  }
  return best.name;
}

// (replaced by FleetMapPanel – real embedded map + overlay markers)

function FleetMapPanel(props: {
  vehicles: Vehicle[];
  selectedVehicleId: string;
  onSelect: (id: string) => void;
}) {
  // Pune-ish viewport. Matches the seed-demo area and keeps the map informative.
  const bbox = { left: 73.70, bottom: 18.45, right: 73.98, top: 18.68 };
  const pts = props.vehicles
    .filter((v) => v.last_lat != null && v.last_lon != null)
    .map((v) => ({ ...v, lat: v.last_lat as number, lon: v.last_lon as number }));

  function xy(lat: number, lon: number) {
    const x = ((lon - bbox.left) / (bbox.right - bbox.left)) * 100;
    const y = (1 - (lat - bbox.bottom) / (bbox.top - bbox.bottom)) * 100;
    return { x: Math.max(0, Math.min(100, x)), y: Math.max(0, Math.min(100, y)) };
  }

  function colorFor(v: Vehicle) {
    if (v.status === "ACTIVE") return "rgba(22, 163, 74, 0.95)";
    if (v.status === "IN_MAINTENANCE") return "rgba(245, 158, 11, 0.95)";
    return "rgba(148, 163, 184, 0.95)";
  }

  const selected = props.vehicles.find((v) => v.id === props.selectedVehicleId) ?? null;

  return (
    <div className="grid2">
      <div className="osmWrap">
        <iframe className="osmIframe" title="fleet-map" src={buildOsmEmbedBBox(bbox)} loading="lazy" />
        <div className="markerLayer">
          {pts.slice(0, 350).map((v) => {
            const p = xy(v.lat, v.lon);
            const isSel = v.id === props.selectedVehicleId;
            return (
              <div
                key={v.id}
                className={`vehMarker ${isSel ? "vehMarkerSelected" : ""}`}
                style={{ left: `${p.x}%`, top: `${p.y}%`, background: colorFor(v) }}
                title={`${v.registration_number} • ${arenaFor(v.lat, v.lon)} • ${v.status} • batt ${v.battery_pct ?? "—"}%`}
                onClick={() => props.onSelect(v.id)}
              />
            );
          })}
        </div>
        <div className="mapLegend">
          <div className="legendItem">
            <span className="legendSwatch" style={{ background: "rgba(22, 163, 74, 0.95)" }} />
            Active
          </div>
          <div className="legendItem">
            <span className="legendSwatch" style={{ background: "rgba(245, 158, 11, 0.95)" }} />
            Maintenance
          </div>
          <div className="legendItem">
            <span className="legendSwatch" style={{ background: "rgba(148, 163, 184, 0.95)" }} />
            Inactive
          </div>
        </div>
      </div>

      <div className="mapSide">
        <div style={{ fontWeight: 1000 }}>Selected vehicle</div>
        <div className="helper">Click a marker on the map to inspect.</div>
        <div className="divider" />
        {selected ? (
          <div className="stack" style={{ gap: 8 }}>
            <div className="row" style={{ justifyContent: "space-between" }}>
              <div>
                <div className="miniPrimary">{selected.registration_number}</div>
                <div className="miniSecondary">{arenaFor(selected.last_lat, selected.last_lon)} • {selected.status}</div>
              </div>
              <div className="tag">{selected.battery_pct != null ? `${selected.battery_pct.toFixed(0)}%` : "—"}</div>
            </div>
            <div className="miniSecondary">
              Last telemetry: {selected.last_telemetry_at ? new Date(selected.last_telemetry_at).toLocaleString() : "—"}
            </div>
            <div className="miniSecondary">
              Odometer: {selected.odometer_km != null ? `${selected.odometer_km.toFixed(1)} km` : "—"}
            </div>
          </div>
        ) : (
          <div className="helper">No vehicle selected.</div>
        )}

        <div className="miniList">
          <div className="miniSecondary" style={{ marginBottom: 8 }}>
            Vehicles on map: {pts.length}
          </div>
          {pts.slice(0, 60).map((v) => (
            <div
              key={v.id}
              className={`miniRow ${v.id === props.selectedVehicleId ? "miniRowActive" : ""}`}
              onClick={() => props.onSelect(v.id)}
            >
              <div>
                <div className="miniPrimary">{v.registration_number}</div>
                <div className="miniSecondary">
                  {arenaFor(v.lat, v.lon)} • {v.status}
                </div>
              </div>
              <div className="miniSecondary">{v.battery_pct != null ? `${v.battery_pct.toFixed(0)}%` : "—"}</div>
            </div>
          ))}
          {pts.length > 60 ? <div className="helper">Showing 60 of {pts.length} vehicles.</div> : null}
        </div>
      </div>
    </div>
  );
}



