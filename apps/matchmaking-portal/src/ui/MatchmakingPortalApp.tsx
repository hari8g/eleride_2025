import React, { useEffect, useMemo, useState } from "react";
import { api, AuditRow, Availability, DemandCard, HttpError, Recommendation } from "../lib/api";
import { clearSession, loadSession, saveSession } from "../lib/session";

function safeMsg(e: unknown): string {
  if (e instanceof HttpError) {
    const body = e.body as any;
    const detail = body?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return "Validation failed.";
    return `Request failed (${e.status}).`;
  }
  return (e as any)?.message ? String((e as any).message) : String(e);
}

function fmt(n: number | null | undefined, digits = 1) {
  if (n == null) return "—";
  return Number(n).toFixed(digits);
}

export function MatchmakingPortalApp() {
  const [health, setHealth] = useState<{ ok: boolean; service: string; env: string } | null>(null);
  const [sess, setSess] = useState(() => loadSession());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // auth
  const [phone, setPhone] = useState<string>("+919999000010");
  const [otpRequestId, setOtpRequestId] = useState<string>("");
  const [otp, setOtp] = useState<string>("");
  const [devOtp, setDevOtp] = useState<string>("");

  // inputs
  const [riderLat, setRiderLat] = useState<string>("18.5204");
  const [riderLon, setRiderLon] = useState<string>("73.8567");
  const [radiusKm, setRadiusKm] = useState<string>("8");
  const [laneId, setLaneId] = useState<string>("store:PUNE:WAKAD");

  const [minBatt, setMinBatt] = useState<string>("20");
  const [maxTelemMin, setMaxTelemMin] = useState<string>("120");
  const [limit, setLimit] = useState<string>("8");

  const [demandCards, setDemandCards] = useState<DemandCard[] | null>(null);
  const [availability, setAvailability] = useState<Availability | null>(null);
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null);
  const [audit, setAudit] = useState<AuditRow[]>([]);

  const lat = Number(riderLat);
  const lon = Number(riderLon);
  const maxKm = Number(radiusKm);

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
    setOtpRequestId("");
    setOtp("");
    setDevOtp("");
    setDemandCards(null);
    setAvailability(null);
    setRecommendation(null);
  }

  useEffect(() => {
    api.health()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  async function refreshDemand() {
    if (!sess?.token) return;
    const res = await api.demandNearby(sess.token, lat, lon, Math.max(1, maxKm));
    setDemandCards(res.cards ?? []);
  }

  async function refreshMatchmaking() {
    if (!sess?.token) return;
    const avail = await api.availability(sess.token, laneId.trim(), lat, lon, Math.max(1, maxKm));
    setAvailability(avail);
    const rec = await api.recommend(sess.token, {
      lane_id: laneId.trim(),
      rider_lat: lat,
      rider_lon: lon,
      max_km: Math.max(1, maxKm),
      min_battery_pct: Math.max(0, Math.min(100, Number(minBatt))),
      max_telemetry_age_min: Math.max(1, Math.min(1440, Number(maxTelemMin))),
      limit: Math.max(1, Math.min(30, Number(limit))),
    });
    setRecommendation(rec);
    const a = await api.auditRecent(sess.token, 50);
    setAudit(a.items ?? []);
  }

  useEffect(() => {
    if (!sess?.token) return;
    refreshMatchmaking().catch(() => null);
    const t = window.setInterval(() => refreshMatchmaking().catch(() => null), 8000);
    return () => window.clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sess?.token, laneId, riderLat, riderLon, radiusKm, minBatt, maxTelemMin, limit]);

  const top = (recommendation?.recommended as any) || null;
  const alts = recommendation?.alternatives ?? [];

  const operatorTable = useMemo(() => {
    const ops = availability?.operators ?? [];
    return [...ops].sort((a, b) => (b.available_vehicles || 0) - (a.available_vehicles || 0));
  }, [availability?.operators]);

  if (!sess?.token) {
    return (
      <div className="app">
        <aside className="sidebar">
          <div className="brand">Eleride Matchmaking Console</div>
          <div className="helper">Login using Rider OTP (MVP) to use the matching APIs.</div>
          <div className="helper">API: {api.base} • {health?.env ?? "—"}</div>
        </aside>
        <main className="main">
          {error ? <div className="card">{error}</div> : null}
          <div className="card stack" style={{ maxWidth: 520 }}>
            <div className="title">Login</div>
            <div>
              <label>Phone</label>
              <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+919999000010" />
            </div>
            <button
              className="btn btnPrimary"
              disabled={busy}
              onClick={() =>
                run(async () => {
                  const r = await api.otpRequest(phone.trim());
                  setOtpRequestId(r.request_id);
                  setDevOtp((r as any).dev_otp ?? "");
                })
              }
            >
              Send OTP
            </button>
            {otpRequestId ? (
              <div className="stack">
                <div>
                  <label>OTP</label>
                  <input value={otp} onChange={(e) => setOtp(e.target.value)} placeholder="6-digit OTP" />
                  {devOtp ? <div className="helper">Dev OTP: {devOtp}</div> : null}
                </div>
                <button
                  className="btn btnPrimary"
                  disabled={busy || otp.trim().length < 4}
                  onClick={() =>
                    run(async () => {
                      const s = await api.otpVerify(otpRequestId, otp.trim());
                      const next = { token: s.access_token, phone: phone.trim() } as const;
                      saveSession(next);
                      setSess(next);
                    })
                  }
                >
                  Verify & Enter
                </button>
              </div>
            ) : null}
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">Eleride Matchmaking Console</div>
        <div className="helper">Auto-assign (moat): constraints → scoring → decision (with reasons).</div>
        <div className="row">
          <span className="pill">{sess.phone}</span>
          <span className="pill">API: {api.base}</span>
        </div>
        <div className="divider" style={{ height: 1, background: "rgba(15,23,42,0.10)", margin: "12px 0" }} />

        <div className="stack">
          <div>
            <label>Rider lat</label>
            <input value={riderLat} onChange={(e) => setRiderLat(e.target.value)} />
          </div>
          <div>
            <label>Rider lon</label>
            <input value={riderLon} onChange={(e) => setRiderLon(e.target.value)} />
          </div>
          <div>
            <label>Lane ID</label>
            <input value={laneId} onChange={(e) => setLaneId(e.target.value)} placeholder="store:PUNE:WAKAD" />
          </div>

          <div className="grid2">
            <div>
              <label>Max km</label>
              <input value={radiusKm} onChange={(e) => setRadiusKm(e.target.value)} inputMode="decimal" />
            </div>
            <div>
              <label>Min battery %</label>
              <input value={minBatt} onChange={(e) => setMinBatt(e.target.value)} inputMode="decimal" />
            </div>
          </div>

          <div className="grid2">
            <div>
              <label>Max telemetry age (min)</label>
              <input value={maxTelemMin} onChange={(e) => setMaxTelemMin(e.target.value)} inputMode="numeric" />
            </div>
            <div>
              <label>Top N</label>
              <input value={limit} onChange={(e) => setLimit(e.target.value)} inputMode="numeric" />
            </div>
          </div>

          <button className="btn" disabled={busy} onClick={() => run(refreshDemand)}>
            Load demand lanes
          </button>
          <button className="btn btnPrimary" disabled={busy} onClick={() => run(refreshMatchmaking)}>
            Run matching now
          </button>
          <button className="btn" onClick={signOut}>
            Sign out
          </button>
        </div>
      </aside>

      <main className="main">
        {error ? <div className="card">{error}</div> : null}

        <div className="grid2">
          <div className="card stack">
            <div className="row" style={{ justifyContent: "space-between" }}>
              <div>
                <div className="title">Decision</div>
                <div className="helper">This is what the platform will auto-assign.</div>
              </div>
              <span className="pill">Refreshes ~8s</span>
            </div>

            {!top ? (
              <div className="helper">No eligible vehicles under current constraints.</div>
            ) : (
              <div className="stack">
                <div className="row">
                  <span className="tag tagOk">Recommended</span>
                  <span className="tag">{top.operator_id}</span>
                  <span className="tag">{top.registration_number}</span>
                  <span className="tag">Score {fmt(top.score, 0)}</span>
                </div>
                <div className="grid2">
                  <div>
                    <div className="helper">Distance</div>
                    <div style={{ fontWeight: 1000 }}>{fmt(top.distance_km)} km</div>
                  </div>
                  <div>
                    <div className="helper">Battery</div>
                    <div style={{ fontWeight: 1000 }}>{top.battery_pct != null ? `${fmt(top.battery_pct, 0)}%` : "—"}</div>
                  </div>
                </div>
                <div>
                  <div style={{ fontWeight: 1000 }}>Why</div>
                  <ul className="reasonList">
                    {(top.reasons ?? []).map((r: string) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                </div>
              </div>
            )}

            {alts.length ? (
              <div className="stack">
                <div style={{ fontWeight: 1000 }}>Alternatives</div>
                <table className="table">
                  <thead>
                    <tr>
                      <th>Operator</th>
                      <th>Vehicle</th>
                      <th>Score</th>
                      <th>Dist</th>
                      <th>Battery</th>
                    </tr>
                  </thead>
                  <tbody>
                    {alts.slice(0, 6).map((a: any) => (
                      <tr key={a.vehicle_id}>
                        <td>{a.operator_id}</td>
                        <td style={{ fontWeight: 900 }}>{a.registration_number}</td>
                        <td>{fmt(a.score, 0)}</td>
                        <td>{a.distance_km != null ? `${fmt(a.distance_km)} km` : "—"}</td>
                        <td>{a.battery_pct != null ? `${fmt(a.battery_pct, 0)}%` : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </div>

          <div className="card stack">
            <div className="row" style={{ justifyContent: "space-between" }}>
              <div>
                <div className="title">Multi-operator availability</div>
                <div className="helper">Real-time fleet posture by operator (capacity + load signals).</div>
              </div>
              <span className="pill">{availability?.lane?.source ?? "—"}</span>
            </div>

            {!availability ? (
              <div className="helper">Run matching to see availability.</div>
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th>Operator</th>
                    <th>Active</th>
                    <th>Available</th>
                    <th>Inbox new</th>
                    <th>Maint</th>
                  </tr>
                </thead>
                <tbody>
                  {operatorTable.map((o) => (
                    <tr key={o.operator_id}>
                      <td style={{ fontWeight: 900 }}>{o.operator_name ?? o.operator_id}</td>
                      <td>{o.active_vehicles}</td>
                      <td>{o.available_vehicles}</td>
                      <td>
                        <span className={o.inbox_new > 3 ? "tag tagWarn" : "tag"}>{o.inbox_new}</span>
                      </td>
                      <td>
                        <span className={o.open_maintenance_vehicles > 3 ? "tag tagWarn" : "tag"}>{o.open_maintenance_vehicles}</span>
                      </td>
                    </tr>
                  ))}
                  {operatorTable.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="helper">
                        No operators yet.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            )}
          </div>
        </div>

        <div className="card stack" style={{ marginTop: 12 }}>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <div>
              <div className="title">Demand lanes</div>
              <div className="helper">Pick a lane → instantly see recommendation + reasons.</div>
            </div>
            <span className="pill">{demandCards ? `${demandCards.length} lanes` : "—"}</span>
          </div>

          {!demandCards ? (
            <div className="helper">Click “Load demand lanes”.</div>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Lane</th>
                  <th>QC</th>
                  <th>Distance</th>
                  <th>Slots</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {demandCards.slice(0, 12).map((c) => (
                  <tr key={c.lane_id}>
                    <td style={{ fontWeight: 900 }}>{c.lane_id}</td>
                    <td className="helper">{c.qc_name}</td>
                    <td>{fmt(c.distance_km)} km</td>
                    <td>{c.slots_available}</td>
                    <td>
                      <button className="btn btnPrimary" onClick={() => setLaneId(c.lane_id)}>
                        Select
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="card stack" style={{ marginTop: 12 }}>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <div>
              <div className="title">Recent assignments (last 50)</div>
              <div className="helper">Shows stored audit fields on each supply request (matched vehicle, score, reasons).</div>
            </div>
            <span className="pill">{audit.length} rows</span>
          </div>

          <table className="table">
            <thead>
              <tr>
                <th>Created</th>
                <th>Lane</th>
                <th>Operator</th>
                <th>Vehicle</th>
                <th>Score</th>
                <th>Why</th>
              </tr>
            </thead>
            <tbody>
              {audit.slice(0, 50).map((r) => (
                <tr key={r.request_id}>
                  <td className="helper">{new Date(r.created_at).toLocaleString()}</td>
                  <td style={{ fontWeight: 900 }}>{r.lane_id}</td>
                  <td>{r.operator_id ?? "—"}</td>
                  <td>{r.matched_vehicle_id ? r.matched_vehicle_id.slice(0, 8) + "…" : "—"}</td>
                  <td>{r.matched_score != null ? String(Math.round(r.matched_score)) : "—"}</td>
                  <td>
                    {r.matched_reasons?.length ? (
                      <ul className="reasonList">
                        {r.matched_reasons.slice(0, 4).map((x) => (
                          <li key={x}>{x}</li>
                        ))}
                      </ul>
                    ) : (
                      <span className="helper">—</span>
                    )}
                  </td>
                </tr>
              ))}
              {audit.length === 0 ? (
                <tr>
                  <td colSpan={6} className="helper">
                    No assignments yet. Create a supply request from the Rider App (“Connect me”) or run the flow in dev.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </main>
    </div>
  );
}


